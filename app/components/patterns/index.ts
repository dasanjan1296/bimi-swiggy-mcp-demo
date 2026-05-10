/**
 * Bimi composed UI patterns. Prefer importing from "@/components/patterns".
 *
 * Patterns are higher-level than `components/ui/` atoms — they compose
 * atoms + tokens into reusable blocks (Card, ListRow, FormSection, etc.)
 * Screens should consume `ui/` and `patterns/` only; never reach for raw
 * `<View>`/`<Text>` compositions when a pattern fits.
 */

export { Card } from "./Card";
export type { CardProps, CardVariant } from "./Card";

export { PhotoCard } from "./PhotoCard";
export type {
  PhotoCardProps,
  PhotoCardRibbon,
  PhotoCardBadge,
} from "./PhotoCard";

export { ListRow, ListRowGroup } from "./ListRow";
export type { ListRowProps } from "./ListRow";

export { ActionListRow } from "./ActionListRow";
export type { ActionListRowProps, ButtonAction } from "./ActionListRow";

export { FormSection } from "./FormSection";
export type { FormSectionProps } from "./FormSection";

export { EmptyState } from "./EmptyState";
export type { EmptyStateProps } from "./EmptyState";

export { GuidanceTip } from "./GuidanceTip";
export type { GuidanceTipProps, GuidanceTone } from "./GuidanceTip";

export { HowItWorks } from "./HowItWorks";
export type { HowItWorksProps, HowItWorksStep } from "./HowItWorks";

export { HeroCard } from "./HeroCard";
export type { HeroCardProps, HeroTone } from "./HeroCard";

export { HeaderWithActions } from "./HeaderWithActions";
export type { HeaderWithActionsProps, HeaderAction } from "./HeaderWithActions";

export { BandHeader } from "./BandHeader";
export type { BandHeaderProps } from "./BandHeader";

export { MealCard } from "./MealCard";
export type { MealCardProps } from "./MealCard";

export { CookActionsSheet } from "./CookActionsSheet";

export { GroceryActionRow } from "./GroceryActionRow";

export { SwiggyBadge, SWIGGY_ORANGE } from "./SwiggyBadge";

export {
  SwiggyDeliveryActiveHero,
  SwiggyDeliveredHero,
} from "./SwiggyDeliveryHeroes";

export { SwiggyTrackingSheet } from "./SwiggyTrackingSheet";

export { DemoSimulationBanner } from "./DemoSimulationBanner";

// 2026-05-10: `CartApprovalSheet` retired with the pre-Swiggy
// auto-grocery-order approval flow. Swiggy MCP cart sheet
// (`CookActionsSheet`) is the single grocery surface now.

export { AuthScreen } from "./AuthScreen";
export type {
  AuthScreenProps,
  AuthPrimaryAction,
  AuthTertiaryLink,
} from "./AuthScreen";

export { WhatsAppButton } from "./WhatsAppButton";
export type {
  WhatsAppButtonProps,
  WhatsAppButtonVariant,
  WhatsAppButtonSize,
} from "./WhatsAppButton";

export { TodaysPlanDrawer } from "./TodaysPlanDrawer";
export type { TodaysPlanDrawerProps } from "./TodaysPlanDrawer";

export { HomeCalendar } from "./HomeCalendar";
export type { HomeCalendarProps } from "./HomeCalendar";

export { DayCardRow } from "./DayCardRow";
export type { DayCardRowProps } from "./DayCardRow";

export { DayDetailSheet } from "./DayDetailSheet";
export type { DayDetailSheetProps } from "./DayDetailSheet";

export { DayMealSheet, DayVotingBody, CookOffBanner } from "./DayMealSheet";
export type { DayMealSheetProps, DayVotingBodyProps } from "./DayMealSheet";

export { PastDayDetailSheet, PastDayBody } from "./PastDayDetailSheet";
export type { PastDayDetailSheetProps, PastDayBodyProps } from "./PastDayDetailSheet";

export type {
  CalendarDay,
  DayState,
  MealPreview,
} from "./home-calendar-types";
