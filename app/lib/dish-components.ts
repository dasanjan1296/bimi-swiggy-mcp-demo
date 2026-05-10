/**
 * Plate-component lookup for popular Indian household dishes.
 *
 * Used by the day-detail modal's expanded meal view to surface what's
 * actually ON the plate when a dish is voted in — e.g., "Rajma Chawal"
 * unfolds into Rajma curry · Steamed rice · Onion-cucumber salad ·
 * Pickle. Raw ingredient lists (`MealSuggestion.ingredients`) describe
 * the cook's shopping list but don't tell the eater what they'll see
 * on the plate; this module bridges that gap with a small, hand-curated
 * map.
 *
 * Lookup is case-insensitive on the dish name. For unknown dishes the
 * caller falls back to the raw ingredient list (`fallbackToIngredients`
 * helper below) so the section is always populated rather than empty.
 *
 * Authoring guidance:
 *   • 3–5 components per dish — enough to convey the plate, not so many
 *     it reads as a recipe.
 *   • Title case ("Steamed Rice", not "rice").
 *   • Lead with the headline component (the curry / main protein), end
 *     with accompaniments (chutney / pickle / salad).
 */

const COMPONENTS: Record<string, string[]> = {
  // ── Lunches ─────────────────────────────────────────────────────────
  "rajma chawal": [
    "Rajma curry",
    "Steamed rice",
    "Sliced onion & lemon",
    "Green chutney",
  ],
  "chole bhature": [
    "Chole (chickpea curry)",
    "Bhature (puffed bread)",
    "Pickled onion",
    "Green chilli",
  ],
  "paneer butter masala": [
    "Paneer butter masala",
    "Steamed rice or naan",
    "Sliced onion",
    "Salad",
  ],
  "dal makhani": [
    "Dal makhani",
    "Jeera rice",
    "Roti",
    "Pickle",
  ],
  "biryani": [
    "Biryani",
    "Raita",
    "Mirchi ka salan",
    "Salad",
  ],
  "veg biryani": [
    "Veg biryani",
    "Raita",
    "Salan",
    "Salad",
  ],
  "chicken biryani": [
    "Chicken biryani",
    "Raita",
    "Salan",
    "Salad",
  ],

  // ── Dinners ─────────────────────────────────────────────────────────
  "dal tadka": [
    "Dal tadka",
    "Phulka or rice",
    "Sabzi",
    "Salad",
  ],
  "khichdi": [
    "Moong dal khichdi",
    "Ghee",
    "Papad",
    "Pickle",
  ],
  "moong dal khichdi": [
    "Moong dal khichdi",
    "Ghee",
    "Papad",
    "Pickle",
  ],
  "aloo gobi": [
    "Aloo gobi sabzi",
    "Phulka",
    "Dal",
    "Salad",
  ],
  "rajma": [
    "Rajma curry",
    "Steamed rice",
    "Salad",
  ],

  // ── Breakfasts ──────────────────────────────────────────────────────
  "aloo paratha with curd": [
    "Aloo paratha",
    "Fresh curd",
    "Pickle",
    "Butter",
  ],
  "aloo paratha": [
    "Aloo paratha",
    "Fresh curd",
    "Pickle",
    "Butter",
  ],
  "poha with chai": [
    "Poha",
    "Masala chai",
    "Sev (optional)",
    "Lemon wedge",
  ],
  "poha": [
    "Poha",
    "Sev",
    "Lemon wedge",
    "Chai",
  ],
  "idli sambar": [
    "Idli (3-4 pcs)",
    "Sambar",
    "Coconut chutney",
    "Tomato chutney",
  ],
  "idli": [
    "Idli",
    "Sambar",
    "Coconut chutney",
  ],
  "dosa": [
    "Dosa",
    "Sambar",
    "Coconut chutney",
    "Potato masala",
  ],
  "masala dosa": [
    "Masala dosa",
    "Sambar",
    "Coconut chutney",
  ],
  "upma": [
    "Rava upma",
    "Coconut chutney",
    "Chai",
  ],
  "rava upma": [
    "Rava upma",
    "Coconut chutney",
    "Chai",
  ],
  "besan chilla": [
    "Besan chilla",
    "Green chutney",
    "Curd",
  ],
  "bread omelette": [
    "Bread omelette",
    "Tomato ketchup",
    "Tea or coffee",
  ],
  "cheese chilli toast": [
    "Cheese chilli toast",
    "Ketchup",
    "Chai",
  ],
  "maggi masala": [
    "Maggi noodles",
    "Egg or veggies (optional)",
  ],
  "curd rice": [
    "Curd rice",
    "Pickle",
    "Papad",
  ],
  "veg mayo sandwich": [
    "Veg mayo sandwich",
    "Wafers",
    "Ketchup",
  ],
  "5-min dal tadka with rice": [
    "Dal tadka",
    "Steamed rice",
    "Ghee",
    "Pickle",
  ],
};

/**
 * Look up the plate components for a dish. Case-insensitive; trims
 * whitespace; returns null for unknown dishes (caller falls back to
 * the raw ingredients list).
 */
export function getDishComponents(dishName: string | undefined | null): string[] | null {
  if (!dishName) return null;
  const key = dishName.trim().toLowerCase();
  if (!key) return null;
  return COMPONENTS[key] ?? null;
}

/**
 * Resolve plate components with a graceful fallback to ingredients.
 * Returns an empty array if neither source has anything (caller can
 * then choose to hide the section entirely).
 */
export function resolveDishComponents(
  dishName: string | undefined | null,
  fallbackIngredients: string[] | undefined,
): string[] {
  const direct = getDishComponents(dishName);
  if (direct && direct.length > 0) return direct;
  return (fallbackIngredients ?? []).map(titleCase);
}

function titleCase(s: string): string {
  return s
    .split(" ")
    .map((w) => (w.length === 0 ? w : w[0].toUpperCase() + w.slice(1).toLowerCase()))
    .join(" ");
}
