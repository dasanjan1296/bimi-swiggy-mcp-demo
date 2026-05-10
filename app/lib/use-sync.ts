import { useEffect, useRef } from "react";
import { AppState, AppStateStatus } from "react-native";
import { useAuthStore } from "./auth-store";
import { DEMO_TOKEN } from "./auth-flags";
import { client, mapAbsenceFromApi } from "./api";
import {
  useCookAbsenceStore,
  useMealStore,
  useOrderStore,
  useInventoryStore,
  useGuestStore,
} from "./store";
import type { MealHistoryEntry, MealType } from "./types";

async function safeFetch<T>(path: string, fallback: T): Promise<T> {
  try {
    const { data } = await client.get(path);
    return data as T;
  } catch {
    return fallback;
  }
}

// Backend wire shape — kept local because nothing else in this file
// needs to know about it. See `lib/use-meal-history.ts` for the
// equivalent react-query-driven path used by the modal.
interface BackendHistoryEntry {
  date: string;
  meal_type: string;
  selected_meal: string;
  finalized_by_proxy: boolean;
  participant_ids: string[];
  votes: {
    member_id: string;
    member_name: string;
    dish_name: string;
    rating: number;
    is_proxy: boolean;
  }[];
  ratings: { member_id: string; rating: number }[];
}

function historyFromBackend(e: BackendHistoryEntry): MealHistoryEntry {
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

function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

export function useLiveSync() {
  const familyId = useAuthStore((s) => s.familyId);
  const token = useAuthStore((s) => s.token);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!familyId || !token || token === DEMO_TOKEN) return;

    const poll = async () => {
      // Fixed 30-day window for the background sync. The history screen
      // can ask for a wider span via useMealHistory when the user
      // navigates further back; this poll only keeps the recent slice
      // hot so a vote on Mayank's phone shows up on Anjan's calendar
      // within the next polling tick.
      const from = isoDaysAgo(30);
      const to = isoDaysAgo(0);

      const [inventory, voting, carts, guests, history, absences] = await Promise.all([
        safeFetch<any>(`/inventory`, null),
        safeFetch<any>(`/families/${familyId}/voting/tomorrow`, null),
        safeFetch<any>(`/carts?family_id=${familyId}`, null),
        safeFetch<any>(`/families/${familyId}/guests`, null),
        safeFetch<BackendHistoryEntry[] | null>(
          `/families/${familyId}/meal-history?from=${from}&to=${to}`,
          null,
        ),
        // 90-day window matches backend `get_absences` cap. The mobile
        // calendar reads ~14 days back + 14 forward; 90 covers any
        // long-tail history view (the meal-history modal goes deeper).
        safeFetch<any[] | null>(`/absences?days=90`, null),
      ]);

      if (inventory && Array.isArray(inventory)) {
        useInventoryStore.getState().setItemsFromBackend(inventory);
      }

      if (voting?.suggestions) {
        useMealStore.getState().setSuggestionsFromBackend(voting.suggestions);
      }

      if (carts && Array.isArray(carts)) {
        useOrderStore.getState().setOrdersFromBackend(carts);
      }

      if (guests && Array.isArray(guests)) {
        const setter = (useGuestStore.getState() as any).setGuestsFromBackend;
        if (typeof setter === "function") setter(guests);
      }

      if (history && Array.isArray(history)) {
        useMealStore.getState().setMealHistoryFromBackend(
          history.map(historyFromBackend),
        );
      }

      if (absences && Array.isArray(absences)) {
        // Server wins for ids it knows about; local `weekly:*` synthetic
        // absences and `temp-*` in-flight POSTs survive the merge. See
        // useCookAbsenceStore.hydrateFromBackend.
        useCookAbsenceStore
          .getState()
          .hydrateFromBackend(absences.map(mapAbsenceFromApi));
      }
    };

    poll();
    intervalRef.current = setInterval(poll, 30000);

    const handleAppState = (state: AppStateStatus) => {
      if (state === "active") poll();
    };
    const sub = AppState.addEventListener("change", handleAppState);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
      sub.remove();
    };
  }, [familyId, token]);
}
