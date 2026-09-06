"""Exclusive flock helpers so parallel ai-art runs cannot fight over Qwen/Comfy."""

from __future__ import annotations

import fcntl
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from ai_art import config
from ai_art.preflight import PreflightError, log

LOCK_PATH = config.LOG_DIR / "pipeline.lock"


@contextmanager
def pipeline_lock(*, timeout_s: float = 7200.0, poll_s: float = 2.0) -> Iterator[None]:
    """Hold an exclusive lock for the whole generate pipeline.

    Parallel runs on this UMA host must not start/stop Qwen while another job
    is using Comfy (or the reverse).
    """
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(LOCK_PATH), os.O_CREAT | os.O_RDWR, 0o644)
    deadline = time.time() + timeout_s
    logged_wait = False
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.time() >= deadline:
                    raise PreflightError(
                        f"timed out after {timeout_s:.0f}s waiting for pipeline lock "
                        f"({LOCK_PATH}). Another ai-art run is still active — do not "
                        "start multiple full runs in parallel on this host."
                    )
                if not logged_wait:
                    log(
                        f"waiting for pipeline lock ({LOCK_PATH}); "
                        "another ai-art run holds Qwen/Comfy"
                    )
                    logged_wait = True
                time.sleep(poll_s)
        os.write(fd, f"pid={os.getpid()} started={time.time():.0f}\n".encode())
        os.fsync(fd)
        log(f"acquired pipeline lock pid={os.getpid()}")
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
        log("released pipeline lock")
