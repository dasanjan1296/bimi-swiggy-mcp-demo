/**
 * Local-day utilities — the canonical "what day is it RIGHT NOW on
 * this device" helpers.
 *
 * `new Date().toISOString().slice(0, 10)` returns the UTC date, not
 * the local one. At 8 AM IST on Monday May 4, this evaluates to
 * "2026-05-03" (because IST is UTC+5:30, so local Monday 00:00 is
 * UTC Sunday 18:30). Every place that used it as "today's date
 * string" was wrong by up to one day depending on the device's
 * timezone offset and the wall-clock hour. Use `localIsoDate()`
 * instead — it pulls year/month/day from local Date methods
 * (`getFullYear`, `getMonth`, `getDate`) and never crosses UTC.
 *
 * `useToday()` is the hook companion — returns the local-midnight
 * Date for use in render. See its doc-comment for the reactivity
 * trade-off (currently captured-once-at-mount).
 *
 * Display formatting with an explicit IST timezone still happens via
 * `lib/time.ts` for user-facing timestamps + relative-time copy —
 * that's a different concern from "what day is it on this device".
 */

import { useTodayStore } from "./today-store";

/**
 * LOCAL-time YYYY-MM-DD. Use everywhere a date is keyed against the
 * day the user is living through (today's plan, history calendar,
 * absence start date, festival overlap, leftover meal date, etc).
 *
 * Replaces `new Date().toISOString().slice(0, 10)` and
 * `.split("T")[0]` — both of which return the UTC date and quietly
 * skew by up to a full day depending on the user's offset.
 */
export function localIsoDate(d: Date = new Date()): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** LOCAL-time YYYY-MM-DD for `n` days from `from` (default today). */
export function localIsoDatePlus(n: number, from: Date = new Date()): string {
  const d = new Date(from);
  d.setDate(d.getDate() + n);
  return localIsoDate(d);
}

/** Local-midnight Date for the day `d` belongs to. */
export function startOfLocalDay(d: Date = new Date()): Date {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  return x;
}

/**
 * Returns today's local-midnight Date. Reactive — subscribes to
 * `useTodayStore` so all consumers re-render together when the
 * day rolls over (via pull-to-refresh on the home tab, or AppState
 * 'active' wired in the root `_layout.tsx`).
 *
 * Implementation note: the store is module-level, so subscribing
 * here is a pure value-read with no per-component side effects.
 * An earlier reactive design mounted `AppState` + `setTimeout`
 * listeners INSIDE each consuming component, which raced with the
 * home tab's ScrollView first-layout pass on iOS Simulator
 * (content jammed at the bottom of the viewport on cold launch).
 * Centralising the side effect in one place dodges that race.
 *
 * The Date reference is stable across renders as long as the day
 * hasn't rolled over (the store's `refresh` action keeps the
 * existing reference when the calendar day is unchanged), so
 * memos and effects keyed on `today` don't re-fire spuriously.
 */
export function useToday(): Date {
  return useTodayStore((s) => s.today);
}

/**
 * Convenience: the local YYYY-MM-DD string for "now", reactive to
 * midnight + foreground (via `useToday`). Most callers want this; a
 * few (e.g. the wheel) want the Date object so they can do offset
 * arithmetic and use that.
 */
export function useTodayIso(): string {
  return localIsoDate(useToday());
}
