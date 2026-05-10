/**
 * useCookSettingsStore — persists the per-cook settings that previously lived
 * in component-level useState in (tabs)/settings.tsx (then settings/cook.tsx):
 *
 *   - cookHolidays  — { date, reason } entries (custom + festival-derived)
 *   - cookInstructions — standing reminders shown to the cook (text + recurrence)
 *   - brandPrefs are still stored on the Cook object directly via useHouseholdStore.setCook,
 *     so we don't duplicate them here.
 *
 * Persisted to AsyncStorage with the same defensive in-memory fallback used by
 * the rest of `lib/store.ts`. Uses Zustand's `persist` middleware.
 */

import { create, type StateCreator } from "zustand";
import { persist, createJSONStorage, type StateStorage } from "zustand/middleware";

// Same defensive AsyncStorage detection as lib/store.ts so this works in dev
// clients without the native module.
const memoryStore = new Map<string, string>();
const inMemoryStorage: StateStorage = {
  getItem: async (key) => (memoryStore.has(key) ? memoryStore.get(key)! : null),
  setItem: async (key, value) => {
    memoryStore.set(key, value);
  },
  removeItem: async (key) => {
    memoryStore.delete(key);
  },
};

// AsyncStorage native module is not linked in the current dev client
// (see QA-REPORT-2026-04-18.md Pass 3 backlog). Stay on in-memory until
// the dev client is rebuilt.
const resolvedStorage: StateStorage = inMemoryStorage;

export type Recurrence = "daily" | "weekdays" | "specific_days" | "one_time";

export interface CookHoliday {
  /** ISO date YYYY-MM-DD. */
  date: string;
  reason: string;
}

export interface CookInstruction {
  id: string;
  text: string;
  forPerson: string | null;
  recurrence: Recurrence;
  /** Specific weekdays (only when recurrence === "specific_days"). */
  days?: string[];
  time: string | null;
  status: "active" | "paused";
  createdAt: string;
}

interface CookSettingsState {
  holidays: CookHoliday[];
  instructions: CookInstruction[];

  addHoliday: (h: CookHoliday) => void;
  removeHoliday: (date: string) => void;

  addInstruction: (i: Omit<CookInstruction, "id" | "createdAt" | "status"> & { status?: "active" | "paused" }) => void;
  toggleInstruction: (id: string) => void;
  removeInstruction: (id: string) => void;

  reset: () => void;
}

const DEFAULT_INSTRUCTIONS: CookInstruction[] = [
  {
    id: "inst-default-1",
    text: "Soak almonds every night at 7 PM",
    forPerson: "Mayank",
    recurrence: "daily",
    time: "7:00 PM",
    status: "active",
    createdAt: new Date().toISOString(),
  },
  {
    id: "inst-default-2",
    text: "Clean kitchen after cooking",
    forPerson: null,
    recurrence: "daily",
    time: null,
    status: "active",
    createdAt: new Date().toISOString(),
  },
  {
    id: "inst-default-3",
    text: "Make ginger chai every morning",
    forPerson: null,
    recurrence: "weekdays",
    time: "8:00 AM",
    status: "active",
    createdAt: new Date().toISOString(),
  },
];

const initializer: StateCreator<CookSettingsState> = (set) => ({
  holidays: [],
  instructions: DEFAULT_INSTRUCTIONS,

  addHoliday: (h) =>
    set((s) => ({
      // Dedupe by date so toggling a festival twice doesn't add duplicates.
      holidays: [...s.holidays.filter((existing) => existing.date !== h.date), h],
    })),

  removeHoliday: (date) =>
    set((s) => ({ holidays: s.holidays.filter((h) => h.date !== date) })),

  addInstruction: ({ text, forPerson, recurrence, days, time, status = "active" }) =>
    set((s) => ({
      instructions: [
        ...s.instructions,
        {
          id: `inst-${Date.now()}`,
          text,
          forPerson,
          recurrence,
          days,
          time,
          status,
          createdAt: new Date().toISOString(),
        },
      ],
    })),

  toggleInstruction: (id) =>
    set((s) => ({
      instructions: s.instructions.map((i) =>
        i.id === id ? { ...i, status: i.status === "active" ? "paused" : "active" } : i,
      ),
    })),

  removeInstruction: (id) =>
    set((s) => ({ instructions: s.instructions.filter((i) => i.id !== id) })),

  reset: () => set({ holidays: [], instructions: DEFAULT_INSTRUCTIONS }),
});

export const useCookSettingsStore = create<CookSettingsState>()(
  persist(initializer, {
    name: "bimi.cook-settings",
    storage: createJSONStorage(() => resolvedStorage),
    version: 1,
  }),
);
