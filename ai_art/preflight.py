"""Health checks and restart helpers for Qwen + Comfy (UMA-safe phases)."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from ai_art import config

LOG_DIR = config.LOG_DIR
COMFY_PID_FILE = LOG_DIR / "comfy.pid"
COMFY_LOG = LOG_DIR / "comfy.log"


class PreflightError(RuntimeError):
    pass


def log(msg: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"[{stamp}] {msg}"
    print(line, flush=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with (LOG_DIR / "preflight.log").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _http_get(url: str, timeout_s: float = 5.0) -> tuple[int, str]:
    req = urllib.request.Request(url, method="GET", headers={"User-Agent": "ai-art-preflight"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return int(resp.status), resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return int(exc.code), body
    except urllib.error.URLError as exc:
        raise ConnectionError(str(exc.reason if hasattr(exc, "reason") else exc)) from exc


def _http_json(
    url: str,
    payload: dict,
    *,
    api_key: str = "",
    timeout_s: float = 60.0,
) -> dict:
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, data=data, method="POST", headers=headers)
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read().decode("utf-8"))


def qwen_health_ok() -> bool:
    try:
        code, _ = _http_get(config.QWEN_HEALTH_URL, timeout_s=3.0)
        return 200 <= code < 300
    except Exception:
        return False


def qwen_smoke_ok() -> bool:
    """Tiny completion through the proxy proves the model is loaded."""
    try:
        _http_json(
            f"{config.QWEN_BASE_URL}/chat/completions",
            {
                "model": config.QWEN_MODEL,
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 2,
                "stream": False,
                "chat_template_kwargs": {"enable_thinking": False},
            },
            api_key=config.QWEN_API_KEY,
            timeout_s=90.0,
        )
        return True
    except Exception as exc:
        log(f"qwen smoke failed: {exc}")
        return False


def start_qwen() -> None:
    """Start llama-server + proxy only (skip Open WebUI — it races under parallel starts)."""
    # Prefer direct systemctl so we never touch docker compose / Open WebUI.
    log("starting Qwen via systemctl --user (server + proxy; Open WebUI skipped)")
    completed = subprocess.run(
        ["systemctl", "--user", "start", "qwen-server", "qwen-proxy"],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "").strip()
        # Another process may already have brought it up.
        if qwen_health_ok():
            log(f"systemctl start returned {completed.returncode} but Qwen is healthy; continuing")
            return
        # Fall back to start script with WebUI disabled.
        script = config.QWEN_START_SCRIPT
        if script.is_file():
            log(f"systemctl start failed ({err}); trying {script} with QWEN_SKIP_WEBUI=1")
            env = os.environ.copy()
            env["QWEN_SKIP_WEBUI"] = "1"
            completed2 = subprocess.run(
                [str(script)],
                check=False,
                capture_output=True,
                text=True,
                timeout=600,
                env=env,
            )
            if completed2.returncode == 0:
                log((completed2.stdout or "qwen start ok").strip())
                return
            if qwen_health_ok():
                log("start script failed but Qwen health is OK; continuing")
                return
            err2 = (completed2.stderr or completed2.stdout or "").strip()
            raise PreflightError(f"Qwen start failed: {err2 or err or completed2.returncode}")
        raise PreflightError(f"Qwen start failed: {err or completed.returncode}")


def restart_qwen() -> None:
    log("restarting qwen-server + qwen-proxy")
    subprocess.run(
        ["systemctl", "--user", "restart", "qwen-server", "qwen-proxy"],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )


def stop_qwen() -> str:
    """Stop Qwen so Comfy can use VRAM (UMA safety)."""
    sys.path.insert(0, str(config.COMFY_MCP_PATH))
    try:
        from qwen_prep import stop_qwen_for_comfy  # type: ignore

        result = stop_qwen_for_comfy()
        log(f"stop_qwen_for_comfy: {result}")
        return str(result)
    except Exception as exc:
        log(f"comfy-mcp stop failed ({exc}); trying stop-systemd.sh")
        script = config.QWEN_STOP_SCRIPT
        if script.is_file():
            completed = subprocess.run(
                [str(script)],
                check=False,
                capture_output=True,
                text=True,
                timeout=120,
            )
            out = (completed.stdout or completed.stderr or "").strip()
            log(f"stop-systemd: {out or completed.returncode}")
            return out or "stopped"
        raise PreflightError(f"could not stop Qwen: {exc}") from exc


def wait_qwen_ready(*, timeout_s: float = 300.0, smoke: bool = True) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if qwen_health_ok():
            if not smoke or qwen_smoke_ok():
                log("Qwen ready")
                return
        time.sleep(3.0)
    raise PreflightError(f"Qwen not ready within {timeout_s:.0f}s")


def ensure_qwen(*, allow_restart: bool = True) -> None:
    """Phase A: Qwen must be healthy before news/LLM work."""
    missing = config.require_secrets(need_email=False, need_brave=False)
    if missing:
        raise PreflightError(f"missing secrets: {', '.join(missing)}")

    if qwen_health_ok() and qwen_smoke_ok():
        log("Qwen already healthy")
        return

    # Another parallel starter may be mid-boot — wait briefly before we start too.
    log("Qwen not healthy; waiting briefly in case another process is starting it")
    try:
        wait_qwen_ready(timeout_s=45.0, smoke=True)
        return
    except PreflightError:
        pass

    log("Qwen still down; starting")
    try:
        start_qwen()
    except PreflightError as exc:
        # Race: peer may have finished starting despite our error (docker webui conflict etc.).
        if qwen_health_ok() and qwen_smoke_ok():
            log(f"start reported error ({exc}) but Qwen is healthy now; continuing")
            return
        raise

    try:
        wait_qwen_ready(timeout_s=360.0, smoke=True)
        return
    except PreflightError:
        if qwen_health_ok() and qwen_smoke_ok():
            log("wait timed out earlier but Qwen is healthy now; continuing")
            return
        if not allow_restart:
            raise
        log("Qwen start did not become ready; one restart attempt")
        restart_qwen()
        wait_qwen_ready(timeout_s=360.0, smoke=True)


def comfy_health_ok() -> bool:
    try:
        code, body = _http_get(f"{config.COMFY_URL}/system_stats", timeout_s=5.0)
        return 200 <= code < 300 and "devices" in body
    except Exception:
        return False


def _comfy_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def start_comfy() -> None:
    script = config.COMFYUI_START
    if not script.is_file():
        raise PreflightError(f"Comfy start script missing: {script}")
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log(f"starting Comfy via {script} (log={COMFY_LOG})")
    with COMFY_LOG.open("ab") as logfh:
        proc = subprocess.Popen(
            [str(script)],
            stdout=logfh,
            stderr=subprocess.STDOUT,
            cwd=str(script.parent),
            start_new_session=True,
        )
    COMFY_PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    log(f"Comfy pid={proc.pid}")


def stop_comfy_process() -> None:
    if COMFY_PID_FILE.is_file():
        try:
            pid = int(COMFY_PID_FILE.read_text().strip())
        except ValueError:
            pid = 0
        if pid and _comfy_pid_alive(pid):
            log(f"stopping Comfy pid={pid}")
            try:
                os.killpg(pid, signal.SIGTERM)
            except ProcessLookupError:
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            time.sleep(2.0)
        COMFY_PID_FILE.unlink(missing_ok=True)
    # Also try pkill by port listen pattern if still up
    if comfy_health_ok():
        subprocess.run(
            ["pkill", "-f", "ComfyUI/main.py.*8188"],
            check=False,
            capture_output=True,
        )
        time.sleep(2.0)


def wait_comfy_ready(*, timeout_s: float = 180.0) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if comfy_health_ok():
            log("Comfy ready")
            return
        time.sleep(2.0)
    raise PreflightError(f"Comfy not ready within {timeout_s:.0f}s")


def ensure_comfy(*, allow_restart: bool = True) -> None:
    """Phase B helper: Comfy must be up (call after Qwen is stopped)."""
    if comfy_health_ok():
        log("Comfy already healthy")
        return
    log("Comfy not healthy; starting")
    start_comfy()
    try:
        wait_comfy_ready(timeout_s=180.0)
        return
    except PreflightError:
        if not allow_restart:
            raise
        log("Comfy start timed out; one restart attempt")
        stop_comfy_process()
        start_comfy()
        wait_comfy_ready(timeout_s=180.0)


def prepare_for_comfy() -> None:
    """Phase B: stop Qwen, then ensure Comfy."""
    stop_qwen()
    # Brief pause for VRAM to settle on unified memory hosts.
    time.sleep(3.0)
    # Confirm Qwen is down (best-effort).
    if qwen_health_ok():
        log("WARN: Qwen still reports health after stop; continuing carefully")
    ensure_comfy(allow_restart=True)


def free_comfy_models() -> None:
    try:
        data = json.dumps({"unload_models": True, "free_memory": True}).encode()
        req = urllib.request.Request(
            f"{config.COMFY_URL}/free",
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
        log("Comfy models freed")
    except Exception as exc:
        log(f"WARN: could not free Comfy models: {exc}")


def restore_qwen() -> None:
    """Phase C: bring Qwen back for other users/Cursor."""
    if not config.RESTORE_QWEN:
        log("AI_ART_RESTORE_QWEN=0; leaving Qwen stopped")
        return
    free_comfy_models()
    time.sleep(2.0)
    log("restoring Qwen after art run")
    start_qwen()
    try:
        wait_qwen_ready(timeout_s=360.0, smoke=True)
    except PreflightError as exc:
        log(f"WARN: Qwen restore incomplete: {exc}")


def check_config(*, need_email: bool = True) -> None:
    missing = config.require_secrets(need_email=need_email, need_brave=True)
    if missing:
        raise PreflightError(f"missing required config: {', '.join(missing)}")
    log("config secrets present")


def run_preflight_cli(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Ensure Qwen/Comfy services are healthy")
    p.add_argument(
        "--phase",
        choices=("a", "b", "c", "all"),
        default="a",
        help="a=ensure Qwen, b=stop Qwen+ensure Comfy, c=restore Qwen, all=a then status",
    )
    p.add_argument("--skip-email-check", action="store_true")
    args = p.parse_args(argv)
    try:
        check_config(need_email=not args.skip_email_check)
        if args.phase in ("a", "all"):
            ensure_qwen()
            log(f"status qwen_health={qwen_health_ok()} comfy_health={comfy_health_ok()}")
        if args.phase == "b":
            prepare_for_comfy()
        if args.phase == "c":
            restore_qwen()
        return 0
    except PreflightError as exc:
        log(f"ERROR: {exc}")
        return 1


def main(argv: list[str] | None = None) -> int:
    return run_preflight_cli(argv)


if __name__ == "__main__":
    raise SystemExit(main())
