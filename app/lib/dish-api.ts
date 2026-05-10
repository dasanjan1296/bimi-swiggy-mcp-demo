/**
 * Bimi Recipes (formerly Dish Catalog) API client.
 *
 * 2026-05-03 audit (FRONTEND-BACKEND-COORDINATION.md): per founder calls:
 *   - "Dish Catalog and Recipe Archive are sort of the same"
 *     → `fetchDishCatalog` and `fetchDish` now hit `/recipe-archive`
 *     instead of the never-implemented `/dishes` routes.
 *   - "No Insta Cook for now"
 *     → all `/instacook/*` calls (createDishBooking, absence-rescue
 *     prefill / confirm) are removed.
 *   - "Delete UI" for Bimi Gold
 *     → membership / subscribe / cancel / savings / credits removed.
 *
 * The `Dish` shape is kept compatible with the previous catalog so the
 * existing UI (DishGridCard, DishHero, etc.) renders without churn.
 * The recipe-archive backend returns a richer payload — fields not yet
 * mapped here can be added incrementally.
 */

import { client } from "./api";

// ─── Types ────────────────────────────────────────────────────────────────

export type Dish = {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  cuisine: string;
  meal_types: string[];
  is_veg: boolean;
  base_time_minutes: number;
  skill_tier: number;
  required_ingredients: string[];
  customization_options: Record<string, unknown>;
  image_url: string | null;
  display_order: number;
  // Optional ingredient list — populated from recipe-archive when available.
  ingredients?: Array<{ name: string; quantity?: string; unit?: string }>;
};

// ─── Recipe archive (replaces /dishes) ────────────────────────────────────
//
// Backend response shape (verified against
// `bimi/backend/app/routers/recipe_archive.py::RecipeSummaryOut`):
//
//   { id, name, name_hindi?, slug, description?, cuisine, course,
//     diet_type, prep_time_mins, cook_time_mins, total_time_mins,
//     default_servings, difficulty, tags?, advance_prep_note?,
//     pairs_well_with?, image_url? }
//
// Detail adds `ingredients[]` (typed: name, quantity?, unit?, ...).
//
// The frontend `Dish` shape predates Recipe Archive — the mapper below
// translates field names + derives missing fields (e.g. `is_veg` from
// `diet_type`, `meal_types` from `course`).

type RecipeArchiveSummary = {
  id: string;
  slug: string;
  name: string;
  name_hindi?: string | null;
  description?: string | null;
  cuisine: string;
  course: string;
  diet_type: string;
  prep_time_mins?: number;
  cook_time_mins?: number;
  total_time_mins?: number;
  default_servings?: number;
  difficulty?: string;
  tags?: string[] | null;
  image_url?: string | null;
};

type RecipeArchiveIngredient = {
  name: string;
  name_hindi?: string | null;
  quantity?: number | string | null;
  unit?: string | null;
  category?: string | null;
  is_optional?: boolean;
  prep_note?: string | null;
  substitutes?: string[] | null;
};

type RecipeArchiveDetail = RecipeArchiveSummary & {
  ingredients?: RecipeArchiveIngredient[];
};

const VEG_DIETS = new Set(["vegetarian", "vegan", "jain", "sattvic"]);
const COURSE_TO_MEAL_TYPES: Record<string, string[]> = {
  breakfast: ["breakfast"],
  brunch: ["breakfast", "lunch"],
  main: ["lunch", "dinner"],
  side: ["lunch", "dinner"],
  snack: ["snack"],
  dessert: ["dessert"],
  beverage: ["beverage"],
};

function difficultyToTier(d?: string): number {
  switch ((d ?? "").toLowerCase()) {
    case "easy": return 1;
    case "medium": return 2;
    case "hard": return 3;
    default: return 2;
  }
}

function mapSummary(r: RecipeArchiveSummary, idx: number): Dish {
  return {
    id: r.id ?? r.slug,
    slug: r.slug,
    name: r.name,
    description: r.description ?? null,
    cuisine: r.cuisine ?? "indian",
    meal_types: COURSE_TO_MEAL_TYPES[r.course?.toLowerCase() ?? ""] ?? ["lunch", "dinner"],
    is_veg: VEG_DIETS.has((r.diet_type ?? "").toLowerCase()),
    base_time_minutes: r.total_time_mins ?? 30,
    skill_tier: difficultyToTier(r.difficulty),
    required_ingredients: [],
    customization_options: {},
    image_url: r.image_url ?? null,
    display_order: idx,
  };
}

function mapDetail(r: RecipeArchiveDetail): Dish {
  const summary = mapSummary(r, 0);
  return {
    ...summary,
    required_ingredients: (r.ingredients ?? []).map((i) => i.name),
    ingredients: (r.ingredients ?? []).map((i) => ({
      name: i.name,
      quantity: i.quantity != null ? String(i.quantity) : undefined,
      unit: i.unit ?? undefined,
    })),
  };
}

export async function fetchDishCatalog(params?: { is_veg?: boolean; meal_type?: string }): Promise<Dish[]> {
  // Recipe archive's filter API takes `diet_type` + `course` parameters,
  // not `is_veg` + `meal_type`. Translate at the boundary.
  const apiParams: Record<string, string> = {};
  if (params?.is_veg === true) apiParams.diet_type = "vegetarian";
  // `is_veg === false` doesn't translate cleanly (could be non_veg/eggetarian/
  // etc.) — let the user filter in-UI rather than over-restrict the query.
  if (params?.meal_type) apiParams.course = params.meal_type;

  const { data } = await client.get("/recipe-archive", { params: apiParams });
  // Recipe archive may return either a list or a paginated envelope —
  // accept both shapes.
  const items: RecipeArchiveSummary[] = Array.isArray(data)
    ? data
    : Array.isArray(data?.items)
      ? data.items
      : Array.isArray(data?.recipes)
        ? data.recipes
        : [];
  return items.map(mapSummary);
}

export async function fetchDish(slugOrId: string): Promise<Dish> {
  const { data } = await client.get(`/recipe-archive/${encodeURIComponent(slugOrId)}`);
  return mapDetail(data as RecipeArchiveDetail);
}
