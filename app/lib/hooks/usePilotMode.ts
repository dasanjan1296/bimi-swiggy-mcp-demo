/**
 * usePilotMode — gates the app surface for the coordination-first pilot cohort.
 *
 * When a household is tagged `cohort === 'pilot_v1'` (set via the backend
 * during pilot onboarding — see investor/PILOT-PLAYBOOK.md §1), the app
 * shows a simplified surface: InstaCook/dish/marketplace screens are
 * replaced by a waitlist card, Settings is trimmed, and the tab bar omits
 * unrelated sections.
 *
 * Non-pilot households see the full app unchanged.
 *
 * Usage:
 *   const isPilot = usePilotMode();
 *   if (isPilot) { ... show simplified surface ... }
 *   else { ... show full app ... }
 *
 * See bimi/pilot/tech-backlog.md T-001 for the engineering context
 * and bimi/pilot/index.html for the pilot positioning.
 */

import { useHouseholdStore } from "@/lib/store";

/** Cohort identifier used by the coordination-first pilot. */
export const PILOT_COHORT = "pilot_v1" as const;

/**
 * Returns true when the current household is part of the coordination-first
 * pilot cohort. Safe to call from any render path; reads reactively from
 * the household store.
 */
export function usePilotMode(): boolean {
  const cohort = useHouseholdStore((s) => s.household?.cohort);
  return cohort === PILOT_COHORT;
}

/**
 * Non-hook version for contexts where hooks can't be used (e.g. navigation
 * config at module level, utility functions). Reads the store directly.
 */
export function isPilotMode(): boolean {
  return useHouseholdStore.getState().household?.cohort === PILOT_COHORT;
}
