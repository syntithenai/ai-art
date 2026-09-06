"""Orchestrator: preflight → news → prompts → Comfy → gallery → publish → email."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path

from ai_art import config
from ai_art.agent_news import run_news_to_prompts
from ai_art.artists import load_artists, pick_artist
from ai_art.email_digest import send_digest
from ai_art.gallery import rebuild_gallery
from ai_art.generate import generate_run
from ai_art.preflight import (
    PreflightError,
    check_config,
    ensure_qwen,
    log,
    restore_qwen,
)
from ai_art.publish import publish_site


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--date", default=None, help="YYYY-MM-DD (default: today)")
    p.add_argument("--artist", default=None, help="Artist id or name override")
    p.add_argument("--dry-run", action="store_true", help="Stop after writing prompts")
    p.add_argument("--skip-email", action="store_true")
    p.add_argument("--skip-publish", action="store_true")
    p.add_argument("--skip-preflight", action="store_true")
    p.add_argument("--skip-restore", action="store_true", help="Do not restart Qwen after")
    p.add_argument("--force", action="store_true", help="Regenerate images even if present")
    p.add_argument("--count", type=int, default=10)
    args = p.parse_args(argv)

    on = date.fromisoformat(args.date) if args.date else date.today()
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)

    try:
        check_config(need_email=not args.skip_email and not args.dry_run)
        if not args.skip_preflight:
            ensure_qwen()
        else:
            log("skip-preflight: assuming Qwen is up")

        artists = load_artists()
        artist = pick_artist(artists, on=on, artist_id=args.artist)
        log(
            f"artist of the day: {artist.name} ({artist.id}) "
            f"mode={artist.render_mode} aspect={artist.aspect_ratio}"
        )

        news = run_news_to_prompts(artist, on=on, count=args.count)
        log(
            f"news summary ok themes={news.themes!r} images={len(news.images)} "
            f"thin={news.thin_search}"
        )

        prompts_path = config.RUNS_DIR / on.isoformat() / "prompts.json"
        prompts_path.parent.mkdir(parents=True, exist_ok=True)
        prompts_path.write_text(
            json.dumps(
                {
                    "date": on.isoformat(),
                    "artist": artist.id,
                    "summary": news.summary,
                    "themes": news.themes,
                    "images": news.images,
                    "thinSearch": news.thin_search,
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        log(f"wrote {prompts_path}")

        if args.dry_run:
            log("dry-run: stopping before Comfy generation")
            return 0

        meta = generate_run(
            artist,
            news,
            on=on,
            skip_preflight=args.skip_preflight,
            force=args.force,
        )

        gallery = rebuild_gallery()
        log(f"gallery runs={len(gallery.get('runs') or [])}")

        if not args.skip_publish:
            try:
                out = publish_site(
                    message=f"AI art {on.isoformat()} — {artist.name}"
                )
                log(f"publish: {out}")
            except Exception as exc:
                log(f"ERROR publish: {exc}")
                return 1
        else:
            log("skip-publish")

        if not args.skip_email:
            try:
                out = send_digest(meta)
                log(out)
            except Exception as exc:
                log(f"ERROR email: {exc}")
                return 1
        else:
            log("skip-email")

        if not args.skip_restore and not args.skip_preflight:
            restore_qwen()

        log("done")
        return 0
    except PreflightError as exc:
        log(f"ERROR preflight: {exc}")
        return 1
    except Exception as exc:
        log(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
