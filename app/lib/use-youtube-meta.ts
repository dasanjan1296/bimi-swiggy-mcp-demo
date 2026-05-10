/**
 * useYouTubeMeta — fetches channel name + canonical title for a
 * YouTube URL via the public oEmbed endpoint.
 *
 *   GET https://www.youtube.com/oembed?url=…&format=json
 *
 * The endpoint is keyless (no Google API quota), CORS-friendly, and
 * cached aggressively in react-query (one week stale time, no retries).
 * Used by the home self-cook sheet to surface "by Hebbar's Kitchen ·
 * Watch on YouTube" attribution beneath each recipe card.
 *
 * Failures (non-YouTube URLs, network blips, removed videos) resolve
 * to `null` so callers can render a graceful fallback layout instead
 * of a spinner.
 *
 * Why this lives client-side: the data is non-sensitive, the response
 * is small (~300 bytes), and routing it through our backend would only
 * add latency and operational surface. If we ever need video duration
 * (which oEmbed doesn't return), that requires the Google Data API
 * with a key and would belong on the backend.
 */

import { useQuery } from "@tanstack/react-query";

export interface YouTubeMeta {
  /** YouTube channel display name, e.g. "Hebbar's Kitchen". */
  channelName: string;
  /** Canonical video title (handy when a saved recipe has a stale title). */
  title: string;
  /** High-quality thumbnail (`hqdefault.jpg` equivalent). */
  thumbnailUrl: string;
}

const YT_HOST_RE = /(?:youtube\.com|youtu\.be|youtube-nocookie\.com)/i;

export function isYouTubeUrl(url: string | undefined | null): boolean {
  if (!url) return false;
  return YT_HOST_RE.test(url);
}

interface OembedResponse {
  author_name?: string;
  title?: string;
  thumbnail_url?: string;
}

export function useYouTubeMeta(url: string | undefined | null) {
  const enabled = isYouTubeUrl(url);
  return useQuery({
    queryKey: ["yt-oembed", url ?? "none"],
    enabled,
    // YouTube channel + title for a given URL is effectively immutable,
    // so we cache for a week. The query layer also dedupes concurrent
    // requests for the same URL across cards.
    staleTime: 1000 * 60 * 60 * 24 * 7,
    gcTime: 1000 * 60 * 60 * 24 * 7,
    retry: false,
    queryFn: async (): Promise<YouTubeMeta | null> => {
      if (!url) return null;
      const endpoint = `https://www.youtube.com/oembed?url=${encodeURIComponent(
        url,
      )}&format=json`;
      try {
        const res = await fetch(endpoint);
        if (!res.ok) return null;
        const data: OembedResponse = await res.json();
        if (!data.author_name) return null;
        return {
          channelName: data.author_name,
          title: data.title ?? "",
          thumbnailUrl: data.thumbnail_url ?? "",
        };
      } catch {
        // Treat all network/parse failures as "no metadata" so the
        // card falls back to its own description / saved-by byline.
        return null;
      }
    },
  });
}
