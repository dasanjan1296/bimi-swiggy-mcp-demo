import { useMemo } from "react";

import { useHouseholdStore } from "./store";

/**
 * P3 (PRD 4.9): Progressive disclosure — gate features by tenure so
 * day-zero users don't see Splitwise/Health/Insights surfaces they
 * haven't earned context for yet. Reveal escalates as trust builds.
 *
 * | Week | Reveals |
 * |------|---------|
 * | 0    | Home, Voting, Kitchen, Cook chat, Plan-a-Day |
 * | 1    | Know-Me prompts (3/day), Smart Cart |
 * | 2    | Expenses tab, Splitwise push |
 * | 3    | Proxy voting offer, Insights, Health Dashboard |
 * | 4+   | Splitwise OAuth, scheduled rules, advisor connections |
 *
 * Households created before this flag landed (no `createdAt`) are
 * treated as fully tenured so we don't regress existing testers.
 */

function weeksSince(iso: string | undefined): number {
  if (!iso) return 99;
  const ms = Date.now() - new Date(iso).getTime();
  if (Number.isNaN(ms) || ms < 0) return 99;
  return Math.floor(ms / (7 * 24 * 60 * 60 * 1000));
}

export interface FeatureFlags {
  weeks: number;
  showKnowMe: boolean;
  showSmartCart: boolean;
  showExpenses: boolean;
  showSplitwise: boolean;
  showProxyVoteOffer: boolean;
  showInsights: boolean;
  showHealthDashboard: boolean;
  showSplitwiseOAuth: boolean;
  showScheduledRules: boolean;
  showAdvisor: boolean;
  /**
   * Insta Cook (on-demand cook marketplace) was paused as part of the
   * coordination-only pivot (May 2026). When false, all Insta Cook surfaces
   * are hidden from the user-facing app: home cards, "Just one cook" tile,
   * cook-off booking chips, etc. Routes still exist so deep links don't 404
   * — they just aren't promoted anywhere visible.
   */
  showInstacook: boolean;
}

export function useFeatureFlags(): FeatureFlags {
  const createdAt = useHouseholdStore((s) => s.household?.createdAt);
  return useMemo(() => {
    const weeks = weeksSince(createdAt);
    return {
      weeks,
      showKnowMe: weeks >= 1,
      showSmartCart: weeks >= 1,
      showExpenses: weeks >= 2,
      showSplitwise: weeks >= 2,
      showProxyVoteOffer: weeks >= 3,
      showInsights: weeks >= 3,
      showHealthDashboard: weeks >= 3,
      showSplitwiseOAuth: weeks >= 4,
      showScheduledRules: weeks >= 4,
      showAdvisor: weeks >= 4,
      // Hard off for the coordination-only launch.
      showInstacook: false,
    };
  }, [createdAt]);
}
