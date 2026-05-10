/**
 * useSavedRecipes — react-query hooks for the household-curated
 * recipe catalog backing the home "Self cook ideas" sheet's "Your
 * recipes" section and the Settings management screen.
 *
 * Backend route: GET/POST/PATCH/DELETE /api/saved-recipes
 *
 * Result shape mirrors `QuickRecipe` from `lib/quick-recipes.ts` (with
 * a few extra fields like `notes` / `createdByName`) so the
 * SelfCookSheet can render saved + curated entries with one card
 * component.
 */

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { client } from "./api";
import type { MealType } from "./types";

export type SavedRecipeCourse = MealType | "any";
export type SavedRecipeSourcePlatform = "youtube" | "instagram" | "web";

/**
 * Backend response shape (snake_case, matches Pydantic).
 */
interface BackendSavedRecipe {
  id: string;
  family_id: string;
  created_by_name: string | null;
  source_url: string;
  source_platform: SavedRecipeSourcePlatform;
  title: string;
  description: string | null;
  image_url: string | null;
  notes: string | null;
  course: SavedRecipeCourse;
  total_time_mins: number | null;
  tags: string[] | null;
  is_active: boolean;
}

/**
 * camelCase shape consumed by the FE. Mirrors the slim `QuickRecipe`
 * shape so a single card component can render both seed + saved.
 */
export interface SavedRecipe {
  id: string;
  familyId: string;
  createdByName: string | null;
  sourceUrl: string;
  sourcePlatform: SavedRecipeSourcePlatform;
  title: string;
  description: string | null;
  imageUrl: string | null;
  notes: string | null;
  course: SavedRecipeCourse;
  totalTimeMins: number | null;
  tags: string[] | null;
  isActive: boolean;
}

function fromBackend(r: BackendSavedRecipe): SavedRecipe {
  return {
    id: r.id,
    familyId: r.family_id,
    createdByName: r.created_by_name,
    sourceUrl: r.source_url,
    sourcePlatform: r.source_platform,
    title: r.title,
    description: r.description,
    imageUrl: r.image_url,
    notes: r.notes,
    course: r.course,
    totalTimeMins: r.total_time_mins,
    tags: r.tags,
    isActive: r.is_active,
  };
}

// ── Query keys ───────────────────────────────────────────────────────

const recipesQueryKey = (familyId: string, course?: SavedRecipeCourse) =>
  course ? ["saved-recipes", familyId, course] : ["saved-recipes", familyId];

// ── List ─────────────────────────────────────────────────────────────

export function useSavedRecipes(opts: {
  familyId: string | undefined;
  course?: SavedRecipeCourse;
}) {
  const { familyId, course } = opts;
  return useQuery({
    queryKey: familyId ? recipesQueryKey(familyId, course) : ["saved-recipes-disabled"],
    queryFn: async (): Promise<SavedRecipe[]> => {
      if (!familyId) return [];
      const params: Record<string, string> = { family_id: familyId };
      if (course) params.course = course;
      const { data } = await client.get<BackendSavedRecipe[]>(
        "/saved-recipes",
        { params },
      );
      return (data ?? []).map(fromBackend);
    },
    enabled: !!familyId,
    staleTime: 60 * 1000,
  });
}

// ── Create ───────────────────────────────────────────────────────────

export interface CreateSavedRecipeInput {
  familyId: string;
  sourceUrl: string;
  createdByName?: string | null;
  title?: string | null;
  description?: string | null;
  imageUrl?: string | null;
  notes?: string | null;
  course?: SavedRecipeCourse;
  totalTimeMins?: number | null;
  tags?: string[] | null;
}

export function useCreateSavedRecipe() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: CreateSavedRecipeInput): Promise<SavedRecipe> => {
      // Map camelCase → snake_case + drop undefined keys so the server's
      // partial-required validation (e.g. title required for non-YT)
      // sees a clean payload.
      const body: Record<string, unknown> = {
        family_id: input.familyId,
        source_url: input.sourceUrl,
        course: input.course ?? "any",
      };
      if (input.createdByName != null) body.created_by_name = input.createdByName;
      if (input.title != null) body.title = input.title;
      if (input.description != null) body.description = input.description;
      if (input.imageUrl != null) body.image_url = input.imageUrl;
      if (input.notes != null) body.notes = input.notes;
      if (input.totalTimeMins != null) body.total_time_mins = input.totalTimeMins;
      if (input.tags != null) body.tags = input.tags;

      const { data } = await client.post<BackendSavedRecipe>(
        "/saved-recipes",
        body,
      );
      return fromBackend(data);
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["saved-recipes", vars.familyId] });
    },
  });
}

// ── Patch ────────────────────────────────────────────────────────────

export interface PatchSavedRecipeInput {
  id: string;
  familyId: string;
  title?: string | null;
  description?: string | null;
  imageUrl?: string | null;
  notes?: string | null;
  course?: SavedRecipeCourse;
  totalTimeMins?: number | null;
  tags?: string[] | null;
}

export function usePatchSavedRecipe() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: PatchSavedRecipeInput): Promise<SavedRecipe> => {
      const body: Record<string, unknown> = {};
      if (input.title !== undefined) body.title = input.title;
      if (input.description !== undefined) body.description = input.description;
      if (input.imageUrl !== undefined) body.image_url = input.imageUrl;
      if (input.notes !== undefined) body.notes = input.notes;
      if (input.course !== undefined) body.course = input.course;
      if (input.totalTimeMins !== undefined) body.total_time_mins = input.totalTimeMins;
      if (input.tags !== undefined) body.tags = input.tags;

      const { data } = await client.patch<BackendSavedRecipe>(
        `/saved-recipes/${input.id}`,
        body,
      );
      return fromBackend(data);
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["saved-recipes", vars.familyId] });
    },
  });
}

// ── Delete ───────────────────────────────────────────────────────────

export function useDeleteSavedRecipe() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: { id: string; familyId: string }): Promise<void> => {
      await client.delete(`/saved-recipes/${input.id}`);
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["saved-recipes", vars.familyId] });
    },
  });
}

// ── Helpers ──────────────────────────────────────────────────────────

const _YOUTUBE_HOST_RE = /^(?:https?:\/\/)?(?:www\.|m\.)?(?:youtube\.com|youtu\.be|youtube-nocookie\.com)\//i;
const _INSTAGRAM_HOST_RE = /^(?:https?:\/\/)?(?:www\.)?instagram\.com\//i;

/**
 * Local platform detection mirroring the server's `detect_platform`.
 * The AddRecipeSheet uses this to decide whether the user MUST type a
 * title (Instagram / web) or whether the server's oEmbed will cover
 * it (YouTube). Server still re-detects authoritatively at insert.
 */
export function detectRecipePlatform(url: string): SavedRecipeSourcePlatform {
  const trimmed = url.trim();
  if (_YOUTUBE_HOST_RE.test(trimmed)) return "youtube";
  if (_INSTAGRAM_HOST_RE.test(trimmed)) return "instagram";
  return "web";
}

/** Extract the YouTube video ID from a URL, or null if none. */
export function extractYouTubeId(url: string): string | null {
  const match = url.match(
    /(?:youtu\.be\/|youtube\.com\/(?:watch\?v=|embed\/|shorts\/|v\/))([\w-]{11})/,
  );
  return match ? match[1] : null;
}
