/**
 * Static dish photo map — bundled into the Expo binary so hero images render
 * instantly without a network round-trip. The compressed JPEGs (max 1200 px,
 * q≈82) live at `assets/dish-photos/dish-<slug>.jpg`.
 *
 * Keep this map in sync with the backend's `_IMAGE_SLUGS` set in
 * `bimi/backend/app/services/dish_catalog.py`. If a slug gains a new photo,
 * add a `require(...)` line here *and* drop the JPEG into the assets folder.
 *
 * We deliberately use literal `require()` calls rather than dynamic paths —
 * Metro only bundles assets it can statically resolve at build time.
 */

export const DISH_IMAGES: Record<string, number> = {
  "aloo-gobi": require("../assets/dish-photos/dish-aloo-gobi.jpg"),
  "aloo-posto": require("../assets/dish-photos/dish-aloo-posto.jpg"),
  "baingan-bharta": require("../assets/dish-photos/dish-baingan-bharta.jpg"),
  "bhindi-masala": require("../assets/dish-photos/dish-bhindi-masala.jpg"),
  "bisi-bele-bath": require("../assets/dish-photos/dish-bisi-bele-bath.jpg"),
  "butter-chicken": require("../assets/dish-photos/dish-butter-chicken.jpg"),
  "chana-masala": require("../assets/dish-photos/dish-chana-masala.jpg"),
  "chicken-biryani": require("../assets/dish-photos/dish-chicken-biryani.jpg"),
  "chicken-chettinad": require("../assets/dish-photos/dish-chicken-chettinad.jpg"),
  "chicken-curry": require("../assets/dish-photos/dish-chicken-curry.jpg"),
  "curd-rice": require("../assets/dish-photos/dish-curd-rice.jpg"),
  "dal-makhani": require("../assets/dish-photos/dish-dal-makhani.jpg"),
  "egg-curry": require("../assets/dish-photos/dish-egg-curry.jpg"),
  "fish-curry-bengali": require("../assets/dish-photos/dish-fish-curry-bengali.jpg"),
  "fish-fry": require("../assets/dish-photos/dish-fish-fry.jpg"),
  "fish-moilee": require("../assets/dish-photos/dish-fish-moilee.jpg"),
  "grilled-chicken": require("../assets/dish-photos/dish-grilled-chicken.jpg"),
  "idli-sambar": require("../assets/dish-photos/dish-idli-sambar.jpg"),
  "jeera-rice": require("../assets/dish-photos/dish-jeera-rice.jpg"),
  "kosha-mangsho": require("../assets/dish-photos/dish-kosha-mangsho.jpg"),
  "masala-dosa": require("../assets/dish-photos/dish-masala-dosa.jpg"),
  "mutton-curry": require("../assets/dish-photos/dish-mutton-curry.jpg"),
  "palak-paneer": require("../assets/dish-photos/dish-palak-paneer.jpg"),
  "paneer-butter-masala": require("../assets/dish-photos/dish-paneer-butter-masala.jpg"),
  "prawn-curry": require("../assets/dish-photos/dish-prawn-curry.jpg"),
  "rajma-chawal": require("../assets/dish-photos/dish-rajma-chawal.jpg"),
  "rasam": require("../assets/dish-photos/dish-rasam.jpg"),
  "rava-upma": require("../assets/dish-photos/dish-rava-upma.jpg"),
  "shukto": require("../assets/dish-photos/dish-shukto.jpg"),
  "veg-pulao": require("../assets/dish-photos/dish-veg-pulao.jpg"),
};

/**
 * Return the bundled hero image for a slug, or `undefined` if we haven't shot
 * one yet. Callers should fall back to the emoji hero / `image_url` from the
 * API for slugs that aren't in the map (dal-tadka, moong-dal, mixed-veg,
 * roti-chapati, khichdi, poha).
 */
export function getDishImage(slug: string): number | undefined {
  return DISH_IMAGES[slug];
}

export function hasDishImage(slug: string): boolean {
  return slug in DISH_IMAGES;
}

/**
 * Slug-from-name lookup for callers that only have the dish display name
 * (e.g. MealSuggestion.dishName "Chole Bhature" → slug "chole-bhature").
 * Returns the bundled image or undefined if no matching slug exists.
 */
export function getDishImageByName(name: string): number | undefined {
  const slug = name.toLowerCase().trim().replace(/\s+/g, "-");
  return DISH_IMAGES[slug];
}
