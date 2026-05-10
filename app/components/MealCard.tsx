/**
 * Compat shim — the canonical, image-led MealCard now lives in
 * `bimi/app/components/patterns/MealCard.tsx`. Existing imports from
 * `@/components/MealCard` keep resolving via this re-export.
 *
 * Prefer `import { MealCard } from "@/components/patterns"` in new code.
 */

export { MealCard } from "./patterns/MealCard";
export type { MealCardProps } from "./patterns/MealCard";
