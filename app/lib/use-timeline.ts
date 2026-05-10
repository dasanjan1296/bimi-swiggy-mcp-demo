/**
 * IC-P2-05: lightweight ETA calculator for the home "Cooking now" pill.
 *
 * Today the data layer doesn't yet stream a real `expected_ready_at` per
 * meal plan, so we infer the ETA from the meal's default serving time:
 *   ready_in_min = default_meal_time(mealType) - now
 * with a safety floor of 5 minutes (so the pill never says "ready in 0").
 *
 * When the backend wires `prep_timeline` polling end-to-end (see
 * `bimi/backend/app/routers/pilot.py::prep_timeline`), this hook is the
 * single place that needs to switch from inferred to live data.
 */

import { useMemo } from "react";
import { defaultMealTime } from "./meal-times";
import type { MealType } from "./types";

function _parseMealTimeToMinutes(raw: string): number | null {
  const match = raw.match(/^(\d{1,2}):(\d{2})\s*(AM|PM)$/i);
  if (!match) return null;
  let hours = parseInt(match[1], 10);
  const minutes = parseInt(match[2], 10);
  const ampm = match[3].toUpperCase();
  if (ampm === "PM" && hours < 12) hours += 12;
  if (ampm === "AM" && hours === 12) hours = 0;
  return hours * 60 + minutes;
}

export interface MealEta {
  /** Inferred minutes until the meal is ready. Floor of 5. */
  readyInMin: number;
  /** Human label like "ready in ~12 min" or "ready any moment". */
  label: string;
}

export function useMealEta(mealType: MealType | undefined): MealEta {
  return useMemo(() => {
    if (!mealType) {
      return { readyInMin: 5, label: "ready any moment" };
    }
    const targetMin = _parseMealTimeToMinutes(defaultMealTime(mealType));
    if (targetMin == null) return { readyInMin: 5, label: "ready any moment" };

    const now = new Date();
    const nowMin = now.getHours() * 60 + now.getMinutes();
    const diff = targetMin - nowMin;
    const readyInMin = Math.max(5, diff);

    if (readyInMin <= 5) return { readyInMin: 5, label: "ready any moment" };
    if (readyInMin < 60) return { readyInMin, label: `ready in ~${readyInMin} min` };
    const h = Math.floor(readyInMin / 60);
    const m = readyInMin % 60;
    const label = m === 0 ? `ready in ~${h} hr` : `ready in ~${h} hr ${m} min`;
    return { readyInMin, label };
  }, [mealType]);
}
