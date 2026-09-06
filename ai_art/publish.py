"""Commit site/ changes and push to GitHub Pages remote."""

from __future__ import annotations

import subprocess
from pathlib import Path

from ai_art import config
from ai_art.preflight import log


def _run(cmd: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(config.ROOT),
        check=check,
        capture_output=True,
        text=True,
    )


def git_available() -> bool:
    return (config.ROOT / ".git").is_dir()


def publish_site(*, message: str | None = None) -> str:
    if not git_available():
        raise RuntimeError("not a git repo — init/publish repo first")

    _run(["git", "add", "site", "artists.json", "README.md"], check=False)
    status = _run(["git", "status", "--porcelain"], check=False)
    if not (status.stdout or "").strip():
        log("publish: nothing to commit")
        # Still push in case remote is behind
        push = _run(["git", "push"], check=False)
        if push.returncode != 0:
            return f"nothing to commit; push: {(push.stderr or push.stdout).strip()}"
        return "nothing to commit; push ok"

    msg = message or "Update AI art gallery"
    commit = _run(["git", "commit", "-m", msg], check=False)
    if commit.returncode != 0:
        raise RuntimeError((commit.stderr or commit.stdout or "commit failed").strip())

    push = _run(["git", "push"])
    log("publish: pushed to remote")
    return (commit.stdout or "").strip() + "\n" + (push.stdout or "pushed").strip()
