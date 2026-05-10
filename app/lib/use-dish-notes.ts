/**
 * useDishNotes — react-query hooks for the household-shared dish-note
 * catalog. Two read paths and three write paths:
 *
 *   • useDishNotesForDish({ familyId, dishName })  — cook-brief style
 *   • useDishNotesForDate({ familyId, date })      — past-day modal
 *   • useCreateDishNote()                          — pencil → save
 *   • usePatchDishNote()                           — author-only edit
 *   • useDeleteDishNote()                          — author-only soft delete
 *
 * Backend route: GET/POST/PATCH/DELETE /api/dish-notes (router lives
 * at `[bimi/backend/app/routers/dish_notes.py]`). The shape this hook
 * returns mirrors `DishNoteOut` snake_case → camelCase so the FE never
 * sees raw server keys.
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { client } from "./api";
import type { MealType } from "./types";

export type DishNoteMealType = Exclude<MealType, "snack"> | "snack";

export interface DishNote {
  id: string;
  familyId: string;
  authorName: string;
  dishName: string;
  mealType: DishNoteMealType | null;
  sourceDate: string;
  noteText: string;
  isActive: boolean;
}

interface BackendDishNote {
  id: string;
  family_id: string;
  author_name: string;
  dish_name: string;
  meal_type: DishNoteMealType | null;
  source_date: string;
  note_text: string;
  is_active: boolean;
}

function fromBackend(n: BackendDishNote): DishNote {
  return {
    id: n.id,
    familyId: n.family_id,
    authorName: n.author_name,
    dishName: n.dish_name,
    mealType: n.meal_type,
    sourceDate: n.source_date,
    noteText: n.note_text,
    isActive: n.is_active,
  };
}

// ── Query keys ───────────────────────────────────────────────────────

const notesKey = (familyId: string, scope: Record<string, string>) => [
  "dish-notes",
  familyId,
  scope,
];

// ── Read: by dish ────────────────────────────────────────────────────

export function useDishNotesForDish(opts: {
  familyId: string | undefined;
  dishName: string | undefined;
}) {
  const { familyId, dishName } = opts;
  return useQuery({
    queryKey: familyId && dishName
      ? notesKey(familyId, { dish: dishName })
      : ["dish-notes-disabled"],
    queryFn: async (): Promise<DishNote[]> => {
      if (!familyId || !dishName) return [];
      const { data } = await client.get<BackendDishNote[]>(
        "/dish-notes",
        { params: { family_id: familyId, dish_name: dishName } },
      );
      return (data ?? []).map(fromBackend);
    },
    enabled: !!familyId && !!dishName,
    staleTime: 60 * 1000,
  });
}

// ── Read: by date ────────────────────────────────────────────────────

export function useDishNotesForDate(opts: {
  familyId: string | undefined;
  date: string | undefined;
}) {
  const { familyId, date } = opts;
  return useQuery({
    queryKey: familyId && date
      ? notesKey(familyId, { date })
      : ["dish-notes-disabled"],
    queryFn: async (): Promise<DishNote[]> => {
      if (!familyId || !date) return [];
      const { data } = await client.get<BackendDishNote[]>(
        "/dish-notes",
        { params: { family_id: familyId, date } },
      );
      return (data ?? []).map(fromBackend);
    },
    enabled: !!familyId && !!date,
    staleTime: 60 * 1000,
  });
}

// ── Write: create ────────────────────────────────────────────────────

export interface CreateDishNoteInput {
  familyId: string;
  authorName: string;
  dishName: string;
  mealType?: DishNoteMealType | null;
  sourceDate: string;
  noteText: string;
}

export function useCreateDishNote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: CreateDishNoteInput): Promise<DishNote> => {
      const body: Record<string, unknown> = {
        family_id: input.familyId,
        author_name: input.authorName,
        dish_name: input.dishName,
        source_date: input.sourceDate,
        note_text: input.noteText,
      };
      if (input.mealType) body.meal_type = input.mealType;
      const { data } = await client.post<BackendDishNote>(
        "/dish-notes",
        body,
      );
      return fromBackend(data);
    },
    onSuccess: (note) => {
      // Invalidate every cached `dish-notes` query for this family —
      // simpler than trying to surgically update both date + dish
      // scoped caches, and notes are a low-volume surface.
      qc.invalidateQueries({ queryKey: ["dish-notes", note.familyId] });
    },
  });
}

// ── Write: patch ─────────────────────────────────────────────────────

export interface PatchDishNoteInput {
  id: string;
  familyId: string;
  authorName: string; // soft-auth byline match
  noteText: string;
}

export function usePatchDishNote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: PatchDishNoteInput): Promise<DishNote> => {
      const { data } = await client.patch<BackendDishNote>(
        `/dish-notes/${input.id}`,
        { note_text: input.noteText },
        { params: { author_name: input.authorName } },
      );
      return fromBackend(data);
    },
    onSuccess: (note) => {
      qc.invalidateQueries({ queryKey: ["dish-notes", note.familyId] });
    },
  });
}

// ── Write: delete ────────────────────────────────────────────────────

export function useDeleteDishNote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      id: string;
      familyId: string;
      authorName: string;
    }): Promise<void> => {
      await client.delete(`/dish-notes/${input.id}`, {
        params: { author_name: input.authorName },
      });
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["dish-notes", vars.familyId] });
    },
  });
}
