/**
 * Curated catalog used by the redesigned onboarding flow. Every entry's
 * `slug` MUST exist in `lib/dish-images.ts` so the bundled photo
 * resolves at build time — no network round-trips during onboarding,
 * which is the worst place to wait for an image to decode.
 *
 * Two views over the same catalog:
 *
 *   • TASTE_DECK_DISHES — the 12 dishes the household swipes through.
 *     Hand-picked to span North/South/East/Coastal Indian + a couple of
 *     vegetarian crowd-pleasers + a couple of clearly non-veg picks, so
 *     a handful of swipes already paint a usable preference profile.
 *
 *   • COOK_REPERTOIRE_OPTIONS — the photo grid the user taps to seed
 *     the cook's repertoire. Wider than the taste deck (24 dishes) and
 *     skewed toward staple weeknight food, since a cook's repertoire
 *     tends to lean home-style not aspirational.
 *
 * Both lists are display-name + slug + isVeg. The flow uses isVeg later
 * to gray-out non-veg dishes when the household has zero non-veg eaters
 * — see `relevantTasteDeck()` for the filter.
 */

import type { DietPreset } from "./store";

export interface OnboardingDish {
  slug: string;
  name: string;
  /** Plain-language sub-line for the swipe card ("Punjabi · creamy" etc.). */
  blurb: string;
  isVeg: boolean;
}

export const TASTE_DECK_DISHES: OnboardingDish[] = [
  { slug: "rajma-chawal",         name: "Rajma Chawal",          blurb: "Punjabi · cosy weeknight",  isVeg: true  },
  { slug: "paneer-butter-masala", name: "Paneer Butter Masala",  blurb: "North · creamy",            isVeg: true  },
  { slug: "masala-dosa",          name: "Masala Dosa",           blurb: "South · crisp",             isVeg: true  },
  { slug: "chana-masala",         name: "Chana Masala",          blurb: "Punjabi · spicy",           isVeg: true  },
  { slug: "chicken-biryani",      name: "Chicken Biryani",       blurb: "Hyderabadi · weekend",      isVeg: false },
  { slug: "fish-curry-bengali",   name: "Bengali Fish Curry",    blurb: "Bengali · light",           isVeg: false },
  { slug: "aloo-gobi",            name: "Aloo Gobi",             blurb: "North · everyday sabzi",    isVeg: true  },
  { slug: "dal-makhani",          name: "Dal Makhani",           blurb: "Punjabi · slow-cooked",     isVeg: true  },
  { slug: "idli-sambar",          name: "Idli Sambar",           blurb: "South · breakfast",         isVeg: true  },
  { slug: "egg-curry",            name: "Egg Curry",             blurb: "North · simple",            isVeg: false },
  { slug: "palak-paneer",         name: "Palak Paneer",          blurb: "North · greens-forward",    isVeg: true  },
  { slug: "mutton-curry",         name: "Mutton Curry",          blurb: "North · Sunday lunch",      isVeg: false },
];

export const COOK_REPERTOIRE_OPTIONS: OnboardingDish[] = [
  // Vegetarian staples first — most cooks lead with these.
  { slug: "rajma-chawal",          name: "Rajma Chawal",           blurb: "", isVeg: true  },
  { slug: "chana-masala",          name: "Chana Masala",           blurb: "", isVeg: true  },
  { slug: "aloo-gobi",             name: "Aloo Gobi",              blurb: "", isVeg: true  },
  { slug: "bhindi-masala",         name: "Bhindi Masala",          blurb: "", isVeg: true  },
  { slug: "baingan-bharta",        name: "Baingan Bharta",         blurb: "", isVeg: true  },
  { slug: "paneer-butter-masala",  name: "Paneer Butter Masala",   blurb: "", isVeg: true  },
  { slug: "palak-paneer",          name: "Palak Paneer",           blurb: "", isVeg: true  },
  { slug: "dal-makhani",           name: "Dal Makhani",            blurb: "", isVeg: true  },
  { slug: "jeera-rice",            name: "Jeera Rice",             blurb: "", isVeg: true  },
  { slug: "veg-pulao",             name: "Veg Pulao",              blurb: "", isVeg: true  },
  { slug: "curd-rice",             name: "Curd Rice",              blurb: "", isVeg: true  },
  { slug: "rasam",                 name: "Rasam",                  blurb: "", isVeg: true  },
  { slug: "idli-sambar",           name: "Idli Sambar",            blurb: "", isVeg: true  },
  { slug: "masala-dosa",           name: "Masala Dosa",            blurb: "", isVeg: true  },
  { slug: "rava-upma",             name: "Rava Upma",              blurb: "", isVeg: true  },
  { slug: "bisi-bele-bath",        name: "Bisi Bele Bath",         blurb: "", isVeg: true  },
  { slug: "aloo-posto",            name: "Aloo Posto",             blurb: "", isVeg: true  },
  { slug: "shukto",                name: "Shukto",                 blurb: "", isVeg: true  },
  // Non-veg block.
  { slug: "egg-curry",             name: "Egg Curry",              blurb: "", isVeg: false },
  { slug: "chicken-curry",         name: "Chicken Curry",          blurb: "", isVeg: false },
  { slug: "chicken-biryani",       name: "Chicken Biryani",        blurb: "", isVeg: false },
  { slug: "fish-curry-bengali",    name: "Bengali Fish Curry",     blurb: "", isVeg: false },
  { slug: "fish-fry",              name: "Fish Fry",               blurb: "", isVeg: false },
  { slug: "mutton-curry",          name: "Mutton Curry",           blurb: "", isVeg: false },
];

/**
 * The 11 most common allergens / aversions in Indian households,
 * picked from a chip list — never typed. Order is loosely "most common
 * first". "Onion / Garlic" is a single pill because they almost always
 * travel together in Jain / Sattvik households.
 */
export const COMMON_ALLERGIES_AND_AVOIDS: string[] = [
  "Peanuts",
  "Tree nuts",
  "Mushroom",
  "Onion / Garlic",
  "Egg",
  "Dairy",
  "Gluten",
  "Soy",
  "Sesame",
  "Shellfish",
  "Brinjal",
];

/**
 * Diet-aware filter — drops non-veg dishes from the deck when nobody in
 * the household eats meat. Onboarding calls this BEFORE rendering the
 * swipe deck so vegetarian households don't see chicken biryani as the
 * second card.
 */
export function relevantTasteDeck(diets: DietPreset[]): OnboardingDish[] {
  const anyNonVeg = diets.some((d) => d === "non_veg" || d === "eggetarian");
  if (anyNonVeg) return TASTE_DECK_DISHES;
  return TASTE_DECK_DISHES.filter((d) => d.isVeg);
}

export function relevantRepertoire(diets: DietPreset[]): OnboardingDish[] {
  const anyNonVeg = diets.some((d) => d === "non_veg" || d === "eggetarian");
  if (anyNonVeg) return COOK_REPERTOIRE_OPTIONS;
  return COOK_REPERTOIRE_OPTIONS.filter((d) => d.isVeg);
}

// ────────────────────────────────────────────────────────────────────
// v3 conversational-flow data
// ────────────────────────────────────────────────────────────────────

import type {
  CityKey,
  CuisineTradition,
  DietFacet,
} from "./store";

export const CITIES: { key: CityKey; label: string }[] = [
  { key: "bangalore",  label: "Bangalore" },
  { key: "mumbai",     label: "Mumbai" },
  { key: "delhi_ncr",  label: "Delhi NCR" },
  { key: "hyderabad",  label: "Hyderabad" },
  { key: "chennai",    label: "Chennai" },
  { key: "pune",       label: "Pune" },
  { key: "kolkata",    label: "Kolkata" },
  { key: "other",      label: "Somewhere else" },
];

/**
 * Per-city short reflection Bimi voices back after the user picks a
 * city. Sourced from rough cohort observations — the cook-simulation
 * report (docs/COOK-SIMULATION-REPORT.md) shows Bangalore households
 * cook 4-5 weeknights, Delhi 5-6, Mumbai 3-4 (more eating out). These
 * are inferences for tone, not commitments — the eat-in cadence step
 * lets the user correct the inference.
 */
export const CITY_REFLECTIONS: Record<CityKey, string> = {
  bangalore: "Most Bangalore households I work with cook 4–5 nights a week.",
  mumbai:    "Mumbai households eat out a lot more — I'll keep weekday plans light.",
  delhi_ncr: "Delhi families cook most nights. Big Sunday lunches are a thing.",
  hyderabad: "Hyderabad households tend to skew non-veg. I'll keep biryani in rotation.",
  chennai:   "Chennai households lean South Indian most days. I'll respect that.",
  pune:      "Pune households are a mix — Maharashtrian classics with North Indian dinners.",
  kolkata:   "Kolkata kitchens are fish-forward and breakfast-heavy. I'll plan around that.",
  other:     "Got it. I'll learn your city's rhythms from what you cook.",
};

export interface CuisineOption {
  value: CuisineTradition;
  label: string;
  blurb: string;
  emoji: string;
}

export const CUISINE_TRADITIONS: CuisineOption[] = [
  { value: "north_indian",   label: "North Indian",     blurb: "Punjabi, Awadhi, Mughlai",       emoji: "🌶️" },
  { value: "south_indian",   label: "South Indian",     blurb: "Karnataka, TN, Kerala, AP",      emoji: "🥥" },
  { value: "bengali",        label: "Bengali",          blurb: "Fish, mustard, rice",            emoji: "🐟" },
  { value: "maharashtrian",  label: "Maharashtrian",    blurb: "Bhakri, varan-bhaat",            emoji: "🌾" },
  { value: "gujarati",       label: "Gujarati",         blurb: "Sweet-savoury, thali style",     emoji: "🍯" },
  { value: "everything",     label: "We eat everything",blurb: "Surprise us — variety welcome",  emoji: "🌍" },
  { value: "continental",    label: "Continental too",  blurb: "Pasta, salads, sandwiches",      emoji: "🥗" },
];

export interface DietFacetOption {
  value: DietFacet;
  label: string;
  /** Short reasoning Bimi will reflect ("I'll keep weekday meals vegetarian.") */
  reflection: string;
  /** Optional incompatibility group — only one facet from each group can be active. */
  group?: "veg" | "nonveg_cadence";
}

export const DIET_PROFILE_OPTIONS: DietFacetOption[] = [
  { value: "pure_veg",         label: "Pure vegetarian",   reflection: "Keeping every suggestion vegetarian.",       group: "veg" },
  { value: "eggs_ok",          label: "Eggs are okay",     reflection: "Eggs in the rotation.",                       group: "veg" },
  { value: "non_veg_weekends", label: "Non-veg weekends",  reflection: "Weekend non-veg, weekday vegetarian.",        group: "nonveg_cadence" },
  { value: "non_veg_weekdays", label: "Non-veg any day",   reflection: "Non-veg in the mix anytime.",                 group: "nonveg_cadence" },
  { value: "no_onion_garlic",  label: "No onion / garlic", reflection: "Sattvik — I'll skip onion and garlic." },
  { value: "no_beef",          label: "No beef",           reflection: "No beef — never suggesting it." },
  { value: "no_pork",          label: "No pork",           reflection: "No pork — never suggesting it." },
  { value: "jain",             label: "Jain",              reflection: "Jain — no roots, no allium." },
];

/**
 * Common Bangalore-household allergies. Order is by real prevalence.
 * Non-Bangalore households see the same list — these are mostly
 * pan-Indian aversions. The 5 most common come first so the chip cloud
 * looks short by default.
 */
export const COMMON_ALLERGIES: string[] = [
  "Peanut",
  "Mushroom",
  "Egg",
  "Shellfish",
  "Lactose",
  "Tree nuts",
  "Mustard",
  "Sesame",
  "Soy",
  "Gluten",
];

/**
 * Names a Bangalore household actually uses for the cook. Most users
 * land on a relational name (Akka in Kannada/Tamil-speaking homes, Didi
 * in Hindi/Hindi-mix homes, Aunty for older cooks) before they learn
 * the cook's first name. Pre-filling these as taps removes the
 * "what do I write here?" friction that broke the prior step.
 */
export const COOK_NAME_OPTIONS: string[] = ["Akka", "Didi", "Aunty", "Bai"];

/**
 * Region-aware default repertoire — used when the cook hasn't yet
 * replied via WhatsApp. Picked so a household in Bangalore with a
 * Karnataka cook gets sambar/bisi-bele-bath/idli as the implied
 * baseline, while a Delhi household gets dal-makhani/chana/aloo-gobi.
 *
 * The intersection of (region defaults ∩ taste verdicts) drives the
 * Day-1 dinner suggestion in the Honest Preview step.
 */
export const REGION_DEFAULT_REPERTOIRE: Record<CuisineTradition, string[]> = {
  north_indian:   ["dal-makhani", "rajma-chawal", "chana-masala", "aloo-gobi", "paneer-butter-masala", "jeera-rice"],
  south_indian:   ["idli-sambar", "masala-dosa", "rasam", "bisi-bele-bath", "curd-rice", "rava-upma"],
  bengali:        ["fish-curry-bengali", "aloo-posto", "shukto", "rajma-chawal"],
  maharashtrian:  ["aloo-gobi", "dal-makhani", "veg-pulao", "jeera-rice"],
  gujarati:       ["aloo-gobi", "dal-makhani", "veg-pulao", "rava-upma"],
  everything:     ["rajma-chawal", "idli-sambar", "chicken-curry", "paneer-butter-masala", "masala-dosa"],
  continental:    ["jeera-rice", "veg-pulao", "grilled-chicken", "aloo-gobi"],
};

/** Combined facets → DietPreset reduction for downstream filters. */
export function reduceDietProfile(facets: DietFacet[]): DietPreset {
  if (facets.includes("non_veg_weekdays") || facets.includes("non_veg_weekends")) {
    return "non_veg";
  }
  if (facets.includes("eggs_ok")) return "eggetarian";
  return "veg";
}

/**
 * Smarter taste deck filter:
 *   • Always 6 cards (deck length tuned to the "swipe momentum ceiling")
 *   • Region-aware: a Bangalore South Indian household sees rasam &
 *     bisi-bele-bath; a Delhi North Indian household sees rajma & dal
 *     makhani — instead of the same 12 cards every household.
 *   • Diet-aware: vegetarian households never see meat dishes.
 *   • Always includes 1 "stretch" card from outside the household's
 *     primary tradition — Bimi explicitly wants to learn whether the
 *     household is open to variety.
 */
export function smartTasteDeck(opts: {
  diets: DietPreset[];
  cuisines: CuisineTradition[];
}): OnboardingDish[] {
  const veganOnly = !opts.diets.some((d) => d === "non_veg" || d === "eggetarian");
  const all = veganOnly ? TASTE_DECK_DISHES.filter((d) => d.isVeg) : TASTE_DECK_DISHES;

  // Score each dish by how strongly it matches the picked traditions.
  // The mapping below is intentionally rough — it's a tiebreaker, not
  // a classifier.
  const traditionMap: Record<CuisineTradition, string[]> = {
    north_indian:  ["rajma", "dal", "chana", "paneer", "aloo", "biryani"],
    south_indian:  ["dosa", "idli", "rasam", "bisi", "curd"],
    bengali:       ["fish", "shukto", "posto"],
    maharashtrian: ["aloo", "dal"],
    gujarati:      ["aloo", "dal", "rava"],
    everything:    [],
    continental:   [],
  };
  const keywords = new Set<string>(
    opts.cuisines.flatMap((c) => traditionMap[c] ?? []),
  );

  const scored = all.map((d) => {
    const slug = d.slug;
    const score = [...keywords].some((k) => slug.includes(k)) ? 1 : 0;
    return { dish: d, score };
  });

  const matched = scored.filter((s) => s.score > 0).map((s) => s.dish);
  const stretch = scored.filter((s) => s.score === 0).map((s) => s.dish);

  const deck: OnboardingDish[] = [];
  // Up to 5 region-matched cards…
  deck.push(...matched.slice(0, 5));
  // …plus 1 stretch card so we learn whether the household will explore.
  if (stretch[0]) deck.push(stretch[0]);
  // Top up to 6 if we're under (e.g., narrow tradition pick).
  if (deck.length < 6) {
    const filler = all.filter((d) => !deck.includes(d)).slice(0, 6 - deck.length);
    deck.push(...filler);
  }
  return deck.slice(0, 6);
}

/**
 * Generates the WhatsApp message Bimi will send to the cook to learn
 * her actual repertoire. This replaces the user-guesses-cook's-skill
 * step. The user previews the message and decides whether to send now
 * or later.
 */
export function buildCookIntroMessage(opts: {
  householdLeadName: string;
  cookDisplayName: string;
}): string {
  const greeting = opts.cookDisplayName ? `Namaste ${opts.cookDisplayName}` : "Namaste";
  return [
    `${greeting} 🙏`,
    ``,
    `Main Bimi hoon — ${opts.householdLeadName} ki kitchen ka helper. App use kar rahi hoon main, taaki khaane ka plan rozaana sort ho jaaye.`,
    ``,
    `Aap kya banati ho sabse ache? Voice note bhi chalega — 5–6 dishes ka naam bata do. Main yaad rakh lungi 🙂`,
  ].join("\n");
}

/**
 * 7-day x 3-meal grid layout helper for the eat-in cadence step. Order
 * is Mon → Sun left-to-right, breakfast → lunch → dinner top-to-bottom.
 */
export const DAYS_OF_WEEK = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;
export const DAY_LABELS_SHORT = ["M", "T", "W", "T", "F", "S", "S"] as const;
export const MEAL_SLOTS_VERTICAL = ["breakfast", "lunch", "dinner"] as const;
export const MEAL_SLOT_LABELS = { breakfast: "Breakfast", lunch: "Lunch", dinner: "Dinner" } as const;
export const MEAL_SLOT_ICONS = { breakfast: "sunny-outline", lunch: "restaurant-outline", dinner: "moon-outline" } as const;
