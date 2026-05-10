import axios from "axios";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useAuthStore } from "./auth-store";
import { isDemoMode, isRealAuth } from "./auth-flags";
import { errorCopyFor, ERR } from "./copy";
import { API_BASE, API_HOST } from "./api-config";
import type {
  Order,
  AutoApprovalRule,
  CookAbsenceEvent,
  CookAbsenceFallback,
  InventoryItem,
  MealVote,
  FairnessScore,
} from "./types";

// Re-export so existing call sites don't have to change their import path.
export { API_HOST };

export const client = axios.create({
  baseURL: API_BASE,
  timeout: 15000,
  headers: { "Content-Type": "application/json" },
});

client.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

client.interceptors.response.use(
  (response) => response,
  (error) => {
    // Only log out on 401 for real sessions. Demo mode returns 401 from
    // any authed endpoint because "demo-token" isn't recognized server-side;
    // per-hook demo fallbacks handle that case gracefully, and logging the
    // user out boots them back to the login screen mid-flow.
    //
    // Dev builds also skip auto-logout so dev-auto-login (lib/dev-auto-login.ts)
    // has a deterministic chance to refresh the token without the races
    // caused by a stale AsyncStorage-loaded JWT triggering logout before it runs.
    if (error.response?.status === 401 && !isDemoMode() && !__DEV__) {
      useAuthStore.getState().logout();
    }
    // IC-P2-07: attach a friendly Hinglish copy string so per-screen catch
    // blocks can show `e.userMessage` directly to the elder persona instead
    // of "Request failed with status code 500". The original Error stays
    // intact for debugging + Sentry.
    try {
      const code = error.response?.data?.code as string | undefined;
      const friendly = code && code in ERR
        ? (ERR as Record<string, string>)[code]
        : errorCopyFor(error);
      (error as any).userMessage = friendly;
    } catch {
      (error as any).userMessage = ERR.unknown;
    }
    return Promise.reject(error);
  }
);

// ─── Auth ───

export async function sendOtp(phone: string) {
  const { data } = await client.post("/families/auth/send-otp", { phone });
  return data as { status: string; phone: string; dev_otp?: string };
}

export async function verifyOtp(phone: string, otp: string) {
  const { data } = await client.post("/families/auth/verify-otp", { phone, otp });
  return data as {
    status: string;
    is_new_user: boolean;
    access_token?: string;
    pending_token?: string;
    token_type?: string;
    child_id?: string;
    family_id?: string;
    child_name?: string;
    phone?: string;
  };
}

export async function completeProfile(pendingToken: string, name: string, householdType: string = "household") {
  const { data } = await client.post(
    "/families/auth/complete-profile",
    { name, household_type: householdType },
    { headers: { Authorization: `Bearer ${pendingToken}` } },
  );
  return data as {
    status: string;
    access_token: string;
    child_id: string;
    family_id: string;
    child_name: string;
  };
}

export async function loginApi(phone: string, password: string) {
  const { data } = await client.post("/families/auth/token", { phone, password });
  return {
    access_token: data.access_token as string,
    family_id: data.family_id as string,
    child_id: data.child_id as string,
    child_name: (data.child_name || data.name || phone) as string,
  };
}

export async function registerApi(phone: string, password: string, name: string) {
  const { data } = await client.post("/families/auth/register", { phone, password, name });
  return {
    access_token: data.access_token as string,
    family_id: data.family_id as string,
    child_id: data.child_id as string,
    child_name: (data.child_name || name) as string,
  };
}

export async function requestPasswordReset(phone: string) {
  try {
    await client.post("/families/auth/reset-request", { phone });
    return { success: true, message: "OTP sent to your phone" };
  } catch {
    return { success: true, message: "If this number is registered, an OTP will be sent" };
  }
}

export async function confirmPasswordReset(phone: string, otp: string, newPassword: string) {
  try {
    await client.post("/families/auth/reset-confirm", { phone, otp, new_password: newPassword });
    return { success: true };
  } catch {
    return { success: false };
  }
}

export async function lookupInviteCode(code: string) {
  try {
    const { data } = await client.get(`/households/invite/${code}`);
    return data as { householdId: string; name: string; memberCount: number; cookName?: string; expenseMode: string } | null;
  } catch {
    const { useHouseholdStore } = require("./store");
    const household = useHouseholdStore.getState().household;
    if (household?.inviteCode === code) {
      return {
        householdId: household.id,
        name: household.name,
        memberCount: household.members.filter((m: any) => m.isActive).length,
        cookName: household.cooks?.[0]?.name,
        expenseMode: household.config.expenseMode,
      };
    }
    return null;
  }
}

export async function joinHouseholdApi(code: string, member: { name: string; dietaryPreferences: any[] }) {
  try {
    const { data } = await client.post("/households/join", { code, ...member });
    return data;
  } catch {
    return null;
  }
}

// ─── Auto-Approval Rules ───

export function useAutoRules(familyId: string) {
  return useQuery({
    queryKey: ["auto-rules", familyId],
    queryFn: async () => {
      const { data } = await client.get(`/families/${familyId}/auto-rules`);
      return data as AutoApprovalRule[];
    },
    enabled: !!familyId,
  });
}

export function useCreateRule(familyId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (rule: Partial<AutoApprovalRule>) => {
      const { data } = await client.post(`/families/${familyId}/auto-rules`, rule);
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["auto-rules", familyId] }),
  });
}

export function useDeleteRule(familyId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (ruleId: string) => {
      await client.delete(`/families/${familyId}/auto-rules/${ruleId}`);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["auto-rules", familyId] }),
  });
}

export function useEvaluateOrder(familyId: string) {
  return useMutation({
    mutationFn: async (body: { total_amount: number; item_names: string[] }) => {
      const { data } = await client.post(`/families/${familyId}/auto-rules/evaluate`, body);
      return data as { auto_approve: boolean; reason: string; matching_rule_id?: string };
    },
  });
}

// ─── Voting ───

function mapSuggestion(s: any): import("./types").MealSuggestion {
  return {
    id: s.id,
    dishName: s.dish_name ?? s.dishName,
    confidence: s.confidence ?? 0.5,
    fairnessScore: s.fairness_score ?? s.fairnessScore ?? 0.5,
    noveltyBonus: s.novelty_bonus ?? s.noveltyBonus ?? 0,
    prepTime: s.prep_time ?? s.prepTime ?? "30 min",
    needsAdvancePrep: s.needs_advance_prep ?? s.needsAdvancePrep ?? false,
    advancePrepNote: s.advance_prep_note ?? s.advancePrepNote,
    constraints: (s.constraints || []).map((c: any) =>
      typeof c === "string" ? { description: c, severity: "info" } : c,
    ),
    ingredients: s.ingredients || [],
    missingIngredients: s.missing_ingredients ?? s.missingIngredients ?? [],
    sourceUrl: s.source_url ?? s.sourceUrl,
    sourcePlatform: s.source_platform ?? s.sourcePlatform,
    sourceThumbnail: s.source_thumbnail ?? s.sourceThumbnail,
    suggestedById: s.suggested_by_id ?? s.suggestedById,
    suggestedByName: s.suggested_by_name ?? s.suggestedByName,
    noteForCook: s.note_for_cook ?? s.noteForCook,
  } as import("./types").MealSuggestion;
}

export function useTomorrowSuggestions(familyId: string) {
  return useQuery({
    queryKey: ["voting-tomorrow", familyId],
    queryFn: async () => {
      const { data } = await client.get(`/families/${familyId}/voting/tomorrow`);
      // P4.3: backend ships snake_case; remap to the camelCase shape the
      // frontend expects so the suggestion list, fairness bar, etc. just work.
      const mapped = {
        date: data.date,
        suggestions: Object.fromEntries(
          Object.entries(data.suggestions || {}).map(([mealType, list]: any) => [
            mealType,
            (list as any[]).map(mapSuggestion),
          ]),
        ) as Record<string, import("./types").MealSuggestion[]>,
        votes: data.votes || [],
        fairnessScores: (data.fairness_scores || []).map((f: any) => ({
          memberId: f.member_id ?? f.memberId,
          memberName: f.member_name ?? f.memberName,
          satisfactionScore: f.satisfaction_score ?? f.satisfactionScore ?? 0,
          mealsServed: f.meals_served ?? f.mealsServed ?? 0,
          avgSatisfaction: f.avg_satisfaction ?? f.avgSatisfaction ?? 0,
          isUnderserved: f.is_underserved ?? f.isUnderserved ?? false,
        })),
      };
      return mapped;
    },
    enabled: !!familyId,
  });
}

/**
 * P4.2 (PRD 4.5): backend-driven proxy voting. Posts the list of members
 * who haven't voted yet; receives a synthesized vote for each, scored by
 * `estimate_person_utility` against the active Thompson candidate set.
 */
export function useGenerateProxyVotes(familyId: string) {
  return useMutation({
    mutationFn: async (params: { mealType: string; missingMemberIds: string[] }) => {
      try {
        const { data } = await client.post(
          `/families/${familyId}/voting/proxy`,
          {
            meal_type: params.mealType,
            missing_member_ids: params.missingMemberIds,
          },
        );
        return (data as any[]).map((v) => ({
          memberId: v.member_id ?? v.memberId,
          dishName: v.dish_name ?? v.dishName,
          proxyConfidence: v.proxy_confidence ?? v.proxyConfidence ?? 0.5,
          rationale: v.rationale ?? "",
        }));
      } catch {
        // Fall back to the local heuristic in `useMealStore.generateProxyVotes`.
        return [];
      }
    },
  });
}

export function useSubmitVote(familyId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (vote: {
      member_id: string;
      member_name: string;
      meal_type: string;
      dish_name: string;
      rating: number;
      // Optional — when omitted the server defaults to "tomorrow".
      // Cross-device sync passes the actual target date (yyyy-mm-dd)
      // so future-week votes route to the right row.
      meal_date?: string;
      // AI proxy task sets this true; member-submitted votes leave it
      // false. Surfaces as "AI voted X" in the past-day modal.
      is_proxy?: boolean;
    }) => {
      const { data } = await client.post(`/families/${familyId}/voting/vote`, vote);
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["voting-tomorrow", familyId] });
      qc.invalidateQueries({ queryKey: ["meal-history", familyId] });
    },
  });
}

export function useVotingResults(familyId: string, mealType: string) {
  return useQuery({
    queryKey: ["voting-results", familyId, mealType],
    queryFn: async () => {
      const { data } = await client.get(`/families/${familyId}/voting/results`, {
        params: { meal_type: mealType },
      });
      return data;
    },
    enabled: !!familyId,
  });
}

export function useFinalizePlan(familyId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: {
      meal_type: string;
      dish_name: string;
      dishes: string[];
      // Optional target date (yyyy-mm-dd). Defaults to "tomorrow" on
      // the server when omitted — preserves the legacy contract.
      meal_date?: string;
      // True only when the AI proxy task closes a vote. Member
      // finalisations leave this false.
      finalized_by_proxy?: boolean;
    }) => {
      const { data } = await client.post(`/families/${familyId}/voting/finalize`, body);
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["voting-tomorrow", familyId] });
      qc.invalidateQueries({ queryKey: ["voting-results", familyId] });
      qc.invalidateQueries({ queryKey: ["meal-history", familyId] });
    },
  });
}

// ─── Existing Endpoints (inventory, carts, meals) ───

export function useInventory(familyId: string) {
  return useQuery({
    queryKey: ["inventory", familyId],
    queryFn: async () => {
      const { data } = await client.get(`/families/${familyId}/inventory`);
      return data as InventoryItem[];
    },
    enabled: !!familyId,
  });
}

/* P6 — Orphan-router hookups (inventory CRUD, leftovers, health, recipes, expenses).
   These wrap endpoints that already exist on the backend but had no React Query
   hooks; without these, the kitchen/health/recipe screens couldn't write anything
   to the API. Each hook invalidates the relevant query key on success. */

export function useCreateInventoryItem(familyId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (item: {
      name: string;
      category?: string;
      quantity: number;
      unit: string;
      expiry_date?: string;
    }) => {
      const { data } = await client.post(`/families/${familyId}/inventory`, item);
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["inventory", familyId] }),
  });
}

export function useUpdateInventoryItem(familyId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ itemId, ...patch }: { itemId: string; quantity?: number; expiry_date?: string }) => {
      const { data } = await client.put(`/families/${familyId}/inventory/${itemId}`, patch);
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["inventory", familyId] }),
  });
}

export function useDeleteInventoryItem(familyId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (itemId: string) => {
      await client.delete(`/families/${familyId}/inventory/${itemId}`);
      return itemId;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["inventory", familyId] }),
  });
}

export function useRestockInventory(familyId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (items: Array<{ name: string; quantity: number; unit: string }>) => {
      const { data } = await client.post(`/families/${familyId}/inventory/restock`, { items });
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["inventory", familyId] }),
  });
}

export function useLowStockInventory(familyId: string) {
  return useQuery({
    queryKey: ["inventory-low-stock", familyId],
    queryFn: async () => {
      const { data } = await client.get(`/families/${familyId}/inventory/low-stock`);
      return data as any[];
    },
    enabled: !!familyId,
  });
}

export function useLeftovers(familyId: string) {
  return useQuery({
    queryKey: ["leftovers", familyId],
    queryFn: async () => {
      const { data } = await client.get(`/families/${familyId}/leftovers`);
      return data as any[];
    },
    enabled: !!familyId,
  });
}

export function useConsumeLeftover(familyId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (leftoverId: string) => {
      await client.post(`/families/${familyId}/leftovers/${leftoverId}/consume`);
      return leftoverId;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["leftovers", familyId] }),
  });
}

export function useDisposeLeftover(familyId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (leftoverId: string) => {
      await client.post(`/families/${familyId}/leftovers/${leftoverId}/dispose`);
      return leftoverId;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["leftovers", familyId] }),
  });
}

export function useHealthMetrics(familyId: string, personId?: string) {
  return useQuery({
    queryKey: ["health-metrics", familyId, personId],
    queryFn: async () => {
      const params = personId ? { person_id: personId } : {};
      const { data } = await client.get(`/families/${familyId}/health/metrics`, { params });
      return data as any[];
    },
    enabled: !!familyId,
  });
}

export function useAddHealthMetric(familyId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (metric: {
      person_id: string;
      metric_type: string;
      value: number;
      unit: string;
      date_recorded?: string;
      source?: string;
    }) => {
      const { data } = await client.post(`/families/${familyId}/health/metrics`, metric);
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["health-metrics", familyId] }),
  });
}

export function useFamilyRecipes(familyId: string) {
  return useQuery({
    queryKey: ["recipes", familyId],
    queryFn: async () => {
      const { data } = await client.get(`/families/${familyId}/recipes`);
      return data as any[];
    },
    enabled: !!familyId,
  });
}

export function useRecipesForDish(familyId: string, dishName: string) {
  return useQuery({
    queryKey: ["recipes-for-dish", familyId, dishName],
    queryFn: async () => {
      const { data } = await client.get(`/families/${familyId}/recipes/for-dish/${encodeURIComponent(dishName)}`);
      return data as any[];
    },
    enabled: !!familyId && !!dishName,
  });
}

export function useExpensesSummary(familyId: string, month: string) {
  return useQuery({
    queryKey: ["expenses-summary", familyId, month],
    queryFn: async () => {
      const { data } = await client.get(`/families/${familyId}/expenses/summary/${month}`);
      return data as any;
    },
    enabled: !!familyId && !!month,
  });
}

export function useSettleExpense(familyId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (params: { from_member_id: string; to_member_id: string; amount: number }) => {
      const { data } = await client.post(`/families/${familyId}/expenses/settle`, params);
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["expenses-summary", familyId] }),
  });
}

export function useEvaluateAutoRules(familyId: string) {
  return useMutation({
    // 2026-05-03 audit fix: the backend accepts `{total_amount, item_names: string[]}`.
    // The previous frontend sent `{items: [{name, estimated_price}]}` which the backend
    // silently ignored — the trusted-items rule never matched because the
    // `item_names` array arrived empty. Translate at the boundary so callers
    // can keep their existing object shape.
    mutationFn: async (params: {
      items: Array<{ name: string; estimated_price?: number }>;
      total_amount: number;
    }) => {
      const body = {
        total_amount: params.total_amount,
        item_names: params.items.map((i) => i.name),
      };
      const { data } = await client.post(`/families/${familyId}/auto-rules/evaluate`, body);
      return data as { auto_approve: boolean; reason: string; matching_rule_id?: string };
    },
  });
}

export function useCarts(familyId: string) {
  return useQuery({
    queryKey: ["carts", familyId],
    queryFn: async () => {
      // 2026-05-03 audit fix: backend route is `GET /carts/` (with trailing
      // slash). Without the slash FastAPI would 307-redirect, which axios
      // follows but at the cost of an extra round-trip per refresh — and
      // breaks request signing in some proxy configurations.
      const { data } = await client.get(`/carts/`, { params: { family_id: familyId } });
      return data as Order[];
    },
    enabled: !!familyId,
    refetchInterval: 15000,
  });
}

export function useApproveCart(familyId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ cartId, childId }: { cartId: string; childId: string }) => {
      const { data } = await client.post(`/carts/${cartId}/approve`, { child_id: childId });
      return data;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["carts", familyId] }),
  });
}

export function useMealSuggestions(familyId: string) {
  return useQuery({
    queryKey: ["meal-suggestions", familyId],
    queryFn: async () => {
      const { data } = await client.get(`/meals/suggest`, { params: { family_id: familyId } });
      return data;
    },
    enabled: !!familyId,
  });
}

// ─── Standing Instructions ───

export function useInstructions(familyId: string) {
  return useQuery({
    queryKey: ["instructions", familyId],
    queryFn: async () => {
      const { data } = await client.get(`/families/${familyId}/instructions`, {
        params: { status: "active" },
      });
      return data as Array<{
        id: string;
        family_id: string;
        created_by_type: string;
        created_by_id: string;
        target_role: string;
        instruction_text: string;
        structured_action: any;
        recurrence: any;
        category: string;
        priority: string;
        status: string;
        compliance_count: number;
        skip_count: number;
        compliance_rate: number;
        created_at: string;
      }>;
    },
    enabled: !!familyId,
  });
}

export function useTodaysInstructions(familyId: string) {
  return useQuery({
    queryKey: ["instructions-today", familyId],
    queryFn: async () => {
      const { data } = await client.get(`/families/${familyId}/instructions/today`);
      return data as Array<{
        id: string;
        instruction_text: string;
        category: string;
        priority: string;
        compliance_rate: number;
        recurrence: any;
        structured_action: any;
      }>;
    },
    enabled: !!familyId,
  });
}

export function useCreateInstruction(familyId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: { raw_text: string; created_by_type?: string; created_by_id?: string; target_role?: string }) => {
      const { data } = await client.post(`/families/${familyId}/instructions`, body);
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["instructions", familyId] });
      qc.invalidateQueries({ queryKey: ["instructions-today", familyId] });
    },
  });
}

export function useUpdateInstruction(familyId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ instructionId, ...body }: { instructionId: string; status?: string; priority?: string }) => {
      const { data } = await client.patch(`/families/${familyId}/instructions/${instructionId}`, body);
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["instructions", familyId] });
      qc.invalidateQueries({ queryKey: ["instructions-today", familyId] });
    },
  });
}

export function useRecordCompliance(familyId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ instructionId, completed }: { instructionId: string; completed: boolean }) => {
      const { data } = await client.post(`/families/${familyId}/instructions/${instructionId}/compliance`, { completed });
      return data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["instructions", familyId] });
      qc.invalidateQueries({ queryKey: ["instructions-today", familyId] });
    },
  });
}

// ─── Push Notifications ───

export async function registerPushToken(familyId: string, childId: string, fcmToken: string) {
  // P3 fix: backend exposes this as PUT (see family.py L300). Was POST → 405.
  // 2026-05-03 audit fix: URL was `/families/${familyId}/children/${childId}/fcm-token`
  // but the backend route is `PUT /families/children/{child_id}/fcm-token` (no
  // family_id segment). The wrong URL silently 404'd in production for every
  // push-token registration. familyId is intentionally unused here — the
  // backend resolves the family from the child row.
  void familyId;
  await client.put(`/families/children/${childId}/fcm-token`, {
    fcm_token: fcmToken,
  });
}


// ─── Swiggy MCP (per-family OAuth — Loop 5) ───────────────────────────────
//
// 2026-05-03 audit (FRONTEND-BACKEND-COORDINATION.md): replaces the
// retired multi-platform connect / verify / disconnect flow. Per founder
// call: "Swiggy-only — commit fully". The backend's per-family OAuth
// flow lives at:
//   GET    /api/swiggy/auth/start      — returns the hosted-consent URL
//   GET    /api/swiggy/auth/callback   — Swiggy redirects here with code
//   GET    /api/swiggy/auth/status     — connected? when does it expire?
//   POST   /api/swiggy/auth/refresh    — manual refresh (admin/debug)
//   DELETE /api/swiggy/auth/disconnect — revoke locally + upstream
//   POST   /api/orders/swiggy/instamart/search
//   POST   /api/orders/swiggy/food/search
//
// Brand attribution: every search response carries
// `attribution: {platform: "swiggy", surface: "instamart"|"food"}` per
// Builders Club terms. Surface that string in any UI that shows results.

export interface SwiggyAuthStatus {
  connected: boolean;
  expires_at?: string;
  granted_at?: string;
  scopes?: string;
  last_refreshed_at?: string | null;
  platforms?: {
    instamart?: { url?: string; available: boolean };
    food?: { url?: string; available: boolean };
  };
}

export function useSwiggyAuthStatus() {
  return useQuery({
    queryKey: ["swiggy-auth-status"],
    queryFn: async () => {
      const { data } = await client.get("/swiggy/auth/status");
      return data as SwiggyAuthStatus;
    },
    refetchInterval: 60_000,
  });
}

export function useSwiggyAuthStart() {
  return useMutation({
    mutationFn: async () => {
      const { data } = await client.get("/swiggy/auth/start");
      return data as {
        auth_url: string;
        state: string;
        redirect_uri: string;
        instructions: string;
      };
    },
  });
}

export function useSwiggyDisconnect() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { data } = await client.delete("/swiggy/auth/disconnect");
      return data as { status: string; had_active_connection: boolean };
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["swiggy-auth-status"] });
    },
  });
}

export interface SwiggyAttribution {
  platform: "swiggy";
  surface: "instamart" | "food";
}

export interface SwiggyInstamartSearchResult {
  query: string;
  products: Array<Record<string, unknown>>;
  attribution: SwiggyAttribution;
  error?: string | null;
}

export function useSwiggyInstamartSearch() {
  return useMutation({
    mutationFn: async (query: string) => {
      const { data } = await client.post("/orders/swiggy/instamart/search", { query });
      return data as SwiggyInstamartSearchResult;
    },
  });
}

export interface SwiggyFoodSearchResult {
  query: string;
  restaurants: Array<Record<string, unknown>>;
  attribution: SwiggyAttribution;
  error?: string | null;
}

export function useSwiggyFoodSearch() {
  return useMutation({
    mutationFn: async (query: string) => {
      const { data } = await client.post("/orders/swiggy/food/search", { query });
      return data as SwiggyFoodSearchResult;
    },
  });
}

// ─── Cook Absences ───
//
// Two-way sync between the backend `househelp_absences` table and the
// local `useCookAbsenceStore`. The mapper below is the single
// snake_case ↔ camelCase boundary; the rest of the frontend stays in
// camelCase. See backend/app/routers/absences.py for the canonical
// shape.

export const QK_ABSENCES = (familyId: string) => ["absences", familyId] as const;

export function mapAbsenceFromApi(row: any): CookAbsenceEvent {
  return {
    id: row.id,
    cookName: row.cook_name ?? "",
    date: row.date,
    endDate: row.end_date ?? undefined,
    reason: row.reason ?? undefined,
    affectedMeals: row.affected_meals ?? undefined,
    fallbackChosen: (row.fallback_chosen ?? undefined) as CookAbsenceFallback | undefined,
    fallbackDetails: row.fallback_details ?? undefined,
    replacementBooked: !!row.replacement_booked,
  };
}

export async function fetchCookAbsences(days = 90): Promise<CookAbsenceEvent[]> {
  const { data } = await client.get(`/absences?days=${days}`);
  return ((data || []) as any[]).map(mapAbsenceFromApi);
}

export function useGetCookAbsences(familyId: string) {
  return useQuery({
    queryKey: QK_ABSENCES(familyId),
    queryFn: () => fetchCookAbsences(90),
    enabled: !!familyId && isRealAuth(),
  });
}

export function usePostCookAbsence(familyId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      parentId: string;
      date: string;
      endDate?: string;
      affectedMeals?: string[];
      reason?: string;
    }) => {
      const { data } = await client.post(`/absences`, {
        parent_id: input.parentId,
        date: input.date,
        end_date: input.endDate ?? null,
        affected_meals: input.affectedMeals ?? null,
        reason: input.reason ?? null,
      });
      return mapAbsenceFromApi(data);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: QK_ABSENCES(familyId) }),
  });
}

export function usePatchAbsenceFallback(familyId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (input: {
      absenceId: string;
      fallback: CookAbsenceFallback | null;
      details?: string;
    }) => {
      const { data } = await client.patch(`/absences/${input.absenceId}/fallback`, {
        fallback_chosen: input.fallback,
        fallback_details: input.details ?? null,
      });
      return mapAbsenceFromApi(data);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: QK_ABSENCES(familyId) }),
  });
}
