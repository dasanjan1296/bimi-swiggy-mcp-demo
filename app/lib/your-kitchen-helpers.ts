/**
 * Pure helpers for the Your Kitchen UI (PRD §4.13).
 *
 * Lives in its own module so unit tests can import it without dragging in
 * the axios client / React Query / React Native imports from
 * `your-kitchen-api.ts`. Don't add any imports here that touch RN, axios,
 * or browser globals.
 */

export type Sentiment = "love" | "like" | "dislike" | "untried";

export type MemberReaction = {
  person_id: string;
  name: string;
  sentiment: Sentiment;
  confidence: number;
};

/** Human-friendly "12 days ago" / "yesterday" / "today". */
export function relativeServedLabel(days: number | null | undefined): string | null {
  if (days === null || days === undefined) return null;
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 7) return `${days} days ago`;
  if (days < 14) return "last week";
  if (days < 30) return `${Math.round(days / 7)} weeks ago`;
  if (days < 365) return `${Math.round(days / 30)} months ago`;
  return "over a year ago";
}

/** Initials for the member-reactions row avatars. */
export function initialsFor(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return "?";
  const parts = trimmed.split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/** Stable ordering for the reactions row: love → like → untried → dislike. */
export function sortReactionsForDisplay(reactions: MemberReaction[]): MemberReaction[] {
  const order: Record<Sentiment, number> = {
    love: 0,
    like: 1,
    untried: 2,
    dislike: 3,
  };
  return [...reactions].sort((a, b) => order[a.sentiment] - order[b.sentiment]);
}
