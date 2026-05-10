"""YouTube oEmbed helper — fetch a video's title + thumbnail from a
public no-auth endpoint so the saved-recipes router can hydrate
user-pasted YouTube URLs without an API key.

oEmbed reference:
  https://www.youtube.com/oembed?url={youtube_url}&format=json

Returns JSON like:
  {
    "title": "How to cook foo",
    "author_name": "Hebbar's Kitchen",
    "thumbnail_url": "https://i.ytimg.com/vi/.../hqdefault.jpg",
    ...
  }

We treat oEmbed as a best-effort enrichment: if YouTube returns a
non-200 (private video, removed, rate-limited, etc.) we return None
and let the caller fall back to user-supplied title / image.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Literal

import httpx


logger = logging.getLogger("bimi")


SourcePlatform = Literal["youtube", "instagram", "web"]


@dataclass
class OEmbedResult:
    """Parsed subset of the oEmbed payload that the FE actually needs."""

    title: str
    author_name: str | None
    thumbnail_url: str | None


_YOUTUBE_HOST_PATTERN = re.compile(
    r"^(?:https?://)?(?:www\.|m\.)?(?:youtube\.com|youtu\.be|youtube-nocookie\.com)/",
    re.IGNORECASE,
)
_INSTAGRAM_HOST_PATTERN = re.compile(
    r"^(?:https?://)?(?:www\.)?instagram\.com/",
    re.IGNORECASE,
)


def detect_platform(url: str) -> SourcePlatform:
    """Classify a recipe URL into one of three buckets.

    The router routes hydration based on this:
      - `youtube` → fetch oEmbed for title + thumbnail
      - `instagram` → leave the user-supplied title/image alone (IG's
        oEmbed requires Meta Graph approval)
      - `web` → ditto: leave it to the user
    """
    url = url.strip()
    if _YOUTUBE_HOST_PATTERN.match(url):
        return "youtube"
    if _INSTAGRAM_HOST_PATTERN.match(url):
        return "instagram"
    return "web"


async def fetch_youtube_metadata(url: str, timeout: float = 6.0) -> OEmbedResult | None:
    """Fetch oEmbed metadata for a YouTube URL. Returns None on any
    failure (network, non-200, malformed payload) — never raises, since
    oEmbed enrichment is best-effort and shouldn't block a recipe save.
    """
    oembed_url = "https://www.youtube.com/oembed"
    params = {"url": url, "format": "json"}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(oembed_url, params=params)
        if resp.status_code != 200:
            logger.info(
                "youtube_oembed_non_200",
                extra={"status": resp.status_code, "url": url},
            )
            return None
        payload = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.info(
            "youtube_oembed_failed",
            extra={"err": str(exc), "url": url},
        )
        return None

    title = payload.get("title")
    if not isinstance(title, str) or not title.strip():
        return None

    return OEmbedResult(
        title=title.strip(),
        author_name=(payload.get("author_name") or None),
        thumbnail_url=(payload.get("thumbnail_url") or None),
    )
