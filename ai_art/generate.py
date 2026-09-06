"""Generate artworks via local Comfy (comfy-mcp) from LLM prompts."""

from __future__ import annotations

import json
import random
import re
import sys
from datetime import date
from pathlib import Path

from PIL import Image

from ai_art import config
from ai_art.agent_news import NewsResult
from ai_art.artists import Artist
from ai_art.preflight import ensure_comfy, log, prepare_for_comfy


def _import_generate_image():
    path = str(config.COMFY_MCP_PATH)
    if path not in sys.path:
        sys.path.insert(0, path)
    from comfy_mcp_server import generate_image  # type: ignore

    return generate_image


def png_to_jpeg(png_path: Path, jpeg_path: Path, quality: int = 90) -> None:
    with Image.open(png_path) as im:
        rgb = im.convert("RGB")
        jpeg_path.parent.mkdir(parents=True, exist_ok=True)
        rgb.save(jpeg_path, "JPEG", quality=quality, optimize=True)


def _parse_seed(result: str) -> int | None:
    m = re.search(r"seed=(\d+)", result or "")
    return int(m.group(1)) if m else None


def generate_run(
    artist: Artist,
    news: NewsResult,
    *,
    on: date | None = None,
    skip_preflight: bool = False,
    force: bool = False,
) -> dict:
    on = on or date.today()
    run_dir = config.RUNS_DIR / on.isoformat()
    run_dir.mkdir(parents=True, exist_ok=True)

    if not skip_preflight:
        prepare_for_comfy()
    else:
        ensure_comfy(allow_restart=False)

    generate_image = _import_generate_image()
    images_meta: list[dict] = []
    n = len(news.images)

    for i, item in enumerate(news.images, start=1):
        stem = f"{i:02d}"
        png = (run_dir / f"{stem}.png").resolve()
        jpg = (run_dir / f"{stem}.jpg").resolve()
        if png.is_file() and jpg.is_file() and not force:
            log(f"skip {stem} (exists)")
            images_meta.append(
                {
                    "index": i,
                    "title": item["title"],
                    "prompt": item["prompt"],
                    "png": png.name,
                    "jpg": jpg.name,
                    "seed": None,
                    "skipped": True,
                }
            )
            continue

        seed = random.randint(0, 2**31 - 1)
        free_after = i == n
        log(f"generating {stem}: {item['title'][:80]}")
        result = generate_image(
            prompt=item["prompt"],
            outputPath=str(png),
            style="flux_klein",
            aspect_ratio=artist.aspect_ratio,
            seed=seed,
            free_after=free_after,
        )
        if isinstance(result, str) and result.startswith("ERROR"):
            raise RuntimeError(f"Comfy generate failed for {stem}: {result}")
        if not png.is_file():
            raise RuntimeError(f"Comfy did not write {png}: {result}")
        png_to_jpeg(png, jpg)
        images_meta.append(
            {
                "index": i,
                "title": item["title"],
                "prompt": item["prompt"],
                "png": png.name,
                "jpg": jpg.name,
                "seed": _parse_seed(str(result)) or seed,
                "comfy": str(result),
                "skipped": False,
            }
        )

    meta = {
        "date": on.isoformat(),
        "artist": {
            "id": artist.id,
            "name": artist.name,
            "era": artist.era,
            "renderMode": artist.render_mode,
            "aspectRatio": artist.aspect_ratio,
            "tags": artist.tags,
        },
        "summary": news.summary,
        "themes": news.themes,
        "headlines": news.headlines,
        "thinSearch": news.thin_search,
        "sources": news.raw_sources,
        "images": images_meta,
    }
    meta_path = run_dir / "meta.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log(f"wrote {meta_path}")
    return meta
