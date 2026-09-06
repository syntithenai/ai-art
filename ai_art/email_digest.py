"""SMTP digest email with one CID-embedded artwork."""

from __future__ import annotations

import random
import smtplib
import ssl
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from ai_art import config


def send_digest(meta: dict, *, to: str | None = None) -> str:
    addr = config.GMAIL_ADDRESS
    pw = config.GMAIL_APP_PASSWORD
    recipient = (to or config.GMAIL_DEFAULT_TO).strip()
    if not addr or not pw:
        raise RuntimeError("GMAIL_ADDRESS and GMAIL_APP_PASSWORD required")
    if not recipient:
        raise RuntimeError("no email recipient")

    artist = (meta.get("artist") or {}).get("name") or "Artist"
    day = meta.get("date") or ""
    images = meta.get("images") or []
    if not images:
        raise RuntimeError("no images to email")

    choice = random.choice(images)
    run_dir = config.RUNS_DIR / day
    img_path = run_dir / (choice.get("jpg") or choice.get("png") or "")
    if not img_path.is_file():
        # fallback first image
        for im in images:
            cand = run_dir / (im.get("jpg") or im.get("png") or "")
            if cand.is_file():
                img_path = cand
                choice = im
                break
    if not img_path.is_file():
        raise RuntimeError(f"image file missing for email: {img_path}")

    pages = f"{config.PAGES_URL}#{day}"
    themes = ", ".join(meta.get("themes") or [])
    summary = (meta.get("summary") or "").strip()
    if len(summary) > 600:
        summary = summary[:597] + "..."

    subject = f"AI Art — {artist} — {day}"
    html = f"""\
<html><body style="font-family: Georgia, serif; color:#222; max-width:640px;">
  <h1 style="font-size:1.4rem; margin-bottom:0.2rem;">AI Art — {artist}</h1>
  <p style="color:#666; margin-top:0;">{day} · {(meta.get('artist') or {}).get('renderMode', '')}</p>
  <p>{_escape(summary)}</p>
  {f'<p style="color:#888;"><em>Themes: {_escape(themes)}</em></p>' if themes else ''}
  <p><strong>{_escape(choice.get('title') or 'Artwork')}</strong></p>
  <p><img src="cid:artwork" alt="artwork" style="max-width:100%; height:auto; border:1px solid #ddd;" /></p>
  <p><a href="{pages}">See all 10 artworks on GitHub Pages</a></p>
</body></html>
"""
    text = (
        f"AI Art — {artist} — {day}\n\n{summary}\n\n"
        f"Preview: {choice.get('title')}\n"
        f"See all: {pages}\n"
    )

    msg = MIMEMultipart("related")
    msg["Subject"] = subject
    msg["From"] = addr
    msg["To"] = recipient

    alt = MIMEMultipart("alternative")
    msg.attach(alt)
    alt.attach(MIMEText(text, "plain", "utf-8"))
    alt.attach(MIMEText(html, "html", "utf-8"))

    data = img_path.read_bytes()
    subtype = "jpeg" if img_path.suffix.lower() in {".jpg", ".jpeg"} else "png"
    image = MIMEImage(data, _subtype=subtype)
    image.add_header("Content-ID", "<artwork>")
    image.add_header("Content-Disposition", "inline", filename=img_path.name)
    msg.attach(image)

    context = ssl.create_default_context()
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=60) as smtp:
        smtp.ehlo()
        smtp.starttls(context=context)
        smtp.ehlo()
        smtp.login(addr, pw)
        smtp.send_message(msg)

    return f"sent to {recipient}: {subject}"


def _escape(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
