// Default arrival/serve times per meal — single source of truth.
// Previously duplicated in voting.tsx and InlineBookingCard.tsx.
import type { MealType } from "./types";

export const MEAL_DEFAULT_TIMES: Record<MealType, string> = {
  breakfast: "8:00 AM",
  lunch: "11:00 AM",
  dinner: "6:00 PM",
  snack: "4:00 PM",
};

/** Safe lookup with a sane fallback (lunch). */
export function defaultMealTime(mealType: string | undefined): string {
  if (mealType && mealType in MEAL_DEFAULT_TIMES) {
    return MEAL_DEFAULT_TIMES[mealType as MealType];
  }
  return MEAL_DEFAULT_TIMES.lunch;
}
