/**
 * `useTodayStore` — module-level Zustand store holding the
 * local-midnight `today` Date. Components read it via `useToday()`
 * (in `local-day.ts`); imperative callers (pull-to-refresh,
 * AppState 'active' at the root layout) hit `refreshToday()` to
 * recompute and broadcast.
 *
 * Why a module store instead of `useState` + per-component
 * AppState listener: an earlier reactive version subscribed inside
 * each consuming component, which raced with the home tab's
 * ScrollView first-layout pass on iOS Simulator (content jammed
 * at the bottom of the viewport on cold launch). A module store
 * has no per-component mount side effects — components just read
 * a value — so the layout race doesn't occur.
 */
import { create } from "zustand";

function startOfLocalDayNow(): Date {
  const x = new Date();
  x.setHours(0, 0, 0, 0);
  return x;
}

interface TodayStore {
  today: Date;
  refresh: () => void;
}

export const useTodayStore = create<TodayStore>((set) => ({
  today: startOfLocalDayNow(),
  refresh: () =>
    set((s) => {
      const next = startOfLocalDayNow();
      // Same calendar day → keep the existing reference so memos
      // and effects keyed on `today` don't re-fire.
      return s.today.getTime() === next.getTime() ? s : { today: next };
    }),
}));

export function refreshToday(): void {
  useTodayStore.getState().refresh();
}
