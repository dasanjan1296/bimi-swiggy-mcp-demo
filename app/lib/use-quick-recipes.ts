/**
 * useQuickRecipes — react-query hook for the home-screen "Self cook
 * ideas" sheet. Hits `GET /recipe-archive/quick` with optional course
 * + diet filters, falls back to the bundled seed in
 * `lib/quick-recipes.ts` when the backend is unreachable, demo mode
 * is on, or the response is empty.
 *
 * Usage:
 *   const { data: recipes, isLoading } = useQuickRecipes({
 *     mealType: cookOff.isFullDay ? undefined : cookOff.affectedMeals[0],
 *     dietType: household?.dietType,
 *   });
 *
 * The hook always resolves to an array; never null. That keeps the
 * sheet rendering straightforward — no separate "empty" state needed.
 */

import { useQuery } from "@tanstack/react-query";
import { client } from "./api";
import { isDemoMode } from "./auth-flags";
import { QUICK_RECIPES, type QuickRecipe } from "./quick-recipes";
import type { MealType } from "./types";

export interface UseQuickRecipesOpts {
  /**
   * Restrict to a single course (breakfast / lunch / dinner). Used by
   * the home modal when the cook-off is partial-day, so the user sees
   * dinner ideas if only dinner is affected. Undefined → all courses.
   */
  mealType?: MealType;
  /** Diet filter, mirroring the household preference. */
  dietType?: "vegetarian" | "non_vegetarian" | "vegan" | "egg_only";
  /** Hard cap on total prep+cook time. Defaults to 30 min. */
  maxTimeMins?: number;
}

/**
 * Backend response shape — keys are snake_case to match Pydantic.
 */
interface BackendQuickRecipe {
  id: string;
  slug: string;
  title: string;
  description: string | null;
  image_url: string | null;
  youtube_url: string | null;
  total_time_mins: number;
  difficulty: "easy" | "medium" | "hard";
  course: MealType;
  diet_type: "vegetarian" | "non_vegetarian" | "vegan" | "egg_only";
  tags: string[] | null;
}

function fromBackend(r: BackendQuickRecipe): QuickRecipe {
  return {
    id: r.id,
    slug: r.slug,
    title: r.title,
    description: r.description ?? undefined,
    imageUrl: r.image_url ?? undefined,
    youtubeUrl: r.youtube_url ?? undefined,
    totalTimeMins: r.total_time_mins,
    difficulty: r.difficulty,
    course: r.course,
    dietType: r.diet_type,
    tags: r.tags ?? undefined,
  };
}

/**
 * Apply the same filters the backend would, locally — so the seed
 * fallback respects `mealType` / `dietType` / `maxTimeMins` exactly
 * the same way as the live data.
 */
function filterLocal(opts: UseQuickRecipesOpts): QuickRecipe[] {
  const { mealType, dietType, maxTimeMins = 30 } = opts;
  return QUICK_RECIPES.filter((r) => {
    if (r.totalTimeMins > maxTimeMins) return false;
    if (mealType && r.course !== mealType) return false;
    if (dietType && r.dietType !== dietType) return false;
    return true;
  }).sort((a, b) => a.totalTimeMins - b.totalTimeMins);
}

export function useQuickRecipes(opts: UseQuickRecipesOpts = {}) {
  return useQuery({
    queryKey: [
      "quick-recipes",
      opts.mealType ?? "all",
      opts.dietType ?? "any",
      opts.maxTimeMins ?? 30,
    ],
    queryFn: async (): Promise<QuickRecipe[]> => {
      // Demo mode: skip the network round-trip entirely and serve the
      // bundled seed. Keeps the sheet snappy on dev devices and in
      // App Store reviewer demos with no backend reachable.
      if (isDemoMode()) return filterLocal(opts);

      try {
        const params: Record<string, string | number> = {};
        if (opts.mealType) params.course = opts.mealType;
        if (opts.dietType) params.diet_type = opts.dietType;
        if (opts.maxTimeMins != null) params.max_time_mins = opts.maxTimeMins;

        const { data } = await client.get<BackendQuickRecipe[]>(
          "/recipe-archive/quick",
          { params },
        );

        const mapped = (data ?? []).map(fromBackend);
        // The backend may temporarily have zero seeded rows on a fresh
        // DB before migration 049 has run. Fall through to the local
        // seed so the modal is never empty for that reason.
        return mapped.length > 0 ? mapped : filterLocal(opts);
      } catch {
        // Network failure / 5xx — graceful fallback so the sheet still
        // works offline or against a cold backend. The user never
        // sees a "couldn't load" state for this surface; the seed
        // is honest enough to ship.
        return filterLocal(opts);
      }
    },
    staleTime: 5 * 60 * 1000,
  });
}
