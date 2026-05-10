/**
 * Home-state hooks — small, read-only selectors the NextBestAction
 * orchestrator consumes to decide which hero to render.
 *
 * Each hook returns either the salient object or null. No data mutation,
 * no side effects. Tree-shakeable; safe to call outside the Home tab.
 *
 * Priority tree (cook household — Bimi's only supported ICP as of
 * 2026-05-03; see NextBestAction.tsx scope note):
 *
 *   active booking -> pending rating -> unresolved cook chat action
 *   -> grocery approval -> festival tomorrow -> tomorrow not voted
 *   -> day complete -> TodayMealStatus (default)
 */

import { useMemo } from "react";
import {
  useChatStore,
  useCookAbsenceStore,
  useMealStore,
} from "./store";
import { getUpcomingFestivals } from "./festivals";
import { localIsoDate, localIsoDatePlus, useToday } from "./local-day";
import type { ActionItem, CookAbsenceEvent, MealPlan } from "./types";

// 2026-05-03 audit (FRONTEND-BACKEND-COORDINATION.md): Insta Cook is
// retired (per founder call: "No Insta cook for now"). The previous
// hooks here — `useActiveInstacookBooking`, `usePendingRatingForLastBooking`,
// `useRecentBookingsUnion` — read from the deleted `useInstacookStore`.
// Their callers in `NextBestAction.tsx` no longer render the booking
// heroes, so the hooks are unreferenced and removed entirely.

/**
 * Cook absence today — only meaningful for cook households. Returns the
 * matching absence event when one is active for today's date.
 *
 * 2026-05-03 audit: previously also checked "did we already book an
 * Insta Cook rescue?". With Insta Cook retired, that gate is gone —
 * any active absence surfaces.
 */
export function useCookAbsentToday(): CookAbsenceEvent | null {
  const absences = useCookAbsenceStore((s) => s.absences);
  // Use localIsoDate(useToday()) so the comparison rolls over at
  // local midnight + on app foreground without a manual refresh.
  const today = localIsoDate(useToday());

  return useMemo(() => {
    return absences.find((a) => a.date === today && !a.replacementBooked) ?? null;
  }, [absences, today]);
}

// 2026-05-10 audit: `usePendingGroceryApproval` was retired with the
// pre-Swiggy `<GroceryApprovalHero>` / `<CartApprovalSheet>` surfaces.
// Swiggy MCP is now the single grocery path; orders still hydrate into
// `useOrderStore` for the auto-rules screen but no longer trigger a hero.

/**
 * Tomorrow's meal status — true when tomorrow's MealPlan has no
 * selectedMeal set. Returns the first unplanned MealPlan so the hero can
 * deep-link directly into voting for it.
 *
 * Suppressed when a cook absence overlaps tomorrow: with the cook off,
 * the household isn't picking a dish for the cook to make — they're
 * picking a fallback (self cook / order / Insta Cook), and that
 * choice is surfaced by the wheel's centre-card cook-off variant
 * (and the day-sheet banner). Showing "Tomorrow's lunch isn't sorted"
 * on top of that reads as a contradiction.
 */
export function useTomorrowNeedsVote(): MealPlan | null {
  const tomorrowsPlan = useMealStore((s) => s.tomorrowsPlan);
  const absences = useCookAbsenceStore((s) => s.absences);
  // Tomorrow is computed off the live `useToday()` so it advances as
  // the local date does — without it, the value would freeze at
  // whatever "tomorrow" was when the hook first ran.
  const today = useToday();
  const tomorrowIso = localIsoDatePlus(1, today);

  return useMemo(() => {
    if (!tomorrowsPlan) return null;
    if (tomorrowsPlan.selectedMeal) return null;

    // Suppress when an absence overlaps tomorrow's date. Single-day
    // absences match by exact date; multi-day absences match when
    // tomorrow falls within [date, endDate].
    const cookOffTomorrow = absences.some((a) =>
      a.endDate
        ? a.date <= tomorrowIso && a.endDate >= tomorrowIso
        : a.date === tomorrowIso,
    );
    if (cookOffTomorrow) return null;

    return tomorrowsPlan;
  }, [tomorrowsPlan, absences, tomorrowIso]);
}

// (Removed 2026-05-03: `useIsNewUser` only fed the no-cook
//  `OrderDinnerHero` first-time copy variant. Bimi serves cook households
//  only — see NextBestAction.tsx.)

/**
 * Today's meal — used by the cook-household default hero. Returns the
 * winning/planned dish for the current day, or null.
 */
export function useTodaysMealPlan(): MealPlan | null {
  const todaysPlans = useMealStore((s) => s.todaysPlans);
  return useMemo(() => {
    if (!todaysPlans || todaysPlans.length === 0) return null;
    // Prefer a plan with a selectedMeal; otherwise the first plan.
    const planned = todaysPlans.find((p) => p.selectedMeal);
    return planned ?? todaysPlans[0];
  }, [todaysPlans]);
}

/**
 * Unresolved cook action items across all chat messages — typically
 * supply_request / meal_query / prep_failed callouts the cook posted that
 * still need a household decision. Per docs/CONTEXT-AWARE-UI.md row 6, an
 * unread cook message deserves an inline hero, not just a red dot.
 *
 * Returns null when there's nothing to surface (so consumers can `if (x)`
 * cheaply).
 */
export interface UnresolvedCookActions {
  /** First / most recent unresolved action item, used for hero copy. */
  primary: ActionItem;
  /** Total count of unresolved actions (>= 1). */
  count: number;
  /** Full array of user-facing unresolved actions, in original order.
   *  Lets the hero compute aggregate price / ETA when every item is a
   *  structured grocery, and lets the sheet render them directly. */
  actions: ActionItem[];
}

export function useUnresolvedCookActions(): UnresolvedCookActions | null {
  const messages = useChatStore((s) => s.messages);
  return useMemo(() => {
    const unresolved: ActionItem[] = [];
    for (const m of messages) {
      if (!m.isFromCook) continue;
      for (const a of m.actionItems) {
        if (a.resolved) continue;
        // `prep_note` items (e.g. "soak chole tonight") are cook-side
        // concerns — handled during the previous-meal prep window.
        // Hidden from the user-facing surface so the hero count and
        // the sheet's grocery list stay in lock-step.
        if (a.type === "prep_note") continue;
        unresolved.push(a);
      }
    }
    if (unresolved.length === 0) return null;
    return { primary: unresolved[0]!, count: unresolved.length, actions: unresolved };
  }, [messages]);
}

/**
 * Festival landing tomorrow per docs/CONTEXT-AWARE-UI.md row 8 — when a
 * festival is exactly one day away AND the household has a working cook,
 * surface a 'plan a festival meal' hero so the dietary override (pure
 * veg / sattvic / fasting) lands a day early. Returns the matching
 * Festival or null.
 */
export interface FestivalTomorrow {
  name: string;
  description: string;
  dietaryOverride?: "pure_veg" | "sattvic" | "no_onion_garlic" | "fasting";
}

export function useFestivalTomorrow(): FestivalTomorrow | null {
  // Re-derive `tomorrow` against `useToday()` so the festival hero
  // appears the moment local midnight rolls into the eve-of-festival
  // (rather than only on the next manual refresh).
  const today = useToday();
  return useMemo(() => {
    const tomorrowStr = localIsoDatePlus(1, today);
    const upcoming = getUpcomingFestivals(2);
    const match = upcoming.find((f) => {
      const endDate = f.endDate || f.date;
      return f.date <= tomorrowStr && endDate >= tomorrowStr;
    });
    return match ?? null;
  }, [today]);
}

/**
 * "Day complete" state per docs/CONTEXT-AWARE-UI.md row 2: every today's
 * meal that was planned has a rating AND every tomorrow's meal slot has
 * been finalized (selectedMeal set, isLocked=true OR no lockInAt window).
 *
 * Returns true only when there is genuinely nothing else for the user to
 * do today. Used by the home hero slot to show a single "you're set"
 * card instead of a degraded version of the busy state.
 */
export function useDayCompleteState(): boolean {
  const todaysPlans = useMealStore((s) => s.todaysPlans);
  const tomorrowsPlans = useMealStore((s) => s.tomorrowsPlans);
  return useMemo(() => {
    // Need at least one plan today AND at least one plan tomorrow before
    // we can call the day "complete" — the empty bachelor seed shouldn't
    // qualify.
    if (!todaysPlans || todaysPlans.length === 0) return false;
    if (!tomorrowsPlans || tomorrowsPlans.length === 0) return false;

    const allTodayRated = todaysPlans.every(
      (p) => !p.selectedMeal || typeof p.rating === "number",
    );
    if (!allTodayRated) return false;

    const allTomorrowFinalized = tomorrowsPlans.every(
      (p) => !!p.selectedMeal && (p.isLocked === true || !p.lockInAt),
    );
    return allTomorrowFinalized;
  }, [todaysPlans, tomorrowsPlans]);
}
