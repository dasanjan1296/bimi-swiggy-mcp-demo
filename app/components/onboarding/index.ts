/**
 * Bimi onboarding-flow components. Used exclusively by the redesigned
 * household-setup flow (see app/household-setup.tsx). These are
 * intentionally feature-specific — they belong here, not in
 * `components/patterns/`, which is reserved for general-purpose blocks.
 *
 * Two generations of components live here:
 *
 *   v2 (in current flow): BimiSays, LearnedSummary, CuisineTradition-
 *       Picker, DietProfileMultiSelect, EatInCadenceGrid,
 *       CookContactCard, HonestPreview, MemberCounter, DishSwipeDeck.
 *
 *   v1 (no longer wired into onboarding, kept as reusable patterns
 *       for settings or future flows): BurnerStove, MealSlotMultiSelect,
 *       MemberDietCard, DishGridPicker.
 */

// v2 — conversational flow
export { BimiSays } from "./BimiSays";
export type { BimiSaysProps, LearnedFact } from "./BimiSays";

export { LearnedSummary } from "./LearnedSummary";
export type { LearnedSummaryProps, LearnedItem } from "./LearnedSummary";

export { CuisineTraditionPicker } from "./CuisineTraditionPicker";
export type { CuisineTraditionPickerProps } from "./CuisineTraditionPicker";

export { DietProfileMultiSelect } from "./DietProfileMultiSelect";
export type { DietProfileMultiSelectProps } from "./DietProfileMultiSelect";

export { EatInCadenceGrid } from "./EatInCadenceGrid";
export type { EatInCadenceGridProps } from "./EatInCadenceGrid";

export { CookContactCard } from "./CookContactCard";
export type { CookContactCardProps } from "./CookContactCard";

export { HonestPreview } from "./HonestPreview";
export type { HonestPreviewProps, PreviewGap } from "./HonestPreview";

export { MemberCounter } from "./MemberCounter";
export type { MemberCounterProps } from "./MemberCounter";

export { DishSwipeDeck } from "./DishSwipeDeck";
export type { DishSwipeDeckProps, SwipeVerdict } from "./DishSwipeDeck";

// v1 — kept for settings or future use
export { BurnerStove } from "./BurnerStove";
export type { BurnerCount, BurnerStoveProps } from "./BurnerStove";

export { MealSlotMultiSelect } from "./MealSlotMultiSelect";
export type { SlotKey, MealSlotMultiSelectProps } from "./MealSlotMultiSelect";

export { MemberDietCard } from "./MemberDietCard";
export type { MemberDietCardProps } from "./MemberDietCard";

export { DishGridPicker } from "./DishGridPicker";
export type { DishGridPickerProps } from "./DishGridPicker";
