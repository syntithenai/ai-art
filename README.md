# AI Art

Daily artworks generated from recent Australian news.

Each day the pipeline:

1. Ensures local **Qwen** is healthy (restarts via systemd if needed)
2. Searches news with **Brave Search**
3. Asks Qwen to **summarize** the news, then **write 10 Comfy/Flux prompts** in today’s locked artist style
4. Stops Qwen (UMA safety), ensures **ComfyUI** is up, generates 10 images
5. Rebuilds this GitHub Pages gallery
6. Emails one preview image with a link back here
7. Optionally restores Qwen

## Gallery

Open [https://syntithenai.github.io/ai-art/](https://syntithenai.github.io/ai-art/) and use the artist filter.

## Local run

```bash
cd /home/stever/projects/ai-art
cp .env.example .env   # fill BRAVE_SEARCH_API_KEY, QWEN_API_KEY, Gmail
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# Check / restart services
.venv/bin/python -m ai_art.preflight --phase a

# Full daily run
.venv/bin/python -m ai_art.run

# Prompt-only smoke test
.venv/bin/python -m ai_art.run --dry-run --skip-email --skip-publish
```

## Cron

```bash
crontab -l > /tmp/cron.bak
cat cron/ai-art.cron >> /tmp/cron.bak   # or merge carefully
crontab /tmp/cron.bak
```

## Layout

- `ai_art/` — Python package
- `artists.json` — curated style locks (`photoreal` / `painterly` / `graphic`)
- `site/` — GitHub Pages root (`index.html`, `gallery.json`, `runs/YYYY-MM-DD/`)
- `logs/` — cron / preflight logs

## Host notes

- Qwen: user systemd `qwen-server` + `qwen-proxy` (`:8081`)
- ComfyUI: `/home/stever/projects/ComfyUI/start.sh` on `:8188`
- Never run heavy Qwen and Comfy together on this machine
