/**
 * useTasteStore — household-level dish preference seed captured at
 * onboarding (the swipe deck) and continuously updated as members rate
 * meals.
 *
 * The shape is intentionally tiny: three buckets keyed by dish slug
 * (matches `lib/dish-images.ts` keys). Downstream consumers:
 *
 *   • `useMealStore` ranking: any suggestion whose normalized name maps
 *     to a slug in `loved` gets a +0.20 boost; `liked` gets +0.10;
 *     `disliked` gets a hard −0.40 (effectively pushed off the top-3).
 *   • `generateProxyVotes()` cold-start: for households with no meal
 *     history, the taste seed substitutes for personal rating history
 *     when picking the proxy vote winner.
 *   • `home-state` Day-1 hero: if no suggestions exist yet, pick the
 *     top `loved` slug as the inaugural dinner suggestion.
 *
 * Persistence is in-memory + Zustand. We do not persist via AsyncStorage
 * here because the broader store file (`lib/store.ts`) intentionally
 * skipped the wrapper while the dev client AsyncStorage link is
 * pending — see the NOTE on persistence in that file.
 */

import { create } from "zustand";

export type TasteVerdict = "loved" | "liked" | "disliked";

export interface TasteEntry {
  slug: string;
  verdict: TasteVerdict;
  /** Member who cast this signal. "household" when set during onboarding. */
  source: string;
  /** ISO timestamp. Last write wins. */
  updatedAt: string;
}

interface TasteStoreState {
  entries: Record<string, TasteEntry>;
  /** Onboarding completion stamp — drives the "is the seed ready?" check. */
  seededAt: string | null;

  setVerdict: (slug: string, verdict: TasteVerdict, source?: string) => void;
  clearVerdict: (slug: string) => void;
  bulkSeed: (verdicts: { slug: string; verdict: TasteVerdict }[], source?: string) => void;
  reset: () => void;

  bySlug: (slug: string) => TasteEntry | undefined;
  bucket: (verdict: TasteVerdict) => string[];
  scoreFor: (slug: string) => number;
}

const TASTE_BOOST: Record<TasteVerdict, number> = {
  loved: 0.20,
  liked: 0.10,
  disliked: -0.40,
};

export const useTasteStore = create<TasteStoreState>((set, get) => ({
  entries: {},
  seededAt: null,

  setVerdict: (slug, verdict, source = "household") =>
    set((state) => ({
      entries: {
        ...state.entries,
        [slug]: { slug, verdict, source, updatedAt: new Date().toISOString() },
      },
    })),

  clearVerdict: (slug) =>
    set((state) => {
      const next = { ...state.entries };
      delete next[slug];
      return { entries: next };
    }),

  bulkSeed: (verdicts, source = "household") =>
    set(() => {
      const now = new Date().toISOString();
      const entries: Record<string, TasteEntry> = {};
      for (const v of verdicts) {
        entries[v.slug] = { slug: v.slug, verdict: v.verdict, source, updatedAt: now };
      }
      return { entries, seededAt: now };
    }),

  reset: () => set({ entries: {}, seededAt: null }),

  bySlug: (slug) => get().entries[slug],
  bucket: (verdict) =>
    Object.values(get().entries)
      .filter((e) => e.verdict === verdict)
      .map((e) => e.slug),
  scoreFor: (slug) => {
    const entry = get().entries[slug];
    return entry ? TASTE_BOOST[entry.verdict] : 0;
  },
}));

/** Slugify the same way `dish-images.ts` does so the maps line up. */
export function slugifyDishName(name: string): string {
  return name.toLowerCase().trim().replace(/\s+/g, "-");
}

/**
 * Apply the household's taste seed to a list of MealSuggestion-shaped
 * objects. Intended hook point for the voting + home recommendation
 * paths: today they read `suggestions[mealType]` straight from
 * `useMealStore` and trust the backend ordering. Once Day-1 households
 * exist (zero meal history, but a freshly seeded taste store), wrap the
 * list:
 *
 *     const tasteScore = useTasteStore((s) => s.scoreFor);
 *     const ranked = applyTasteRanking(suggestions[mealType] ?? [], tasteScore);
 *
 * The function never mutates the input. Suggestions whose dish name
 * doesn't slugify to anything in the store retain their original score.
 *
 * The combined score formula is intentionally conservative — taste is a
 * +/- 0.40 nudge on top of the baseline confidence, never a takeover.
 * That keeps the cook's repertoire and the missing-ingredients filter
 * dominant; we only re-sort the top-N, we don't push a never-cooked
 * dish into the top spot just because it was loved during onboarding.
 */
export function applyTasteRanking<T extends { dishName: string; confidence: number }>(
  suggestions: T[],
  scoreFor: (slug: string) => number,
): T[] {
  return [...suggestions].sort((a, b) => {
    const sa = (a.confidence ?? 0) + scoreFor(slugifyDishName(a.dishName));
    const sb = (b.confidence ?? 0) + scoreFor(slugifyDishName(b.dishName));
    return sb - sa;
  });
}
