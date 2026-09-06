"""Rebuild gallery.json and docs/index.html from run metadata."""

from __future__ import annotations

import json

from ai_art import config

INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AI Art — Australian News</title>
  <style>
    :root {
      --bg: #0f1210;
      --panel: #1a1f1c;
      --ink: #e8ebe4;
      --muted: #9aa396;
      --accent: #c4a574;
      --line: #2a312c;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif;
      background:
        radial-gradient(1200px 600px at 10% -10%, #243028 0%, transparent 55%),
        radial-gradient(900px 500px at 100% 0%, #2a2218 0%, transparent 50%),
        var(--bg);
      color: var(--ink);
      min-height: 100vh;
    }
    header {
      padding: 2.5rem 1.25rem 1rem;
      max-width: 1200px;
      margin: 0 auto;
    }
    h1 {
      font-size: clamp(2rem, 5vw, 3.2rem);
      font-weight: 600;
      letter-spacing: -0.02em;
      margin: 0 0 0.4rem;
    }
    .sub {
      color: var(--muted);
      max-width: 40rem;
      line-height: 1.45;
      margin: 0 0 1.5rem;
    }
    .controls {
      display: flex;
      flex-wrap: wrap;
      gap: 0.75rem;
      align-items: center;
    }
    label { color: var(--muted); font-size: 0.95rem; }
    input[type="search"] {
      flex: 1 1 240px;
      min-width: 200px;
      background: var(--panel);
      border: 1px solid var(--line);
      color: var(--ink);
      padding: 0.7rem 0.9rem;
      font: inherit;
      border-radius: 2px;
    }
    input[type="search"]:focus {
      outline: 1px solid var(--accent);
      border-color: var(--accent);
    }
    main {
      max-width: 1200px;
      margin: 0 auto;
      padding: 0.5rem 1.25rem 3rem;
    }
    .run {
      margin: 2rem 0 3rem;
    }
    .run-head {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem 1rem;
      align-items: baseline;
      border-bottom: 1px solid var(--line);
      padding-bottom: 0.6rem;
      margin-bottom: 1rem;
    }
    .run-head h2 {
      margin: 0;
      font-size: 1.35rem;
      font-weight: 600;
    }
    .meta { color: var(--muted); font-size: 0.95rem; }
    .themes {
      width: 100%;
      color: var(--accent);
      font-size: 0.9rem;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
      gap: 1rem;
    }
    figure {
      margin: 0;
    }
    figure img {
      width: 100%;
      height: auto;
      display: block;
      background: var(--panel);
      border: 1px solid var(--line);
      cursor: zoom-in;
    }
    figcaption {
      margin-top: 0.45rem;
      font-size: 0.9rem;
      color: var(--muted);
      line-height: 1.35;
    }
    figcaption a {
      color: var(--muted);
      text-decoration: none;
      border-bottom: 1px solid transparent;
    }
    figcaption a:hover {
      color: var(--accent);
      border-bottom-color: var(--accent);
    }
    .empty {
      color: var(--muted);
      padding: 2rem 0;
    }
    footer {
      max-width: 1200px;
      margin: 0 auto;
      padding: 1rem 1.25rem 2.5rem;
      color: var(--muted);
      font-size: 0.85rem;
    }
    a { color: var(--accent); }

    /* Fullscreen lightbox */
    .lightbox {
      display: none;
      position: fixed;
      inset: 0;
      z-index: 1000;
      background: rgba(0, 0, 0, 0.92);
      align-items: center;
      justify-content: center;
      padding: 1rem;
      cursor: zoom-out;
    }
    .lightbox.open { display: flex; }
    .lightbox img {
      max-width: min(96vw, 1400px);
      max-height: 94vh;
      width: auto;
      height: auto;
      object-fit: contain;
      box-shadow: 0 8px 40px rgba(0,0,0,0.5);
      cursor: default;
    }
    .lightbox-close {
      position: absolute;
      top: 1rem;
      right: 1.25rem;
      background: transparent;
      border: none;
      color: var(--ink);
      font-size: 2rem;
      line-height: 1;
      cursor: pointer;
      opacity: 0.8;
    }
    .lightbox-close:hover { opacity: 1; }

    /* Detail view */
    .detail-back {
      display: inline-block;
      margin-bottom: 1.25rem;
      color: var(--accent);
      text-decoration: none;
      font-size: 0.95rem;
    }
    .detail-back:hover { text-decoration: underline; }
    .detail {
      max-width: 720px;
    }
    .detail img {
      width: 100%;
      height: auto;
      display: block;
      background: var(--panel);
      border: 1px solid var(--line);
      cursor: zoom-in;
    }
    .detail h2 {
      margin: 1.25rem 0 0.35rem;
      font-size: 1.5rem;
      font-weight: 600;
    }
    .detail .meta { margin-bottom: 1rem; }
    .detail .desc {
      line-height: 1.55;
      color: var(--ink);
      white-space: pre-wrap;
    }
    .home-controls.hidden,
    .home-footer.hidden { display: none; }
  </style>
</head>
<body>
  <header>
    <h1>AI Art</h1>
    <p class="sub">Daily artworks from Australian news.</p>
    <div class="controls home-controls" id="homeControls">
      <label for="artistFilter">Filter by artist</label>
      <input id="artistFilter" type="search" placeholder="e.g. Hopper, Nolan, Adams…" autocomplete="off" />
    </div>
  </header>
  <main id="gallery"><p class="empty">Loading…</p></main>
  <footer class="home-footer" id="homeFooter">
    Generated locally. Source prompts and news summaries live in each run’s <code>meta.json</code>.
  </footer>
  <div id="lightbox" class="lightbox" role="dialog" aria-modal="true" aria-label="Fullscreen image">
    <button type="button" class="lightbox-close" id="lightboxClose" aria-label="Close">&times;</button>
    <img id="lightboxImg" alt="" />
  </div>
  <script>
    async function load() {
      const res = await fetch('gallery.json?_=' + Date.now());
      const data = await res.json();
      const runs = data.runs || [];
      const main = document.getElementById('gallery');
      const input = document.getElementById('artistFilter');
      const homeControls = document.getElementById('homeControls');
      const homeFooter = document.getElementById('homeFooter');
      const lightbox = document.getElementById('lightbox');
      const lightboxImg = document.getElementById('lightboxImg');

      function escapeHtml(s) {
        return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
      }
      function escapeAttr(s) { return escapeHtml(s); }

      function parseRoute() {
        const raw = location.hash.replace(/^#\\/?/, '');
        const parts = raw.split('/').filter(Boolean);
        if (parts.length >= 2 && /^\\d{4}-\\d{2}-\\d{2}$/.test(parts[0])) {
          return { view: 'detail', date: parts[0], index: parseInt(parts[1], 10) };
        }
        if (parts.length === 1 && /^\\d{4}-\\d{2}-\\d{2}$/.test(parts[0])) {
          return { view: 'home', date: parts[0], index: null };
        }
        return { view: 'home', date: '', index: null };
      }

      function findImage(date, index) {
        const run = runs.find(r => r.date === date);
        if (!run) return null;
        const img = (run.images || []).find(i => Number(i.index) === Number(index));
        if (!img) return null;
        return { run, img };
      }

      function openLightbox(src, alt) {
        lightboxImg.src = src;
        lightboxImg.alt = alt || '';
        lightbox.classList.add('open');
        document.body.style.overflow = 'hidden';
      }
      function closeLightbox() {
        lightbox.classList.remove('open');
        lightboxImg.removeAttribute('src');
        document.body.style.overflow = '';
      }
      lightbox.addEventListener('click', (e) => {
        if (e.target === lightbox || e.target === document.getElementById('lightboxClose')) {
          closeLightbox();
        }
      });
      document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && lightbox.classList.contains('open')) closeLightbox();
      });

      function renderHome() {
        homeControls.classList.remove('hidden');
        homeFooter.classList.remove('hidden');
        const params = new URLSearchParams(location.search);
        const qParam = params.get('artist') || '';
        if (qParam && !input.value) input.value = qParam;
        const route = parseRoute();
        const q = (input.value || '').trim().toLowerCase();
        const filtered = runs.filter(r => {
          if (route.date && r.date !== route.date) return false;
          if (!q) return true;
          const hay = ((r.artist && r.artist.name) || '') + ' ' + ((r.artist && r.artist.id) || '');
          return hay.toLowerCase().includes(q);
        });
        if (!filtered.length) {
          main.innerHTML = '<p class="empty">No runs match this filter.</p>';
          return;
        }
        main.innerHTML = filtered.map(run => {
          const themes = (run.themes || []).join(' · ');
          const imgs = (run.images || []).map(img => {
            const src = 'runs/' + run.date + '/' + (img.jpg || img.png);
            const idx = img.index;
            const title = img.title || '';
            return `
            <figure>
              <img src="${escapeAttr(src)}" alt="${escapeAttr(title)}" loading="lazy"
                   data-fullsrc="${escapeAttr(src)}" data-action="fullscreen" />
              <figcaption>
                <a href="#/${escapeAttr(run.date)}/${escapeAttr(String(idx))}" data-action="detail">${escapeHtml(title)}</a>
              </figcaption>
            </figure>`;
          }).join('');
          return `
            <section class="run" data-artist="${escapeAttr((run.artist && run.artist.name) || '')}" id="${run.date}">
              <div class="run-head">
                <h2>${escapeHtml((run.artist && run.artist.name) || 'Unknown')}</h2>
                <span class="meta">${escapeHtml(run.date)} · ${escapeHtml((run.artist && run.artist.renderMode) || '')}</span>
                ${themes ? `<div class="themes">${escapeHtml(themes)}</div>` : ''}
              </div>
              <div class="grid">${imgs}</div>
            </section>`;
        }).join('');
      }

      function renderDetail(date, index) {
        homeControls.classList.add('hidden');
        homeFooter.classList.add('hidden');
        const found = findImage(date, index);
        if (!found) {
          main.innerHTML = '<p class="empty">Artwork not found. <a href="#">Back</a></p>';
          return;
        }
        const { run, img } = found;
        const src = 'runs/' + run.date + '/' + (img.jpg || img.png);
        const title = img.title || 'Untitled';
        const desc = img.prompt || run.summary || '';
        const artist = (run.artist && run.artist.name) || '';
        const backHref = '#/' + run.date;
        main.innerHTML = `
          <article class="detail">
            <a class="detail-back" href="${escapeAttr(backHref)}">&larr; Back</a>
            <img src="${escapeAttr(src)}" alt="${escapeAttr(title)}"
                 data-fullsrc="${escapeAttr(src)}" data-action="fullscreen" />
            <h2>${escapeHtml(title)}</h2>
            <p class="meta">${escapeHtml(artist)} · ${escapeHtml(run.date)} · ${escapeHtml((run.artist && run.artist.renderMode) || '')}</p>
            <div class="desc">${escapeHtml(desc)}</div>
          </article>`;
      }

      function render() {
        const route = parseRoute();
        if (route.view === 'detail') {
          renderDetail(route.date, route.index);
        } else {
          renderHome();
        }
      }

      main.addEventListener('click', (e) => {
        const t = e.target;
        if (!(t instanceof Element)) return;
        const img = t.closest('[data-action="fullscreen"]');
        if (img) {
          e.preventDefault();
          openLightbox(img.getAttribute('data-fullsrc') || img.getAttribute('src'), img.getAttribute('alt'));
        }
      });

      input.addEventListener('input', () => {
        const v = input.value.trim();
        const url = new URL(location.href);
        if (v) url.searchParams.set('artist', v); else url.searchParams.delete('artist');
        history.replaceState(null, '', url);
        if (parseRoute().view === 'home') render();
      });
      window.addEventListener('hashchange', render);
      render();
    }
    load().catch(err => {
      document.getElementById('gallery').innerHTML =
        '<p class="empty">Could not load gallery.json</p>';
      console.error(err);
    });
  </script>
</body>
</html>
"""


def rebuild_gallery() -> dict:
    config.RUNS_DIR.mkdir(parents=True, exist_ok=True)
    runs: list[dict] = []
    for meta_path in sorted(config.RUNS_DIR.glob("*/meta.json"), reverse=True):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        runs.append(
            {
                "date": meta.get("date") or meta_path.parent.name,
                "artist": meta.get("artist") or {},
                "themes": meta.get("themes") or [],
                "summary": meta.get("summary") or "",
                "images": [
                    {
                        "index": im.get("index"),
                        "title": im.get("title"),
                        "jpg": im.get("jpg"),
                        "png": im.get("png"),
                        "prompt": im.get("prompt") or "",
                    }
                    for im in (meta.get("images") or [])
                ],
            }
        )
    payload = {"generated": True, "runs": runs}
    config.SITE_DIR.mkdir(parents=True, exist_ok=True)
    config.GALLERY_JSON.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    config.INDEX_HTML.write_text(INDEX_TEMPLATE, encoding="utf-8")
    return payload
