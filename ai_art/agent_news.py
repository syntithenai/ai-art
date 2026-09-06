"""Brave Search + Qwen agent: gather AU news, summarize, write Comfy prompts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from urllib.parse import urlparse

import httpx

from ai_art import config
from ai_art.artists import Artist, render_mode_instruction

ALLOWED_SUFFIXES = tuple(config.NEWS_HOST_ALLOWLIST)
SAFETY_SUFFIX = config.SAFETY_SUFFIX


@dataclass
class NewsResult:
    summary: str
    themes: list[str]
    headlines: list[dict[str, str]]
    images: list[dict[str, str]]
    thin_search: bool = False
    raw_sources: list[dict[str, str]] = field(default_factory=list)


def _host_allowed(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return False
    host = host.lower()
    return any(host == s or host.endswith("." + s) for s in ALLOWED_SUFFIXES)


def _extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise ValueError("empty LLM response")
    # Strip markdown fences if present.
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


class NewsAgent:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self._owns = client is None
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(60.0, connect=15.0),
            headers={"User-Agent": config.USER_AGENT},
            follow_redirects=True,
        )

    def close(self) -> None:
        if self._owns:
            self.client.close()

    def __enter__(self) -> "NewsAgent":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def brave_search(self, query: str, *, count: int = 8) -> list[dict[str, str]]:
        if not config.BRAVE_SEARCH_API_KEY:
            raise RuntimeError("BRAVE_SEARCH_API_KEY is required")
        resp = self.client.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": query, "count": count, "country": "AU", "search_lang": "en"},
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": config.BRAVE_SEARCH_API_KEY,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        web = ((resp.json().get("web") or {}).get("results")) or []
        out: list[dict[str, str]] = []
        for item in web[:count]:
            url = (item.get("url") or "").strip()
            out.append(
                {
                    "title": (item.get("title") or "").strip(),
                    "url": url,
                    "snippet": (item.get("description") or "").strip(),
                    "source": "brave",
                }
            )
        return out

    def fetch_url(self, url: str, *, max_chars: int = 4000) -> str:
        if not _host_allowed(url):
            return f"[blocked host] {url}"
        try:
            resp = self.client.get(url, timeout=25.0)
            resp.raise_for_status()
            text = resp.text
        except Exception as exc:
            return f"[fetch failed] {url}: {exc}"
        # Crude HTML strip.
        text = re.sub(r"(?is)<script.*?>.*?</script>", " ", text)
        text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
        text = re.sub(r"(?is)<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > max_chars:
            text = text[: max_chars - 3] + "..."
        return text

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 2048,
        temperature: float = 0.4,
        retries: int = 6,
    ) -> str:
        import time

        from ai_art.preflight import ensure_qwen, log, qwen_health_ok

        payload = {
            "model": config.QWEN_MODEL,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        headers = {"Authorization": f"Bearer {config.QWEN_API_KEY}"}
        last_exc: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                resp = self.client.post(
                    f"{config.QWEN_BASE_URL}/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=180.0,
                )
                resp.raise_for_status()
                data = resp.json()
                msg = ((data.get("choices") or [{}])[0].get("message")) or {}
                content = msg.get("content") or ""
                return str(content).strip()
            except (httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError) as exc:
                last_exc = exc
                log(
                    f"Qwen chat connection error (attempt {attempt}/{retries}): {exc}; "
                    "re-ensuring Qwen"
                )
                try:
                    ensure_qwen(allow_restart=True)
                except Exception as ensure_exc:
                    log(f"ensure_qwen during chat retry failed: {ensure_exc}")
                time.sleep(min(2 ** attempt, 15))
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                code = exc.response.status_code if exc.response is not None else 0
                if code in {502, 503, 504}:
                    log(
                        f"Qwen chat HTTP {code} (attempt {attempt}/{retries}); "
                        f"healthy={qwen_health_ok()}; waiting"
                    )
                    if not qwen_health_ok():
                        try:
                            ensure_qwen(allow_restart=True)
                        except Exception as ensure_exc:
                            log(f"ensure_qwen during 5xx retry failed: {ensure_exc}")
                    time.sleep(min(2 ** attempt, 15))
                    continue
                raise
        raise RuntimeError(f"Qwen chat failed after {retries} retries: {last_exc}") from last_exc

    def gather_sources(
        self,
        on: date,
        *,
        topics: list[str] | None = None,
    ) -> list[dict[str, str]]:
        day = on.isoformat()
        topic_bits = [t.strip() for t in (topics or []) if t and str(t).strip()]
        if topic_bits:
            focus = " ".join(topic_bits[:6])
            queries = [
                f"Australia {focus} news {day}",
                f"Australia {topic_bits[0]} site:abc.net.au",
                f"Australia {' OR '.join(topic_bits[:3])} site:theguardian.com/australia-news",
                f"Australian {focus} news",
            ]
            if len(topic_bits) > 1:
                queries.append(f"Australia {topic_bits[1]} news")
        else:
            queries = [
                f"Australia news today {day}",
                "Australia top stories site:abc.net.au",
                "Australia politics economy climate news",
                "Australian breaking news site:theguardian.com/australia-news",
            ]
        seen: set[str] = set()
        sources: list[dict[str, str]] = []
        for q in queries:
            try:
                hits = self.brave_search(q, count=6)
            except Exception as exc:
                sources.append(
                    {
                        "title": f"search error: {q}",
                        "url": "",
                        "snippet": str(exc),
                        "source": "error",
                    }
                )
                continue
            for h in hits:
                url = h.get("url") or ""
                if not url or url in seen:
                    continue
                if url and not _host_allowed(url) and "australia" not in (
                    h.get("title", "") + h.get("snippet", "")
                ).lower():
                    # Keep AU-relevant even from other hosts if clearly Australian.
                    if "australia" not in (h.get("title", "") + " " + h.get("snippet", "")).lower():
                        continue
                seen.add(url)
                sources.append(h)
        # Fetch a few allowlisted pages for richer context.
        fetched = 0
        for s in sources:
            if fetched >= 5:
                break
            url = s.get("url") or ""
            if url and _host_allowed(url):
                body = self.fetch_url(url)
                s["body"] = body
                fetched += 1
        return sources

    def summarize(
        self,
        sources: list[dict[str, str]],
        on: date,
        *,
        topics: list[str] | None = None,
    ) -> dict[str, Any]:
        blob_parts = []
        for i, s in enumerate(sources[:20], 1):
            part = (
                f"[{i}] {s.get('title')}\nURL: {s.get('url')}\n"
                f"Snippet: {s.get('snippet')}\n"
            )
            if s.get("body"):
                part += f"Extract: {s['body'][:2500]}\n"
            blob_parts.append(part)
        evidence = "\n".join(blob_parts) or "(no sources)"
        topic_bits = [t.strip() for t in (topics or []) if t and str(t).strip()]
        focus_line = ""
        if topic_bits:
            focus_line = (
                "Focus the summary on these topic areas when present in the evidence: "
                + ", ".join(topic_bits)
                + ". Still note other major AU stories briefly if present.\n"
            )
        system = (
            "You are a careful Australian news analyst. "
            "Use only the provided evidence. Reply with JSON only."
        )
        user = (
            f"Date: {on.isoformat()}\n"
            f"{focus_line}"
            "Summarize recent Australian news from the evidence below.\n"
            "Return JSON with keys:\n"
            '  summary: string (2-4 paragraphs),\n'
            "  themes: string array (3-8 short theme labels),\n"
            '  headlines: array of {title, url} (up to 8, prefer real URLs from evidence).\n'
            "If evidence is thin, still summarize what you can and set themes accordingly.\n\n"
            f"EVIDENCE:\n{evidence}"
        )
        raw = self.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=1800,
            temperature=0.3,
        )
        data = _extract_json(raw)
        return {
            "summary": str(data.get("summary") or "").strip(),
            "themes": [str(t).strip() for t in (data.get("themes") or []) if str(t).strip()],
            "headlines": [
                {
                    "title": str(h.get("title") or "").strip(),
                    "url": str(h.get("url") or "").strip(),
                }
                for h in (data.get("headlines") or [])
                if isinstance(h, dict)
            ],
        }

    def write_prompts(
        self,
        *,
        summary_pack: dict[str, Any],
        artist: Artist,
        count: int = 10,
        topics: list[str] | None = None,
    ) -> list[dict[str, str]]:
        mode_help = render_mode_instruction(artist.render_mode)
        topic_bits = [t.strip() for t in (topics or []) if t and str(t).strip()]
        focus = ""
        if topic_bits:
            focus = (
                "Prioritize visual subjects drawn from these focus topics: "
                + ", ".join(topic_bits)
                + ".\n"
            )
        system = (
            "You write image-generation prompts for Flux / ComfyUI. "
            "Reply with JSON only. Each prompt must be a single detailed English paragraph."
        )
        user = (
            f"Artist of the day: {artist.name} (id={artist.id})\n"
            f"Era: {artist.era}\n"
            f"Render mode: {artist.render_mode}\n"
            f"{mode_help}\n\n"
            f"STYLE LOCK (must influence every prompt):\n{artist.style_lock}\n\n"
            f"NEGATIVE HINTS to avoid:\n{artist.negative_hint}\n\n"
            f"{focus}"
            "NEWS SUMMARY (subjects must come from this — do not invent unrelated topics):\n"
            f"{summary_pack.get('summary')}\n\n"
            f"Themes: {', '.join(summary_pack.get('themes') or [])}\n\n"
            f"Write exactly {count} distinct artworks inspired by the news summary, "
            "all consistently in the locked artist style and render mode.\n"
            "Translate news into visual scenes (metaphor allowed) suitable for fine art — "
            "avoid logos, readable text, watermarks, and real living politicians' exact likenesses; "
            "prefer symbolic crowds, places, weather, institutions, landscapes, and objects.\n"
            "Return JSON:\n"
            '{ "images": [ { "title": "...", "prompt": "full Flux prompt..." } ] }\n'
            "Each prompt must already include the style language (not just a short subject)."
        )
        raw = self.chat(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=3500,
            temperature=0.7,
        )
        data = _extract_json(raw)
        images = data.get("images") or []
        out: list[dict[str, str]] = []
        for item in images:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip() or f"Untitled {len(out)+1}"
            prompt = str(item.get("prompt") or "").strip()
            if not prompt:
                continue
            if "no text" not in prompt.lower() and "watermark" not in prompt.lower():
                prompt = prompt.rstrip(". ") + "." + SAFETY_SUFFIX
            out.append({"title": title, "prompt": prompt})
        return out[:count]


def run_news_to_prompts(
    artist: Artist,
    *,
    on: date | None = None,
    count: int = 10,
    topics: list[str] | None = None,
) -> NewsResult:
    from ai_art.preflight import ensure_qwen, log

    on = on or date.today()
    topic_bits = [t.strip() for t in (topics or []) if t and str(t).strip()]
    with NewsAgent() as agent:
        sources = agent.gather_sources(on, topics=topic_bits or None)
        thin = len([s for s in sources if s.get("url")]) < 3
        # Brave search can take 30s+; another process (Comfy MCP) may have
        # stopped Qwen in the meantime — bring it back before any LLM call.
        log("re-checking Qwen before summary/prompts")
        ensure_qwen(allow_restart=True)
        summary_pack = agent.summarize(sources, on, topics=topic_bits or None)
        if not summary_pack.get("summary"):
            summary_pack["summary"] = (
                "Limited Australian news evidence was available. "
                "Focus on weather, landscape, civic life, and community resilience themes."
            )
            thin = True
        ensure_qwen(allow_restart=True)
        images = agent.write_prompts(
            summary_pack=summary_pack,
            artist=artist,
            count=count,
            topics=topic_bits or None,
        )
        # Pad if LLM returned fewer than count (should be rare).
        while len(images) < count:
            n = len(images) + 1
            images.append(
                {
                    "title": f"Theme study {n}",
                    "prompt": (
                        f"{artist.style_lock} Symbolic Australian civic scene inspired by: "
                        f"{summary_pack['summary'][:400]}. Variation {n}."
                        f"{SAFETY_SUFFIX}"
                    ),
                }
            )
        return NewsResult(
            summary=summary_pack["summary"],
            themes=list(summary_pack.get("themes") or []),
            headlines=list(summary_pack.get("headlines") or []),
            images=images[:count],
            thin_search=thin,
            raw_sources=[
                {k: v for k, v in s.items() if k != "body"} for s in sources[:20]
            ],
        )
