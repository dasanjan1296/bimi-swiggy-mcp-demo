"""
Link metadata extraction for dish suggestion URLs.

Supports YouTube and Instagram Reels via oEmbed APIs, with a generic
OpenGraph fallback for other URLs. All extraction is best-effort —
the caller should handle partial/empty metadata gracefully.
"""
import logging
import re
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

YOUTUBE_OEMBED = "https://www.youtube.com/oembed"
INSTAGRAM_OEMBED = "https://graph.facebook.com/v18.0/instagram_oembed"


@dataclass
class LinkMetadata:
    platform: str = "other"
    title: str | None = None
    author: str | None = None
    thumbnail_url: str | None = None
    description: str | None = None
    original_url: str = ""


def detect_platform(url: str) -> str:
    host = urlparse(url).hostname or ""
    host = host.lower().removeprefix("www.").removeprefix("m.")
    if host in ("youtube.com", "youtu.be"):
        return "youtube"
    if host in ("instagram.com",):
        return "instagram"
    return "other"


async def extract_metadata(url: str, instagram_token: str | None = None) -> LinkMetadata:
    """Extract metadata from a video URL. Never raises — returns partial data on failure."""
    platform = detect_platform(url)
    meta = LinkMetadata(platform=platform, original_url=url)

    try:
        if platform == "youtube":
            return await _extract_youtube(url, meta)
        elif platform == "instagram":
            return await _extract_instagram(url, meta, instagram_token)
        else:
            return await _extract_opengraph(url, meta)
    except Exception:
        logger.exception("Link metadata extraction failed for %s", url)
        return meta


async def _extract_youtube(url: str, meta: LinkMetadata) -> LinkMetadata:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(YOUTUBE_OEMBED, params={"url": url, "format": "json"})
        resp.raise_for_status()
        data = resp.json()

    meta.title = data.get("title")
    meta.author = data.get("author_name")
    meta.thumbnail_url = data.get("thumbnail_url")
    return meta


async def _extract_instagram(
    url: str, meta: LinkMetadata, token: str | None
) -> LinkMetadata:
    if not token:
        return await _extract_opengraph(url, meta)

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            INSTAGRAM_OEMBED,
            params={"url": url, "access_token": token},
        )
        if resp.status_code != 200:
            return await _extract_opengraph(url, meta)
        data = resp.json()

    meta.title = data.get("title")
    meta.author = data.get("author_name")
    meta.thumbnail_url = data.get("thumbnail_url")
    return meta


async def _extract_opengraph(url: str, meta: LinkMetadata) -> LinkMetadata:
    """Lightweight OG tag extraction — fetches only the first 32KB of HTML."""
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        resp = await client.get(url, headers={"User-Agent": "Bimi/1.0"})
        if resp.status_code != 200:
            return meta
        html = resp.text[:32_768]

    og_title = _og_content(html, "og:title")
    og_desc = _og_content(html, "og:description")
    og_image = _og_content(html, "og:image")

    meta.title = og_title or _html_title(html)
    meta.description = og_desc
    meta.thumbnail_url = og_image
    return meta


def _og_content(html: str, prop: str) -> str | None:
    pattern = rf'<meta[^>]+property=["\']?{re.escape(prop)}["\']?[^>]+content=["\']([^"\']+)["\']'
    match = re.search(pattern, html, re.IGNORECASE)
    if match:
        return match.group(1)
    pattern2 = rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']?{re.escape(prop)}["\']?'
    match2 = re.search(pattern2, html, re.IGNORECASE)
    return match2.group(1) if match2 else None


def _html_title(html: str) -> str | None:
    match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
    return match.group(1).strip() if match else None
