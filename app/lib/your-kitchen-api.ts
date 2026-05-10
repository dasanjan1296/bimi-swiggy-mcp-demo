/**
 * Your Kitchen — API client + types (PRD §4.13).
 *
 * Mirrors `bimi/backend/app/routers/your_kitchen.py`. The shape is the
 * household's lived history with each dish: per-member reactions, last-served,
 * peculiarities, and queue state. Surfaced on the Your Kitchen screen.
 *
 * All routes are family-scoped via JWT — no `family_id` ever travels in the
 * client request. Use `useYourKitchen()` for the canon hook (with TanStack
 * Query caching) or call the raw `fetchCanon()` etc. for one-off reads.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { client } from "./api";
import {
  initialsFor,
  relativeServedLabel,
  sortReactionsForDisplay,
  type MemberReaction,
  type Sentiment,
} from "./your-kitchen-helpers";

export {
  initialsFor,
  relativeServedLabel,
  sortReactionsForDisplay,
  type MemberReaction,
  type Sentiment,
};

// ─── Types (mirror backend pydantic schemas) ─────────────────────────────────

export type DishHouseholdFacts = {
  dish_id: string;
  slug: string;
  name: string;
  image_url: string | null;
  cuisine: string;
  is_veg: boolean;
  base_time_minutes: number;
  inspired_by_chef?: string;
  inspired_by_url?: string;

  times_made: number;
  last_served_at: string | null;
  days_since_last_served: number | null;
  last_rating: number | null;

  reactions: MemberReaction[];
  love_count: number;
  like_count: number;
  dislike_count: number;
  untried_count: number;

  in_cook_repertoire: boolean;
  cook_learned_recently: boolean;

  pinned_note: string | null;
  note_count: number;
  family_pref_summary: string | null;

  is_queued: boolean;
  queued_by_name: string | null;
  queued_at: string | null;
};

export type CanonSection = {
  id: string;
  title: string;
  subtitle: string | null;
  dishes: DishHouseholdFacts[];
};

export type CanonResponse = {
  sections: CanonSection[];
  has_canon: boolean;
  total_dishes: number;
};

export type QueueEntry = {
  id: string;
  dish_id: string;
  slug: string;
  name: string;
  queued_by_person_id: string | null;
  meal_type: string | null;
  note: string | null;
  status: string;
  expires_at: string;
  created_at: string;
};

export type Note = {
  id: string;
  dish_id: string;
  body: string;
  pinned: boolean;
  author_person_id: string | null;
  created_at: string;
  updated_at: string;
};

// ─── Raw API calls ───────────────────────────────────────────────────────────

export async function fetchCanon(): Promise<CanonResponse> {
  const { data } = await client.get<CanonResponse>("/your-kitchen");
  return data;
}

export async function fetchDishFacts(slugOrId: string): Promise<DishHouseholdFacts> {
  const { data } = await client.get<DishHouseholdFacts>(
    `/your-kitchen/dish/${encodeURIComponent(slugOrId)}`,
  );
  return data;
}

export async function addToQueue(input: {
  dish_id?: string;
  slug?: string;
  meal_type?: string;
  note?: string;
}): Promise<QueueEntry> {
  const { data } = await client.post<QueueEntry>("/your-kitchen/queue", input);
  return data;
}

export async function removeFromQueue(queueId: string): Promise<void> {
  await client.delete(`/your-kitchen/queue/${encodeURIComponent(queueId)}`);
}

export async function listQueue(): Promise<QueueEntry[]> {
  const { data } = await client.get<QueueEntry[]>("/your-kitchen/queue");
  return data;
}

export async function upsertNote(input: {
  dish_id?: string;
  slug?: string;
  body: string;
  pinned?: boolean;
  household_only?: boolean;
}): Promise<Note> {
  const { data } = await client.post<Note>("/your-kitchen/notes", input);
  return data;
}

export async function listNotes(slugOrId: string): Promise<Note[]> {
  const { data } = await client.get<Note[]>(
    `/your-kitchen/notes/${encodeURIComponent(slugOrId)}`,
  );
  return data;
}

export async function deleteNote(noteId: string): Promise<void> {
  await client.delete(`/your-kitchen/notes/${encodeURIComponent(noteId)}`);
}

export async function react(input: {
  dish_id?: string;
  slug?: string;
  sentiment: Sentiment;
  person_id: string;
}): Promise<void> {
  await client.post("/your-kitchen/react", input);
}

// ─── Hooks ────────────────────────────────────────────────────────────────────

const CANON_KEY = ["your-kitchen", "canon"] as const;
const dishFactsKey = (slugOrId: string) => ["your-kitchen", "dish", slugOrId] as const;

export function useYourKitchen() {
  return useQuery<CanonResponse>({
    queryKey: CANON_KEY,
    queryFn: fetchCanon,
    staleTime: 30_000,
    // Day-zero is a normal state — don't retry forever.
    retry: 1,
  });
}

export function useDishFacts(slugOrId: string | undefined | null) {
  return useQuery<DishHouseholdFacts>({
    queryKey: dishFactsKey(slugOrId ?? ""),
    queryFn: () => fetchDishFacts(slugOrId!),
    enabled: !!slugOrId,
    staleTime: 30_000,
  });
}

/** Adds to queue and optimistically updates the canon view. */
export function useAddToQueue() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: addToQueue,
    onMutate: async (input) => {
      await qc.cancelQueries({ queryKey: CANON_KEY });
      const previous = qc.getQueryData<CanonResponse>(CANON_KEY);
      // Optimistically flip is_queued on the matching dish in every section.
      qc.setQueryData<CanonResponse>(CANON_KEY, (prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          sections: prev.sections.map((s) => ({
            ...s,
            dishes: s.dishes.map((d) =>
              d.slug === input.slug || d.dish_id === input.dish_id
                ? { ...d, is_queued: true, queued_at: new Date().toISOString() }
                : d,
            ),
          })),
        };
      });
      return { previous };
    },
    onError: (_err, _input, ctx) => {
      // Roll back on failure — Query's optimistic update lifecycle.
      if (ctx?.previous) qc.setQueryData(CANON_KEY, ctx.previous);
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: CANON_KEY });
    },
  });
}

export function useRemoveFromQueue() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: removeFromQueue,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: CANON_KEY });
    },
  });
}

export function useReact() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: react,
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: CANON_KEY });
      const slug = vars.slug ?? vars.dish_id;
      if (slug) qc.invalidateQueries({ queryKey: dishFactsKey(slug) });
    },
  });
}

export function useUpsertNote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: upsertNote,
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: CANON_KEY });
      const slug = vars.slug ?? vars.dish_id;
      if (slug) qc.invalidateQueries({ queryKey: dishFactsKey(slug) });
    },
  });
}

// (Pure helpers live in `./your-kitchen-helpers` so unit tests can import
// them without dragging in axios + React Query + RN modules.)
