/**
 * NextBestAction — single above-the-fold hero on the Home tab.
 *
 * Picks exactly ONE of the hero variants in NextBestActionHeroes.tsx based
 * on the priority tree documented in bimi_product_rework_*.plan.md. As of
 * the 2026-05-03 ICP narrowing, Bimi serves cook households exclusively —
 * the previous `hasRegularCook` / no-cook branch was retired.
 *
 * Owns the inline-review sheet state for the hero that needs one:
 *   - `<UnreadCookMessageHero>` → `<CookActionsSheet>` (Swiggy MCP cart)
 *
 * Keeping the sheet owned here means the hero stays dumb (it accepts
 * an `onPress`, no routing knowledge) and the user never leaves Today
 * to discharge a one-tap decision — honouring the brand promise that
 * Bimi pre-decides and the user just confirms.
 */

import React, { useState } from "react";
import {
  DayCompleteHero,
  FestivalTomorrowHero,
  HeroSkeleton,
  TodayMealStatusHero,
  TomorrowVoteHero,
  UnreadCookMessageHero,
} from "./NextBestActionHeroes";
import {
  CookActionsSheet,
  SwiggyDeliveryActiveHero,
  SwiggyDeliveredHero,
  SwiggyTrackingSheet,
} from "./patterns";
import {
  useDayCompleteState,
  useFestivalTomorrow,
  useTodaysMealPlan,
  useTomorrowNeedsVote,
  useUnresolvedCookActions,
} from "@/lib/home-state";
import { useHouseholdStore } from "@/lib/store";
import { useSwiggyDeliveryStore } from "@/lib/swiggy-delivery-store";

// Priority tree (2026-05-10 update — Swiggy MCP lifecycle takes over
// the home tab whenever a grocery delivery is in flight or just landed):
//   1. Swiggy delivery DELIVERED  → <SwiggyDeliveredHero>     (auto-restock fired)
//   2. Swiggy delivery ACTIVE     → <SwiggyDeliveryActiveHero>
//   3. unresolved cook chat       → <UnreadCookMessageHero>
//   4. festival tomorrow          → <FestivalTomorrowHero>
//   5. tomorrow needs vote        → <TomorrowVoteHero>
//   6. day complete               → <DayCompleteHero>
//   7. today's meal status        → <TodayMealStatusHero>     (default)
//
// Rationale: once the user's placed an order, that's the #1 thing to
// watch — surfaces it above any new cook chatter for the lifecycle
// window. The legacy `<GroceryApprovalHero>` / `<CartApprovalSheet>`
// (pre-Swiggy auto-grocery-order workflow) was retired in this pass.
export function NextBestAction() {
  const household = useHouseholdStore((s) => s.household);
  const unresolvedCookActions = useUnresolvedCookActions();
  const tomorrowNeedsVote = useTomorrowNeedsVote();
  const festivalTomorrow = useFestivalTomorrow();
  const todaysPlan = useTodaysMealPlan();
  const isDayComplete = useDayCompleteState();
  const swiggyState = useSwiggyDeliveryStore((s) => s.state);

  const [cookSheetOpen, setCookSheetOpen] = useState(false);
  const [trackingSheetOpen, setTrackingSheetOpen] = useState(false);

  if (!household) {
    return <HeroSkeleton />;
  }

  if (swiggyState === "delivered") {
    return <SwiggyDeliveredHero />;
  }
  if (swiggyState === "out_for_delivery") {
    return (
      <>
        <SwiggyDeliveryActiveHero
          onOpenTracking={() => setTrackingSheetOpen(true)}
        />
        <SwiggyTrackingSheet
          visible={trackingSheetOpen}
          onClose={() => setTrackingSheetOpen(false)}
        />
      </>
    );
  }

  if (unresolvedCookActions) {
    return (
      <>
        <UnreadCookMessageHero
          primary={unresolvedCookActions.primary}
          count={unresolvedCookActions.count}
          actions={unresolvedCookActions.actions}
          onOpenSheet={() => setCookSheetOpen(true)}
        />
        <CookActionsSheet
          visible={cookSheetOpen}
          onClose={() => setCookSheetOpen(false)}
        />
      </>
    );
  }
  if (festivalTomorrow) {
    return (
      <FestivalTomorrowHero
        name={festivalTomorrow.name}
        description={festivalTomorrow.description}
        dietaryOverride={festivalTomorrow.dietaryOverride}
      />
    );
  }
  if (tomorrowNeedsVote) {
    return <TomorrowVoteHero plan={tomorrowNeedsVote} />;
  }
  if (isDayComplete) {
    return <DayCompleteHero />;
  }
  return <TodayMealStatusHero plan={todaysPlan} />;
}
