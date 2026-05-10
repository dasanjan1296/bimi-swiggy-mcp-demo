/**
 * Ingredient overlap with this week's actual cooking.
 *
 * Honesty principle (Pass 7): the app cannot truthfully say "uses what's in
 * your kitchen" because we don't track inventory in real time. What we CAN
 * truthfully say is "uses the same ingredients the cook reached for this
 * week" — that's a behavioural fact derived from `mealHistory`, not a
 * pantry-state guess.
 *
 * If the household made Dal Tadka two days ago (dal, ghee, jeera, tomato)
 * and Bimi suggests Khichdi (dal, ghee, jeera, rice), 3 of 4 ingredients
 * overlap with what was actively used. Higher overlap = higher chance the
 * pantry still carries it OR the cook can swing by the same shop she did
 * for Dal Tadka without scrambling for unfamiliar items.
 *
 * This module is presentational: the score it returns drives the meal-card
 * reason chip ("Uses ingredients from this week's cooking") and is NOT used
 * for ranking or recommendation logic — that lives elsewhere. Keeping it
 * pure (no React, no store) so it can be unit-tested in isolation.
 */

import type { MealHistoryEntry, MealSuggestion } from "./types";

/**
 * Lower-case + trim a single ingredient string for matching. Two ingredients
 * are "the same" if their normalised forms match. Generous on purpose:
 * "Dal" and "dal" should fold together; "Tomato " and "Tomato" likewise.
 *
 * We deliberately do NOT do plural-stripping or stem-matching: those create
 * false positives ("rice" matching "rice flour") that would let the chip
 * claim more overlap than is real.
 */
function normaliseIngredient(raw: string): string {
  return raw.trim().toLowerCase();
}

/**
 * Build a `dishName -> ingredientSet` lookup from every suggestion currently
 * known across all meal types. The same dish (Dal Tadka) typically has the
 * same ingredients regardless of slot, so we collapse across mealTypes —
 * if a dish appears in multiple slots with different ingredient lists, we
 * UNION them (better to over-include than under-include for overlap math).
 */
export function buildIngredientLookup(
  suggestions: Record<string, MealSuggestion[]>,
): Map<string, Set<string>> {
  const map = new Map<string, Set<string>>();
  for (const list of Object.values(suggestions)) {
    for (const s of list) {
      const dishKey = s.dishName.trim().toLowerCase();
      if (!dishKey) continue;
      const existing = map.get(dishKey) ?? new Set<string>();
      for (const ing of s.ingredients ?? []) {
        const k = normaliseIngredient(ing);
        if (k) existing.add(k);
      }
      map.set(dishKey, existing);
    }
  }
  return map;
}

export interface RecentOverlapArgs {
  suggestion: MealSuggestion;
  mealHistory: MealHistoryEntry[];
  ingredientLookup: Map<string, Set<string>>;
  /** Days back from `now` to include (default 14). */
  days?: number;
  /** Override for testability. */
  now?: Date;
}

/**
 * Returns 0..1 — fraction of `suggestion.ingredients` that appeared in any
 * dish cooked in the last `days` days of `mealHistory`.
 *
 * Returns 0 (not undefined / NaN) for the following degenerate cases so the
 * caller can treat the score uniformly:
 *   - history is empty (don't penalise new users with a low signal)
 *   - the suggestion itself has no ingredients listed
 *   - none of the historical dishes have a known ingredient set
 *
 * Matching uses the normalised lower-cased+trimmed form on both sides.
 */
export function computeRecentIngredientOverlap(args: RecentOverlapArgs): number {
  const { suggestion, mealHistory, ingredientLookup, days = 14, now = new Date() } = args;

  const sIngs = (suggestion.ingredients ?? [])
    .map(normaliseIngredient)
    .filter(Boolean);
  if (sIngs.length === 0) return 0;
  if (mealHistory.length === 0) return 0;

  // Cutoff in ms — entries older than `days` are ignored. We compare against
  // the entry's `date` (a YYYY-MM-DD string) parsed as UTC midnight.
  const cutoff = now.getTime() - days * 24 * 60 * 60 * 1000;

  // Union of every ingredient used across all dishes cooked within the window.
  const recentIngs = new Set<string>();
  for (const entry of mealHistory) {
    const t = new Date(entry.date).getTime();
    if (Number.isNaN(t) || t < cutoff) continue;
    const dishKey = entry.selectedMeal.trim().toLowerCase();
    const set = ingredientLookup.get(dishKey);
    if (!set) continue;
    for (const ing of set) recentIngs.add(ing);
  }
  if (recentIngs.size === 0) return 0;

  let hits = 0;
  for (const ing of sIngs) {
    if (recentIngs.has(ing)) hits += 1;
  }
  return hits / sIngs.length;
}
