"""Paths, env, and shared settings for the ai-art pipeline."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
SITE_DIR = ROOT / "site"
RUNS_DIR = SITE_DIR / "runs"
ARTISTS_PATH = ROOT / "artists.json"
LOG_DIR = ROOT / "logs"
GALLERY_JSON = SITE_DIR / "gallery.json"
INDEX_HTML = SITE_DIR / "index.html"

load_dotenv(ROOT / ".env")
# Also allow secrets from sibling MCPs if not already set.
for extra in (
    Path("/home/stever/projects/gmail-mcp/.env"),
    Path("/home/stever/projects/qwen-server/env/qwen-server.env"),
    Path("/home/stever/projects/abc2book/local-resolver/.env"),
):
    if extra.is_file():
        load_dotenv(extra, override=False)

COMFY_MCP_PATH = Path(
    os.environ.get("COMFY_MCP_PATH", "/home/stever/projects/comfy-mcp")
).expanduser()
COMFYUI_START = Path(
    os.environ.get("COMFYUI_START", "/home/stever/projects/ComfyUI/start.sh")
).expanduser()
COMFY_URL = os.environ.get("COMFY_URL", "http://127.0.0.1:8188").rstrip("/")

QWEN_BASE_URL = os.environ.get("QWEN_BASE_URL", "http://127.0.0.1:8081/v1").rstrip("/")
QWEN_HEALTH_URL = os.environ.get(
    "QWEN_HEALTH_URL", QWEN_BASE_URL.rsplit("/v1", 1)[0] + "/health"
)
QWEN_ENGINE_URL = os.environ.get("QWEN_ENGINE_URL", "http://127.0.0.1:8000").rstrip("/")
QWEN_API_KEY = (os.environ.get("QWEN_API_KEY") or "").strip()
QWEN_MODEL = os.environ.get("QWEN_MODEL", "qwen3.8-off").strip()
QWEN_START_SCRIPT = Path(
    os.environ.get(
        "QWEN_START_SCRIPT",
        "/home/stever/projects/qwen-server/scripts/start-systemd.sh",
    )
).expanduser()
QWEN_STOP_SCRIPT = Path(
    os.environ.get(
        "QWEN_STOP_SCRIPT",
        "/home/stever/projects/qwen-server/scripts/stop-systemd.sh",
    )
).expanduser()

BRAVE_SEARCH_API_KEY = (os.environ.get("BRAVE_SEARCH_API_KEY") or "").strip()

GMAIL_ADDRESS = (os.environ.get("GMAIL_ADDRESS") or "").strip()
GMAIL_APP_PASSWORD = (
    (os.environ.get("GMAIL_APP_PASSWORD") or "").replace(" ", "").strip()
)
GMAIL_DEFAULT_TO = (
    (os.environ.get("GMAIL_DEFAULT_TO") or GMAIL_ADDRESS or "").strip()
)

PAGES_URL = os.environ.get(
    "AI_ART_PAGES_URL", "https://syntithenai.github.io/ai-art/"
).rstrip("/") + "/"

RESTORE_QWEN = os.environ.get("AI_ART_RESTORE_QWEN", "1").lower() in {
    "1",
    "true",
    "yes",
}

SAFETY_SUFFIX = (
    " COMPLETE self-contained composition with clear margin from all four edges, "
    "finished design that does not look cropped. No text, watermark, frame, logo, "
    "signature, or UI."
)

USER_AGENT = (
    "Mozilla/5.0 (compatible; ai-art/0.1; +https://syntithenai.github.io/ai-art/)"
)

NEWS_HOST_ALLOWLIST = (
    "abc.net.au",
    "theguardian.com",
    "smh.com.au",
    "afr.com",
    "news.com.au",
    "sbs.com.au",
    "theage.com.au",
    "canberratimes.com.au",
    "reuters.com",
    "apnews.com",
    "bbc.com",
    "bbc.co.uk",
)


def env_truthy(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).lower() in {"1", "true", "yes"}


def require_secrets(*, need_email: bool = True, need_brave: bool = True) -> list[str]:
    missing: list[str] = []
    if need_brave and not BRAVE_SEARCH_API_KEY:
        missing.append("BRAVE_SEARCH_API_KEY")
    if not QWEN_API_KEY:
        missing.append("QWEN_API_KEY")
    if need_email:
        if not GMAIL_ADDRESS:
            missing.append("GMAIL_ADDRESS")
        if not GMAIL_APP_PASSWORD:
            missing.append("GMAIL_APP_PASSWORD")
        if not GMAIL_DEFAULT_TO:
            missing.append("GMAIL_DEFAULT_TO")
    return missing
