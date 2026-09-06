"""Artist catalog loader and day-of-year rotation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from ai_art import config


@dataclass(frozen=True)
class Artist:
    id: str
    name: str
    era: str
    tags: list[str]
    render_mode: str  # photoreal | painterly | graphic
    style_lock: str
    negative_hint: str
    aspect_ratio: str

    @classmethod
    def from_dict(cls, raw: dict) -> "Artist":
        mode = (raw.get("renderMode") or "painterly").strip().lower()
        if mode not in {"photoreal", "painterly", "graphic"}:
            mode = "painterly"
        return cls(
            id=(raw.get("id") or "").strip(),
            name=(raw.get("name") or "").strip(),
            era=(raw.get("era") or "").strip(),
            tags=list(raw.get("tags") or []),
            render_mode=mode,
            style_lock=(raw.get("styleLock") or "").strip(),
            negative_hint=(raw.get("negativeHint") or "").strip(),
            aspect_ratio=(raw.get("aspectRatio") or "3:4").strip(),
        )


def load_artists(path: Path | None = None) -> list[Artist]:
    p = path or config.ARTISTS_PATH
    data = json.loads(p.read_text(encoding="utf-8"))
    items = data.get("artists") if isinstance(data, dict) else data
    artists = [Artist.from_dict(x) for x in (items or [])]
    artists = [a for a in artists if a.id and a.style_lock]
    if not artists:
        raise ValueError(f"no artists in {p}")
    return artists


def pick_artist(
    artists: list[Artist],
    *,
    on: date | None = None,
    artist_id: str | None = None,
) -> Artist:
    if artist_id:
        for a in artists:
            if a.id == artist_id or a.name.lower() == artist_id.lower():
                return a
        raise KeyError(f"artist not found: {artist_id}")
    d = on or date.today()
    # day_of_year is 1..366
    idx = (d.timetuple().tm_yday - 1) % len(artists)
    return artists[idx]


def render_mode_instruction(mode: str) -> str:
    if mode == "photoreal":
        return (
            "Render mode for ALL images: photorealistic photography / cinematic still. "
            "Use camera, lens, lighting, depth of field, and film language. "
            "Do not describe brushstrokes, paint, or illustration."
        )
    if mode == "graphic":
        return (
            "Render mode for ALL images: graphic print / poster / illustration. "
            "Use flat or limited color, strong silhouette, printmaking or poster language. "
            "Do not describe photoreal camera detail."
        )
    return (
        "Render mode for ALL images: painterly fine-art. "
        "Use medium, brushwork, pigment, and canvas/paper language. "
        "Do not describe modern digital cameras or photoreal CGI."
    )
