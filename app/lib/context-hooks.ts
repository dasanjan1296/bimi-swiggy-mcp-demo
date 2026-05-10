/**
 * Context-aware UI hooks per `bimi/docs/CONTEXT-AWARE-UI.md`.
 *
 * Each hook answers exactly one question about the current household state.
 * Read-sites then say what state they are guarding for, e.g.
 *
 *   {usePicksAreActionable() && <PickRows />}
 *
 * If you find yourself writing a long inline conditional in a screen, that's
 * a smell — pull it into a named hook here so the call site reads itself.
 */

import { useMemo } from "react";

import { useFeatureFlags } from "./feature-flags";
import { localIsoDate, useToday } from "./local-day";
import { useCookAbsenceStore, useHouseholdStore } from "./store";

const DAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"] as const;

function tomorrowParts(today: Date): { iso: string; dayIndex: number } {
  const d = new Date(today);
  d.setDate(d.getDate() + 1);
  return {
    iso: localIsoDate(d),
    dayIndex: d.getDay(),
  };
}

function isAbsenceCovering(
  absences: Array<{ date: string; endDate?: string }>,
  dateStr: string,
): boolean {
  return absences.some((a) =>
    a.endDate ? a.date <= dateStr && a.endDate >= dateStr : a.date === dateStr,
  );
}

/**
 * True when the household's cook is off tomorrow — either by a registered
 * absence (covering tomorrow) or by their weekly schedule (no `workingDays`
 * entry for tomorrow's weekday).
 *
 * Empty `slots` array on a household with `hasCook` is treated as "Sunday
 * off only" for back-compat with legacy bachelor seeds.
 */
export function useIsCookOffTomorrow(): boolean {
  const household = useHouseholdStore((s) => s.household);
  const absences = useCookAbsenceStore((s) => s.absences);
  // Subscribe to local-day changes so this hook recomputes when
  // midnight rolls in (and "tomorrow" becomes a different actual date).
  const today = useToday();
  return useMemo(() => {
    const { iso, dayIndex } = tomorrowParts(today);
    if (isAbsenceCovering(absences, iso)) return true;

    const hasCook = household?.hasCook ?? false;
    const cook = household?.cooks?.[0];
    if (!hasCook || !cook) return false;

    const slots = cook.slots ?? [];
    if (slots.length === 0) return dayIndex === 0; // legacy bachelor seed
    return !slots.some((s) => s.workingDays?.includes(DAY_NAMES[dayIndex]!));
  }, [household, absences, today]);
}

/**
 * True when we should render the cook-off teaser card on the Tomorrow band.
 *
 * Two conditions must hold:
 *   1. The cook is off tomorrow (no one will execute a brief).
 *   2. InstaCook is currently gated off — otherwise the regular booking
 *      surface is the right thing to show, not a "coming soon" teaser.
 */
export function useCookOffTeaserVisible(): boolean {
  const isCookOffTomorrow = useIsCookOffTomorrow();
  const flags = useFeatureFlags();
  return isCookOffTomorrow && !flags.showInstacook;
}

/**
 * True when the per-meal Pick rows on the home screen are actionable.
 *
 * They are NOT actionable while the cook-off teaser is taking over the
 * Tomorrow band — picking a meal in that state would feed it to a cook
 * who isn't coming.
 */
export function usePicksAreActionable(): boolean {
  return !useCookOffTeaserVisible();
}
