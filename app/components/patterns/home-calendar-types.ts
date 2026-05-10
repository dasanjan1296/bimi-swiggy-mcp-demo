/**
 * Shared view-model types for the home calendar agenda.
 *
 * `<HomeCalendar>` builds an array of `CalendarDay` objects from the
 * three sources of truth (`useWeekMealPlans` for D+0..D+6,
 * `useMealHistory` for past, and `useCookAbsenceStore` for absences)
 * and hands them to `<DayCardRow>` for render and `<DayDetailSheet>`
 * for the tap-through modal. Co-locating the shape keeps the row +
 * sheet + builder in lockstep.
 */

import type {
  Cook,
  CookAbsenceEvent,
  MealHistoryEntry,
  MealType,
} from "@/lib/types";
import {
  buildCookOff,
  type DayCookOff,
  type WeekDay,
} from "@/lib/use-week-meal-plans";

/**
 * Where this day sits in time relative to "now".
 *
 * - past         — yesterday or earlier; data comes from MealHistoryEntry[]
 * - today        — anchor; data comes from WeekDay (offset 0)
 * - tomorrow     — D+1; data comes from WeekDay (offset 1)
 * - near-future  — D+2..D+6; data comes from WeekDay
 * - far-future   — D+7..D+13; no plans yet, render as placeholder
 */
export type DayState =
  | "past"
  | "today"
  | "tomorrow"
  | "near-future"
  | "far-future";

export interface CalendarDay {
  /** Local ISO yyyy-mm-dd. Used as React key + sheet identifier. */
  date: string;
  state: DayState;
  /** Display labels — precomputed once at build time. */
  dayLong: string;        // "Saturday · May 9"
  dayOfMonth: number;     // 9
  weekdayShort: string;   // "Sat"
  /** Optional eyebrow ("Yesterday", "2 days ago") for past cards. */
  relativeLabel?: string;
  /** Source for state in [today, tomorrow, near-future]. */
  weekDay?: WeekDay;
  /** Source for state = past. Always set when state is past, may be []. */
  pastEntries?: MealHistoryEntry[];
  /** Cook absence overlapping this date (any state). Null if none. */
  cookOff: DayCookOff | null;
  /** Whether the card has any meal data to surface. */
  hasData: boolean;
}

export interface MealPreview {
  mealType: MealType;
  selectedMeal: string | null;
  /**
   * Per-meal preview status. Ordered by precedence (cook-off variants
   * supersede lifecycle states because the cook isn't cooking either way):
   *
   *   Cook-off branch (set when an absence overlaps this meal):
   *     - "off"        — cook off, no fallback chosen yet
   *     - "self-cook"  — cook off, household will self-cook
   *
   *   Past-day branch:
   *     - "rated"      — past meal that received a household rating
   *     - "skipped"    — past day, nothing recorded
   *
   *   Future / today / tomorrow lifecycle (mirrors `classifyMealState`
   *   from `lib/meal-state.ts`):
   *     - "open"       — no votes, no winner; show no chip
   *     - "voting"     — votes exist, threshold not met (no winner yet);
   *                      preview shows the "X / N" tally
   *     - "tentative"  — winner picked but soft-lock window still active;
   *                      user can still switch
   *     - "locked"     — final, cook briefed (or future-day pre-vote
   *                      since those skip the soft-lock cycle)
   *
   * Legacy alias:
   *     - "voted"      — old name for "locked", kept for any older callers
   *                      that haven't migrated yet
   *     - "pending"    — old name for "open"
   */
  status:
    | "open"
    | "voting"
    | "tentative"
    | "locked"
    | "rated"
    | "skipped"
    | "off"
    | "self-cook"
    | "voted"
    | "pending";
  /**
   * Vote tally for the "voting" state. Carries `castVotes` (the count
   * of household members who've voted) and `totalVoters` (active
   * members) so the cell can render "1 / 3". Only populated when
   * `status === "voting"`; ignored otherwise.
   */
  voteTally?: { castVotes: number; totalVoters: number };
}

/**
 * Re-export of the canonical `buildCookOff` (in
 * `lib/use-week-meal-plans.ts`) under the historical `buildDayCookOff`
 * name used by `<HomeCalendar>`. Single source of truth for the
 * absence + weekly-schedule classification — keeps today/tomorrow
 * (driven by useWeekMealPlans) and past/far-future (driven by
 * HomeCalendar's per-day resolver) in lock-step on cook-off rendering,
 * including the recurring weekly day-off (e.g. Sunday).
 */
export const buildDayCookOff = buildCookOff;
// Silence unused-import warnings for callers that destructure these
// types alongside `buildDayCookOff`.
export type { Cook, CookAbsenceEvent, MealType };
