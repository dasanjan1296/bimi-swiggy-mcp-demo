/**
 * useMealHistory — react-query hook for the cross-device meal-history
 * feed that backs the meals-history calendar + past-day modal.
 *
 * Backend route: GET /api/families/{family_id}/meal-history?from=&to=
 * (router lives at `[bimi/backend/app/routers/meal_history.py]`).
 *
 * The query key includes `from` / `to` so the same hook can power
 * different month panes without thrashing each other's caches. The
 * meals-history screen typically pulls a 60-day window once at mount;
 * `useLiveSync` separately keeps a smaller "last 30 days" window
 * fresh on the 30 s background poll.
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { client } from "./api";
import type { MealHistoryEntry, MealType } from "./types";

// Backend wire shape — snake_case. The hook converts to the FE
// camelCase `MealHistoryEntry` so screens never see raw server keys.
interface BackendHistoryVote {
  member_id: string;
  member_name: string;
  dish_name: string;
  rating: number;
  is_proxy: boolean;
}

interface BackendHistoryRating {
  member_id: string;
  rating: number;
}

interface BackendHistoryEntry {
  date: string;
  meal_type: string;
  selected_meal: string;
  finalized_by_proxy: boolean;
  participant_ids: string[];
  votes: BackendHistoryVote[];
  ratings: BackendHistoryRating[];
}

function fromBackend(e: BackendHistoryEntry): MealHistoryEntry {
  return {
    date: e.date,
    mealType: e.meal_type as MealType,
    selectedMeal: e.selected_meal,
    participantIds: e.participant_ids ?? [],
    votes: (e.votes ?? []).map((v) => ({
      memberId: v.member_id,
      dishName: v.dish_name,
      rating: v.rating,
      isProxy: v.is_proxy,
    })),
    ratings: (e.ratings ?? []).map((r) => ({
      memberId: r.member_id,
      rating: r.rating,
    })),
  };
}

const historyKey = (familyId: string, from: string, to: string) => [
  "meal-history",
  familyId,
  from,
  to,
];

export interface UseMealHistoryOpts {
  familyId: string | undefined;
  /** ISO yyyy-mm-dd, inclusive. */
  from: string | undefined;
  /** ISO yyyy-mm-dd, inclusive. */
  to: string | undefined;
  /** Override the default 60s staleTime — useful when the screen knows
   *  the data is volatile (e.g. immediately after a vote/finalize). */
  staleTime?: number;
}

export function useMealHistory(opts: UseMealHistoryOpts) {
  const { familyId, from, to, staleTime = 60_000 } = opts;
  return useQuery({
    queryKey: familyId && from && to
      ? historyKey(familyId, from, to)
      : ["meal-history-disabled"],
    queryFn: async (): Promise<MealHistoryEntry[]> => {
      if (!familyId || !from || !to) return [];
      const { data } = await client.get<BackendHistoryEntry[]>(
        `/families/${familyId}/meal-history`,
        { params: { from, to } },
      );
      return (data ?? []).map(fromBackend);
    },
    enabled: !!familyId && !!from && !!to,
    staleTime,
  });
}

// ── Rating mutation (server-side natural key) ───────────────────────
// The legacy `POST /meals/{plan_id}/feedback` required the server's
// MealLog UUID, which the FE never had — every call 404'd. The new
// `POST /meals/feedback` keys on (family, date, meal_type, dish,
// member) so the FE can submit ratings using only what the user sees.

export interface RateMealInput {
  familyId: string;
  memberId: string;
  memberName: string;
  /** ISO yyyy-mm-dd. */
  mealDate: string;
  mealType: MealType;
  dishName: string;
  rating: number;
  feedback?: string;
}

export function useRateMeal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: RateMealInput) => {
      const { data } = await client.post("/meals/feedback", {
        family_id: input.familyId,
        member_id: input.memberId,
        member_name: input.memberName,
        meal_date: input.mealDate,
        meal_type: input.mealType,
        dish_name: input.dishName,
        rating: input.rating,
        feedback: input.feedback,
      });
      return data;
    },
    onSuccess: (_data, vars) => {
      // Invalidate every meal-history pane for this family so the
      // updated rating appears in the calendar + modal on the next
      // render.
      qc.invalidateQueries({ queryKey: ["meal-history", vars.familyId] });
    },
  });
}
