/**
 * Meal lifecycle state machine — single source of truth for "what
 * does the system actually think about this meal right now?"
 *
 * The store maintains three signals on a `MealPlan`:
 *   • `votes`         — every household member's individual pick.
 *   • `selectedMeal`  — the WINNER per the household's voting mode
 *                       (set by the backend once the threshold is met:
 *                       solo = 1 vote; majority = >50%; consensus =
 *                       all; hierarchical = decision-maker's vote).
 *   • `lockInAt`      — soft-lock window: now + 5 min, capped at the
 *                       voting deadline. Until it elapses the user
 *                       can still switch (`selectedMeal` mutable).
 *   • `isLocked`      — hard-lock flag, set after `lockInAt` fires.
 *                       Cook brief has been sent, choice is final.
 *
 * UI surfaces (calendar cell, day-detail modal, etc.) consume the
 * derived `MealLifecycleState` instead of reading these four fields
 * directly so the labels, colors, and copy stay consistent.
 *
 * State transitions:
 *
 *   open   ──first vote──▶ voting   ──threshold met──▶ tentative
 *                                                          │
 *                                                  lockInAt elapses
 *                                                          ▼
 *                                                       locked
 *
 * Future days (D+2..D+6) skip the soft-lock cycle entirely:
 * `voteFutureDay` writes `selectedMeal` directly with no `lockInAt`,
 * so they always classify as `locked` once a dish is picked. That
 * matches reality — these are pre-votes, not consensus moments.
 */

import type {
  HouseholdMember,
  MealPlan,
  MealVote,
  VotingMode,
} from "./types";

export type MealLifecycleState =
  | "open"       // No votes, no winner.
  | "voting"     // Some votes, no winner yet (threshold not met).
  | "tentative"  // Winner picked, soft-lock window still ticking.
  | "locked";    // Final: cook briefed; user can no longer change.

/**
 * Classify a meal's lifecycle state. Pure function of the plan data
 * + the current wall-clock time (for the soft-lock window check).
 *
 * Pass `now` explicitly if you need deterministic output (tests); it
 * defaults to `Date.now()` for callers that don't care.
 */
export function classifyMealState(
  plan: Pick<MealPlan, "selectedMeal" | "isLocked" | "lockInAt" | "votes">,
  now: number = Date.now(),
): MealLifecycleState {
  if (plan.isLocked) return "locked";
  if (plan.selectedMeal) {
    if (plan.lockInAt) {
      const deadline = new Date(plan.lockInAt).getTime();
      // Tentative ONLY while the soft-lock timer is in the future.
      // Past deadlines mean the lock fired but the FE store hasn't
      // yet flipped `isLocked` — treat as effectively locked.
      if (Number.isFinite(deadline) && now < deadline) return "tentative";
    }
    return "locked";
  }
  if ((plan.votes ?? []).filter((v) => !v.skipped).length > 0) {
    return "voting";
  }
  return "open";
}

/**
 * "Anjan, Mayank · Dal Tadka" style tally row for the modal's
 * "Household votes" section. Filters proxy + skipped votes so the
 * tally reflects what the human members actually picked.
 */
export interface VoteTallyRow {
  dishName: string;
  voters: { memberId: string; memberName: string; isProxy: boolean }[];
}

export function buildVoteTally(plan: Pick<MealPlan, "votes">): VoteTallyRow[] {
  const byDish = new Map<string, VoteTallyRow>();
  for (const v of plan.votes ?? []) {
    if (v.skipped) continue;
    const key = v.dishName.toLowerCase();
    let row = byDish.get(key);
    if (!row) {
      row = { dishName: v.dishName, voters: [] };
      byDish.set(key, row);
    }
    row.voters.push({
      memberId: v.memberId,
      memberName: v.memberName,
      isProxy: !!v.isProxy,
    });
  }
  // Sort: largest tally first, then alphabetical for stable display.
  return Array.from(byDish.values()).sort((a, b) => {
    if (b.voters.length !== a.voters.length) return b.voters.length - a.voters.length;
    return a.dishName.localeCompare(b.dishName);
  });
}

/**
 * One-line explanation of HOW the system arrived at `selectedMeal`,
 * for the day-detail modal. Returns an empty string if there's no
 * winner yet.
 *
 * Examples (mode → output):
 *   solo          → "Your pick"
 *   consensus     → "Consensus pick — everyone chose Dal Tadka"
 *                 → "Picked by household" (when not all members voted)
 *   majority      → "Majority pick — 2 of 3 voted Dal Tadka"
 *   hierarchical  → "Anjan's pick" (decision-maker's name)
 *   unknown mode  → "Picked by household"
 */
export function explainDecision(
  plan: Pick<MealPlan, "selectedMeal" | "votes">,
  votingMode: VotingMode | undefined,
  activeMembers: Pick<HouseholdMember, "id" | "name" | "role">[],
): string {
  if (!plan.selectedMeal) return "";

  const winner = plan.selectedMeal.toLowerCase();
  const realVotes = (plan.votes ?? []).filter((v) => !v.skipped);
  const winnerVotes = realVotes.filter(
    (v) => v.dishName.toLowerCase() === winner,
  );
  const totalRealVotes = realVotes.length;
  const activeCount = activeMembers.length;

  if (votingMode === "solo") {
    return "Your pick";
  }

  if (votingMode === "consensus") {
    if (
      winnerVotes.length > 0 &&
      activeCount > 0 &&
      winnerVotes.length === activeCount
    ) {
      return `Consensus pick — everyone chose ${plan.selectedMeal}`;
    }
    return "Picked by household";
  }

  if (votingMode === "majority") {
    if (winnerVotes.length > 0 && totalRealVotes > 0) {
      return `Majority pick — ${winnerVotes.length} of ${totalRealVotes} voted ${plan.selectedMeal}`;
    }
    return "Picked by household";
  }

  if (votingMode === "hierarchical") {
    const decider = pickHierarchicalDecider(winnerVotes, activeMembers);
    if (decider) return `${decider}'s pick`;
    return "Decision-maker's pick";
  }

  return "Picked by household";
}

/**
 * In hierarchical households the decision-maker is conventionally a
 * `parent` role. When multiple parents voted for the winner, return
 * the first parent name; otherwise fall back to the first winning
 * voter we have a name for.
 */
function pickHierarchicalDecider(
  winnerVotes: MealVote[],
  members: Pick<HouseholdMember, "id" | "name" | "role">[],
): string | undefined {
  const memberById = new Map(members.map((m) => [m.id, m] as const));
  for (const v of winnerVotes) {
    const m = memberById.get(v.memberId);
    if (m?.role === "parent") return splitFirstName(v.memberName);
  }
  if (winnerVotes.length > 0) return splitFirstName(winnerVotes[0].memberName);
  return undefined;
}

function splitFirstName(name: string): string {
  return name.trim().split(/\s+/)[0] || name;
}

/**
 * Format the soft-lock countdown for human display. Returns labels
 * like "5 min" / "1 min" / "<1 min". Used by the day-detail modal's
 * tentative state copy.
 */
export function minutesUntil(iso: string | undefined, now: number = Date.now()): number | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  if (!Number.isFinite(t)) return null;
  const ms = t - now;
  if (ms <= 0) return 0;
  return Math.ceil(ms / 60000);
}

/**
 * "7:30 PM" style local-time formatter for the lock-in deadline.
 */
export function formatLocalClock(iso: string | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleTimeString("en-IN", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
}
