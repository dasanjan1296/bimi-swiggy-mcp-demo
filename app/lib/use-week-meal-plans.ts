/**
 * useWeekMealPlans — returns a 7-day meal plan window starting today,
 * one entry per day, each containing the breakfast / lunch / dinner
 * MealPlan rows.
 *
 * Wires three sources together:
 *   - D+0 (today)    → useMealStore.todaysPlans
 *   - D+1 (tomorrow) → useMealStore.tomorrowsPlans
 *   - D+2..D+6       → synthesised on the fly, hydrated with any votes
 *                      that exist in useMealStore.futureWeekPlans
 *
 * The synthesised future-day plans are seeded with the household's
 * current `suggestions[mealType]` so the inline picker in
 * `<DayVotingBody>` always has 3 dishes to show.
 *
 * Used by `<HomeCalendar>` (the home agenda) and `<DayDetailSheet>`
 * (the day-tap modal that composes `<DayVotingBody>`).
 */

import { useMemo } from "react";
import { useMealStore, useCookAbsenceStore, useHouseholdStore } from "./store";
import { localIsoDate, useToday } from "./local-day";
import type {
  Cook,
  CookAbsenceEvent,
  CookAbsenceFallback,
  MealPlan,
  MealType,
} from "./types";

/**
 * Cook-off summary for a single day. Built from `useCookAbsenceStore`
 * by `buildCookOff()` below. When the matching absence has no
 * `affectedMeals` field set, we treat it as a full-day absence.
 */
export interface DayCookOff {
  /** The originating absence record (so callers can act on it directly). */
  absence: CookAbsenceEvent;
  /** Meals affected on this day. Always non-empty. */
  affectedMeals: MealType[];
  /**
   * True when ALL of the day's three meal slots are off (i.e. the user
   * is functionally without a cook for the whole day). False if only
   * a subset (e.g. lunch only). Computed from `affectedMeals`.
   */
  isFullDay: boolean;
  /** Whichever fallback the user already chose, or null if undecided. */
  fallbackChosen: CookAbsenceFallback | null;
}

export interface WeekDay {
  /** ISO date YYYY-MM-DD. */
  date: string;
  /** Day-of-week label, e.g. "Sun", "Mon". */
  dayShort: string;
  /** Full label, e.g. "Sunday, May 4". */
  dayLong: string;
  /** Index 0..6, where 0 is today. */
  offset: number;
  /** The three meal plans for this day, in canonical order. */
  plans: MealPlan[];
  /** Counts of finalised + total slots. */
  voted: number;
  total: number;
  /** Cook-off context for this day, or null if no absence overlaps. */
  cookOff: DayCookOff | null;
}

const MEAL_TYPES: MealType[] = ["breakfast", "lunch", "dinner"];

function shortLabel(d: Date): string {
  return d.toLocaleDateString("en-IN", { weekday: "short" });
}

function longLabel(d: Date): string {
  return d.toLocaleDateString("en-IN", { weekday: "long", month: "short", day: "numeric" });
}

export function useWeekMealPlans(): WeekDay[] {
  const todaysPlans = useMealStore((s) => s.todaysPlans);
  const tomorrowsPlans = useMealStore((s) => s.tomorrowsPlans);
  const futureWeekPlans = useMealStore((s) => s.futureWeekPlans);
  const suggestions = useMealStore((s) => s.suggestions);
  const absences = useCookAbsenceStore((s) => s.absences);
  const cook = useHouseholdStore((s) => s.household?.cooks?.[0]) ?? null;

  // `useToday()` re-runs this hook at local midnight + on app
  // foreground, so the wheel auto-rolls over: the sector that was
  // "Today" yesterday silently becomes the trailing day, and the
  // new today appears at 12 o'clock without a manual refresh.
  const today = useToday();

  return useMemo(() => {
    const todayIso = localIsoDate(today);
    const days: WeekDay[] = [];
    for (let offset = 0; offset < 7; offset++) {
      const d = new Date(today);
      d.setDate(today.getDate() + offset);
      const date = localIsoDate(d);

      let plans: MealPlan[];
      if (offset === 0) {
        plans = MEAL_TYPES.map((mt) => findOrSynth(todaysPlans, mt, date, suggestions));
      } else if (offset === 1) {
        plans = MEAL_TYPES.map((mt) => findOrSynth(tomorrowsPlans, mt, date, suggestions));
      } else {
        // D+2..D+6: read the futureWeekPlans map first; synthesise the rest.
        plans = MEAL_TYPES.map((mt) => {
          const key = `${date}-${mt}`;
          if (futureWeekPlans[key]) return futureWeekPlans[key];
          return synthesise(date, mt, suggestions);
        });
      }

      const voted = plans.filter((p) => !!p.selectedMeal).length;
      days.push({
        date,
        dayShort: shortLabel(d),
        dayLong: longLabel(d),
        offset,
        plans,
        voted,
        total: plans.length,
        cookOff: buildCookOff(date, absences, cook, todayIso),
      });
    }

    return days;
  }, [today, todaysPlans, tomorrowsPlans, futureWeekPlans, suggestions, absences, cook]);
}

/**
 * Resolve the cook-off context for a single date. Two sources:
 *
 *   1. **Ad-hoc absences** (`useCookAbsenceStore`) — manually entered
 *      time-off; honoured for ANY date (past + present + future).
 *      Handles single-date, multi-day, and per-meal shapes.
 *
 *   2. **Recurring weekly schedule** (`cook.slots[].workingDays`) —
 *      a day not in any working-days list is the cook's regular day
 *      off (typically Sunday). Honoured only for today + future, since
 *      past Sundays might have been worked overtime; the meal-history
 *      record is the source of truth there.
 *
 * If multiple ad-hoc absences overlap, the union of affected meals is
 * taken and the first absence's metadata is surfaced. Weekly-off
 * synthesises an absence whose id starts with `weekly:` so callers
 * (CookOffBanner) can detect and materialise it on first user action.
 */
export function buildCookOff(
  date: string,
  absences: CookAbsenceEvent[],
  cook?: Cook | null,
  todayIso?: string,
): DayCookOff | null {
  // ── 1. Ad-hoc absences ──────────────────────────────────────────
  const overlapping = absences.filter((a) =>
    a.endDate ? a.date <= date && a.endDate >= date : a.date === date,
  );
  if (overlapping.length > 0) {
    const meals = new Set<MealType>();
    for (const a of overlapping) {
      if (a.affectedMeals && a.affectedMeals.length > 0) {
        a.affectedMeals.forEach((m) => meals.add(m));
      } else {
        MEAL_TYPES.forEach((m) => meals.add(m));
      }
    }
    const affectedMeals = MEAL_TYPES.filter((m) => meals.has(m));
    const isFullDay = MEAL_TYPES.every((m) => meals.has(m));
    return {
      absence: overlapping[0],
      affectedMeals,
      isFullDay,
      fallbackChosen: overlapping[0].fallbackChosen ?? null,
    };
  }

  // ── 2. Recurring weekly off (today + future only) ───────────────
  if (!cook || !cook.slots || cook.slots.length === 0) return null;
  if (todayIso && date < todayIso) return null;

  const dayName = isoDateWeekdayName(date);
  if (!dayName) return null;
  const isWorkingDay = cook.slots.some((s) =>
    s.workingDays?.includes(dayName),
  );
  if (isWorkingDay) return null;

  return {
    absence: {
      id: `weekly:${cook.id}:${date}`,
      cookName: cook.name,
      date,
      replacementBooked: false,
    },
    affectedMeals: [...MEAL_TYPES],
    isFullDay: true,
    fallbackChosen: null,
  };
}

/**
 * "Sun" / "Mon" / … from a yyyy-mm-dd string. Local-noon parsing
 * dodges timezone DST drift — `new Date("yyyy-mm-dd")` interprets the
 * string as UTC midnight, which can flip the weekday in some zones
 * (the cause of the iOS-vs-Android Sunday-detection drift the user
 * reported).
 */
const WEEKDAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"] as const;
function isoDateWeekdayName(iso: string): string | null {
  const [y, m, d] = iso.split("-").map((p) => parseInt(p, 10));
  if (!y || !m || !d) return null;
  return WEEKDAY_NAMES[new Date(y, m - 1, d, 12, 0, 0).getDay()] ?? null;
}

function findOrSynth(
  store: MealPlan[],
  mealType: MealType,
  date: string,
  suggestions: Record<string, any[]>,
): MealPlan {
  const existing = store.find((p) => p.mealType === mealType);
  return existing ?? synthesise(date, mealType, suggestions);
}

function synthesise(
  date: string,
  mealType: MealType,
  suggestions: Record<string, any[]>,
): MealPlan {
  return {
    id: `fwp-${date}-${mealType}`,
    date,
    mealType,
    selectedMeal: undefined,
    dishes: [],
    status: "planned",
    votes: [],
    suggestions: suggestions[mealType] || [],
  };
}
