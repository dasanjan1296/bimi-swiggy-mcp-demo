/**
 * useKitchenCapacityStore — physical-kitchen + meal-cadence constraints
 * captured at onboarding, consumed by the suggestion + cook-brief
 * pipelines.
 *
 *   • `burners` (1–4) caps how many simultaneous dishes the planner can
 *     ask the cook to pull off in one slot. The suggestion engine reads
 *     this when it considers multi-dish meals (rice + dal + sabzi + roti
 *     is a 4-burner plan; a 1-burner kitchen gets a one-pot suggestion).
 *
 *   • `orchestratedMeals` is the multi-select of which slots the
 *     household actually wants Bimi to manage (a single working person
 *     usually only cares about dinner; a family wants all three). The
 *     home dashboard hides bands the household didn't opt into.
 *
 *   • `mealTimes` is the household's default eat-by clock per slot. The
 *     cook-brief uses this to phrase "ready by 8 PM" in the WhatsApp
 *     mirror; the home time bands snap to it.
 *
 * Defaults match what an Indian middle-class household actually has
 * (2-burner stove + dinner-only orchestration is the most common cohort
 * we observed in the cook-simulation report — see docs/COOK-SIMULATION-
 * REPORT.md). They're picked so a user who taps "Next" without changing
 * anything still ends up with a coherent system.
 */

import { create } from "zustand";

export type BurnerCount = 1 | 2 | 3 | 4;

export type OrchestratedMeal = "breakfast" | "lunch" | "dinner";

export interface MealTimes {
  /** HH:mm 24-hour. */
  breakfast: string;
  lunch: string;
  dinner: string;
}

interface KitchenCapacityState {
  burners: BurnerCount;
  orchestratedMeals: OrchestratedMeal[];
  mealTimes: MealTimes;

  setBurners: (n: BurnerCount) => void;
  toggleMeal: (m: OrchestratedMeal) => void;
  setOrchestratedMeals: (m: OrchestratedMeal[]) => void;
  setMealTime: (slot: OrchestratedMeal, hhmm: string) => void;
  reset: () => void;

  /** Max simultaneous dishes the planner can request in one slot. */
  maxSimultaneousDishes: () => number;
  /** Is `slot` part of what Bimi is allowed to suggest for? */
  isOrchestrated: (slot: OrchestratedMeal) => boolean;
}

const DEFAULT_MEAL_TIMES: MealTimes = {
  breakfast: "08:30",
  lunch: "13:30",
  dinner: "20:00",
};

const DEFAULT_BURNERS: BurnerCount = 2;
const DEFAULT_ORCHESTRATED: OrchestratedMeal[] = ["dinner"];

export const useKitchenCapacityStore = create<KitchenCapacityState>((set, get) => ({
  burners: DEFAULT_BURNERS,
  orchestratedMeals: DEFAULT_ORCHESTRATED,
  mealTimes: DEFAULT_MEAL_TIMES,

  setBurners: (burners) => set({ burners }),
  toggleMeal: (m) =>
    set((state) => {
      const has = state.orchestratedMeals.includes(m);
      // Refuse to leave the user with zero orchestrated slots — that
      // would make the entire app silent. The toggle is a no-op when
      // it'd remove the last selected slot.
      if (has && state.orchestratedMeals.length === 1) return state;
      return {
        orchestratedMeals: has
          ? state.orchestratedMeals.filter((x) => x !== m)
          : [...state.orchestratedMeals, m],
      };
    }),
  setOrchestratedMeals: (orchestratedMeals) =>
    set({ orchestratedMeals: orchestratedMeals.length === 0 ? DEFAULT_ORCHESTRATED : orchestratedMeals }),
  setMealTime: (slot, hhmm) =>
    set((state) => ({ mealTimes: { ...state.mealTimes, [slot]: hhmm } })),
  reset: () =>
    set({ burners: DEFAULT_BURNERS, orchestratedMeals: DEFAULT_ORCHESTRATED, mealTimes: DEFAULT_MEAL_TIMES }),

  maxSimultaneousDishes: () => {
    // 1 burner = 1 dish; 2 = 2; 3+ = 3 (more than 3 active dishes is
    // rare in home cooking even with 4 burners — the bottleneck is the
    // cook's attention, not the heat source).
    const b = get().burners;
    return b === 1 ? 1 : b === 2 ? 2 : 3;
  },
  isOrchestrated: (slot) => get().orchestratedMeals.includes(slot),
}));
