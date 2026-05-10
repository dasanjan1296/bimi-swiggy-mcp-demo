import { create } from "zustand";
import { isRealAuth } from "./auth-flags";
import { localIsoDate, localIsoDatePlus } from "./local-day";
import type {
  Household,
  MealPlan,
  MealVote,
  Order,
  AutoApprovalRule,
  InventoryItem,
  CookMessage,
  FairnessScore,
  MealSuggestion,
  MealType,
  HouseholdType,
  HouseholdMember,
  Cook,
  WishlistItem,
  MonthlyExpenseSummary,
  RecipeSource,
  LeftoverItem,
  HealthMetric,
  HealthTrend,
  GuestProfile,
  GuestVisit,
  IngredientSubstitution,
  MonthlyBudget,
  CookAbsenceEvent,
  CookAbsenceFallback,
  PrepStatus,
  MealHistoryEntry,
} from "./types";
import { HOUSEHOLD_DEFAULTS } from "./types";
import {
  BACHELOR_HOUSEHOLD,
  COUPLE_HOUSEHOLD,
  FAMILY_HOUSEHOLD,
  ALL_HOUSEHOLDS,
  MOCK_TODAYS_PLANS,
  MOCK_TOMORROWS_PLAN,
  MOCK_TOMORROWS_PLANS,
  MOCK_ORDERS,
  MOCK_AUTO_RULES,
  MOCK_INVENTORY,
  MOCK_COOK_MESSAGES,
  BACHELOR_FAIRNESS,
  COUPLE_FAIRNESS,
  FAMILY_FAIRNESS,
  MOCK_MEAL_HISTORY,
  MOCK_MEAL_SUGGESTIONS,
  MOCK_WISHLIST,
  MOCK_EXPENSES,
  generateCookMessage,
} from "./mock-data";

// NOTE on persistence: an earlier Pass 2 attempt wrapped useInstacookStore
// in zustand `persist` backed by AsyncStorage. The current dev client
// doesn't have the native AsyncStorage module linked, and the wrapper
// throws an uncatchable LogBox warning at module load. Persistence is
// disabled here until the dev client is rebuilt with the dep linked;
// see Pass 3 backlog in QA-REPORT-2026-04-18.md for the follow-up.

// ─── Available Dishes Helper ───

export function getAvailableDishes(inventoryItems: InventoryItem[], repertoire: string[]): string[] {
  const inStockNames = new Set(inventoryItems.filter((i) => !i.isLowStock).map((i) => i.name.toLowerCase()));
  const hasBasicStaples = inStockNames.has("basmati rice") || inStockNames.has("aashirvaad atta") || inStockNames.has("rice");
  if (!hasBasicStaples) return repertoire.slice(0, 3);
  return repertoire;
}

// ─── Household Store ───

interface HouseholdStore {
  household: Household | null;
  allHouseholds: Household[];
  isOnboarded: boolean;

  setHousehold: (h: Household) => void;
  switchHousehold: (id: string) => void;
  setOnboarded: (v: boolean) => void;
  updateMember: (id: string, data: Partial<HouseholdMember>) => void;
  addMember: (member: HouseholdMember) => void;
  removeMember: (id: string) => void;
  leaveHousehold: (memberId: string) => void;
  /**
   * Member-lifecycle archive: marks the household archived (e.g. after
   * couple breakup) so the user can stay logged in but the surface goes
   * empty until they create or join a new one.
   */
  archiveHousehold: () => void;
  /**
   * P3: joins the matched household from invite-code lookup. Swaps the
   * current `household` to a stub built from `matched` + the new member,
   * fixing the prior bug where addMember mutated the WRONG household.
   */
  joinHousehold: (
    matched: { householdId: string; name: string; memberCount: number; cookName?: string; expenseMode: string },
    member: HouseholdMember,
  ) => void;
  transferAdmin: (fromId: string, toId: string) => void;
  setCook: (cook: Cook) => void;
  addCook: (cook: Cook) => void;
  removeCook: () => void;
  generateInviteCode: () => string;
  setMemberAvailability: (memberId: string, available: boolean) => void;
}

export const useHouseholdStore = create<HouseholdStore>((set, get) => ({
  household: BACHELOR_HOUSEHOLD,
  allHouseholds: ALL_HOUSEHOLDS,
  isOnboarded: true,

  setHousehold: (household) => set({ household }),
  switchHousehold: (id) => {
    const found = get().allHouseholds.find((h) => h.id === id);
    if (found) {
      set({ household: found });
      const members = found.members.filter((m) => m.isActive).map((m) => ({ id: m.id, name: m.name }));
      const history = useMealStore.getState().mealHistory;
      useMealStore.setState({ fairnessScores: computeFairness(members, history) });
    }
  },
  setOnboarded: (isOnboarded) => set({ isOnboarded }),

  updateMember: (id, data) =>
    set((state) => {
      if (!state.household) return state;
      return {
        household: {
          ...state.household,
          members: state.household.members.map((m) => (m.id === id ? { ...m, ...data } : m)),
        },
      };
    }),

  addMember: (member) =>
    set((state) => {
      if (!state.household) return state;
      return {
        household: {
          ...state.household,
          members: [...state.household.members, member],
        },
      };
    }),

  removeMember: (id) =>
    set((state) => {
      if (!state.household) return state;
      return {
        household: {
          ...state.household,
          members: state.household.members.map((m) =>
            m.id === id ? { ...m, isActive: false } : m
          ),
        },
      };
    }),

  leaveHousehold: (memberId) =>
    set((state) => {
      if (!state.household) return state;
      const updatedMembers = state.household.members.map((m) =>
        m.id === memberId ? { ...m, isActive: false } : m,
      );
      // P3: if the leaver was the sole admin, auto-promote the next active
      // member so the household isn't left orphaned.
      const remainingActive = updatedMembers.filter((m) => m.isActive);
      const stillHasAdmin = remainingActive.some((m) => m.isAdmin);
      if (!stillHasAdmin && remainingActive.length > 0) {
        const promoted = remainingActive[0].id;
        return {
          household: {
            ...state.household,
            members: updatedMembers.map((m) => (m.id === promoted ? { ...m, isAdmin: true } : m)),
          },
        };
      }
      return {
        household: {
          ...state.household,
          members: updatedMembers,
        },
      };
    }),

  archiveHousehold: () =>
    set((state) => {
      if (!state.household) return state;
      return {
        household: { ...state.household, archivedAt: new Date().toISOString() } as Household,
      };
    }),

  joinHousehold: (matched, member) =>
    set(() => {
      // Build a synthesized Household from the lookup payload + the new
      // member. Preserves ID so downstream state (mealHistory etc.) keys
      // off the right household.
      const expenseMode = (matched.expenseMode || "equal_split") as any;
      const config = HOUSEHOLD_DEFAULTS.flatmates;
      const cooks: Cook[] = matched.cookName
        ? [
            {
              id: `cook-${matched.householdId}`,
              name: matched.cookName,
              whatsappNumber: "",
              schedule: "",
              repertoire: [],
              slots: [],
            },
          ]
        : [];
      const householdName = matched.name || "Your House";
      const newHousehold: Household = {
        id: matched.householdId,
        type: "flatmates",
        name: householdName,
        members: [{ ...member, isAdmin: false }],
        cooks,
        hasCook: cooks.length > 0,
        config: { ...config, expenseMode },
        createdAt: new Date().toISOString(),
      } as Household;
      return { household: newHousehold, isOnboarded: true };
    }),

  transferAdmin: (fromId, toId) =>
    set((state) => {
      if (!state.household) return state;
      return {
        household: {
          ...state.household,
          members: state.household.members.map((m) => {
            if (m.id === fromId) return { ...m, isAdmin: false };
            if (m.id === toId) return { ...m, isAdmin: true };
            return m;
          }),
        },
      };
    }),

  setCook: (cook) =>
    set((state) => {
      if (!state.household) return state;
      return {
        household: {
          ...state.household,
          cooks: [cook],
          hasCook: true,
        },
      };
    }),
  addCook: (cook) =>
    set((state) => {
      if (!state.household) return state;
      return {
        household: {
          ...state.household,
          cooks: [...state.household.cooks, cook],
          hasCook: true,
        },
      };
    }),
  removeCook: () =>
    set((state) => {
      if (!state.household) return state;
      return {
        household: { ...state.household, cooks: [], hasCook: false },
      };
    }),

  generateInviteCode: () => {
    const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
    let code = "";
    for (let i = 0; i < 6; i++) code += chars[Math.floor(Math.random() * chars.length)];
    set((state) => {
      if (!state.household) return state;
      return {
        household: {
          ...state.household,
          inviteCode: code,
          inviteCodeExpiresAt: new Date(Date.now() + 7 * 86400000).toISOString(),
        },
      };
    });
    return code;
  },

  setMemberAvailability: (memberId, available) =>
    set((state) => {
      if (!state.household) return state;
      return {
        household: {
          ...state.household,
          members: state.household.members.map((m) =>
            m.id === memberId ? { ...m, isAvailable: available } : m
          ),
        },
      };
    }),
}));

// ─── Meal Store ───

interface MealStore {
  todaysPlans: MealPlan[];
  tomorrowsPlans: MealPlan[];
  /** @deprecated Use tomorrowsPlans instead */
  tomorrowsPlan: MealPlan;
  suggestions: Record<string, MealSuggestion[]>;
  fairnessScores: FairnessScore[];
  mealHistory: MealHistoryEntry[];
  activeMealType: MealType;
  setActiveMealType: (t: MealType) => void;
  submitVote: (vote: MealVote) => void;
  finalizePlan: (dishName: string, dishes: string[], hasCook?: boolean) => void;
  /**
   * Hard-lock promoter for the soft-lock window. Called by the voting screen
   * timer when `lockInAt` elapses. Idempotent: no-ops if the plan is already
   * locked, has no soft-pick winner, or has no `lockInAt`.
   *
   * Side effects on success:
   *   - Promotes the soft-pick to a finalized plan (delegates to finalizePlan
   *     to write meal history and brief the cook exactly once).
   *   - Sets `isLocked: true` and clears `lockInAt` on the matching plan.
   */
  lockInPlan: (mealType: MealType, hasCook?: boolean) => void;
  setFairnessScores: (scores: FairnessScore[]) => void;
  recomputeFairness: () => void;
  rateMeal: (planId: string, rating: number) => void;
  removeVote: (memberId: string, dishId: string) => void;
  addSuggestion: (mealType: string, suggestion: MealSuggestion) => void;
  confirmPrep: () => void;
  assignPrepToUser: () => void;
  failPrepAndSwitch: () => string | null;
  votingStreak: number;
  incrementStreak: () => void;
  resetStreak: () => void;
  /**
   * P3 (PRD 4.5): For each active member who hasn't voted on the active
   * meal type, synthesize a proxy vote derived from their meal history.
   * No-ops if there are no real candidates or no missing voters. Idempotent.
   */
  generateProxyVotes: () => void;
  /**
   * Wheel-of-Meals future-day votes. Keyed by `${date}-${mealType}` where
   * date is YYYY-MM-DD. Holds D+2..D+6 picks made via the weekly planner.
   * Today (D+0) and tomorrow (D+1) keep using `todaysPlans` /
   * `tomorrowsPlans` — this map only covers the window beyond tomorrow.
   * Client-side only for v1; v2 work persists these to the backend.
   */
  futureWeekPlans: Record<string, MealPlan>;
  /**
   * Cast a vote for a future day (D+2..D+6) via the Wheel of Meals.
   * Idempotent: re-voting overwrites the prior pick. Records meal history
   * locally so the wheel sector reflects the new state immediately.
   */
  voteFutureDay: (date: string, mealType: MealType, dishName: string) => void;
}

/**
 * Computes fairness scores from meal history.
 *
 * For each member, only meals they participated in count. Skipped meals
 * are invisible — they don't help or hurt the member's score.
 *
 * satisfactionScore (0-1): weighted blend of two signals:
 *   - pickRate: how often the member's voted dish was the one selected (their voice matters)
 *   - ratingAvg: their average meal rating normalized to 0-1 (they enjoyed what was served)
 *   Weight: 60% pickRate + 40% normalized rating
 *
 * isUnderserved: true if the member's satisfactionScore is below the group average.
 */
function computeFairness(
  members: { id: string; name: string }[],
  history: MealHistoryEntry[],
): FairnessScore[] {
  if (history.length === 0) {
    return members.map((m) => ({
      memberId: m.id,
      memberName: m.name,
      satisfactionScore: 0.5,
      mealsServed: 0,
      avgSatisfaction: 0,
      isUnderserved: false,
    }));
  }

  const scores = members.map((m) => {
    const participated = history.filter((h) => h.participantIds.includes(m.id));
    const mealsServed = participated.length;
    if (mealsServed === 0) {
      return { memberId: m.id, memberName: m.name, satisfactionScore: 0.5, mealsServed: 0, avgSatisfaction: 0, isUnderserved: false };
    }

    let pickWins = 0;
    for (const meal of participated) {
      // Fairness pick-rate must reflect MEMBER engagement, not Bimi's
      // proxy guesses. History now stores both real and proxy votes
      // (so the past-day modal can show attribution); filter proxies
      // out here so pick-wins only credit actual member taps.
      const memberVote = meal.votes.find(
        (v) => v.memberId === m.id && !v.isProxy,
      );
      if (memberVote && memberVote.dishName === meal.selectedMeal) pickWins++;
    }
    const pickRate = pickWins / mealsServed;

    const memberRatings = participated
      .flatMap((meal) => meal.ratings.filter((r) => r.memberId === m.id))
      .map((r) => r.rating);
    const avgSatisfaction = memberRatings.length > 0
      ? memberRatings.reduce((a, b) => a + b, 0) / memberRatings.length
      : 3;
    const normalizedRating = (avgSatisfaction - 1) / 4;

    const satisfactionScore = Math.round((0.6 * pickRate + 0.4 * normalizedRating) * 100) / 100;

    return { memberId: m.id, memberName: m.name, satisfactionScore, mealsServed, avgSatisfaction: Math.round(avgSatisfaction * 10) / 10, isUnderserved: false };
  });

  const activeScores = scores.filter((s) => s.mealsServed > 0);
  if (activeScores.length > 1) {
    const avg = activeScores.reduce((sum, s) => sum + s.satisfactionScore, 0) / activeScores.length;
    for (const s of scores) {
      if (s.mealsServed > 0) {
        s.isUnderserved = s.satisfactionScore < avg;
      }
    }
  }

  return scores;
}

function findBackupMeal(suggestions: MealSuggestion[]): MealSuggestion | undefined {
  return [...suggestions]
    .filter((s) => !s.needsAdvancePrep)
    .sort((a, b) => b.confidence - a.confidence)[0];
}

function updatePlanByMealType(plans: MealPlan[], mealType: string, updater: (p: MealPlan) => MealPlan): MealPlan[] {
  return plans.map((p) => p.mealType === mealType ? updater(p) : p);
}

function getActivePlan(state: { tomorrowsPlans: MealPlan[]; activeMealType: string }): MealPlan {
  return state.tomorrowsPlans.find((p) => p.mealType === state.activeMealType) || state.tomorrowsPlans[0];
}

export const useMealStore = create<MealStore & {
  setSuggestionsFromBackend: (s: any) => void;
  setMealHistoryFromBackend: (entries: MealHistoryEntry[]) => void;
}>((set, get) => ({
  todaysPlans: MOCK_TODAYS_PLANS,
  tomorrowsPlans: MOCK_TOMORROWS_PLANS,
  tomorrowsPlan: MOCK_TOMORROWS_PLAN,
  futureWeekPlans: {},
  suggestions: MOCK_MEAL_SUGGESTIONS,
  mealHistory: MOCK_MEAL_HISTORY,
  fairnessScores: computeFairness(
    BACHELOR_HOUSEHOLD.members.filter((m) => m.isActive).map((m) => ({ id: m.id, name: m.name })),
    MOCK_MEAL_HISTORY,
  ),
  activeMealType: "lunch",
  setActiveMealType: (activeMealType) => set({ activeMealType }),
  submitVote: (vote) => {
    const mt = get().activeMealType;
    set((state) => ({
      tomorrowsPlans: updatePlanByMealType(state.tomorrowsPlans, mt, (p) => ({
        ...p,
        votes: [...p.votes.filter((v) => !(v.memberId === vote.memberId && v.dishId === vote.dishId)), vote],
      })),
      tomorrowsPlan: state.tomorrowsPlan.mealType === mt
        ? { ...state.tomorrowsPlan, votes: [...state.tomorrowsPlan.votes.filter((v) => !(v.memberId === vote.memberId && v.dishId === vote.dishId)), vote] }
        : state.tomorrowsPlan,
    }));
    const { useAuthStore } = require("./auth-store");
    const { client } = require("./api");
    const auth = useAuthStore.getState();
    if (isRealAuth() && auth.familyId) {
      client.post(`/families/${auth.familyId}/voting/vote`, {
        member_id: vote.memberId,
        member_name: vote.memberName || "Voter",
        meal_type: mt,
        dish_name: vote.dishName || vote.dishId,
        rating: vote.rating,
      }).catch(() => {});
    }
  },
  removeVote: (memberId, dishId) => {
    const mt = get().activeMealType;
    set((state) => ({
      tomorrowsPlans: updatePlanByMealType(state.tomorrowsPlans, mt, (p) => ({
        ...p,
        votes: p.votes.filter((v) => !(v.memberId === memberId && v.dishId === dishId)),
      })),
      tomorrowsPlan: state.tomorrowsPlan.mealType === mt
        ? { ...state.tomorrowsPlan, votes: state.tomorrowsPlan.votes.filter((v) => !(v.memberId === memberId && v.dishId === dishId)) }
        : state.tomorrowsPlan,
    }));
  },
  addSuggestion: (mealType, suggestion) => {
    set((state) => ({
      suggestions: {
        ...state.suggestions,
        [mealType]: [...(state.suggestions[mealType] || []), suggestion],
      },
    }));
    if (suggestion.sourceUrl) {
      const { useAuthStore } = require("./auth-store");
      const { client } = require("./api");
      const auth = useAuthStore.getState();
      if (isRealAuth() && auth.familyId) {
        client.post(`/families/${auth.familyId}/dish-suggestions`, {
          dish_name: suggestion.dishName,
          source_url: suggestion.sourceUrl,
          note_for_cook: suggestion.noteForCook || null,
          suggested_by_id: suggestion.suggestedById || null,
          suggested_by_name: suggestion.suggestedByName || null,
          meal_type: mealType,
        }).then((resp: any) => {
          const d = resp.data;
          const enriched: MealSuggestion = {
            id: suggestion.id,
            dishName: d.dish_name,
            confidence: d.confidence,
            fairnessScore: d.fairness_score,
            noveltyBonus: d.novelty_bonus,
            prepTime: d.prep_time,
            needsAdvancePrep: d.needs_advance_prep,
            advancePrepNote: d.advance_prep_note,
            constraints: d.constraints || [],
            ingredients: d.ingredients || [],
            missingIngredients: d.missing_ingredients || [],
            sourceUrl: d.source_url,
            sourcePlatform: d.source_platform,
            sourceThumbnail: d.source_thumbnail,
            suggestedById: d.suggested_by_id,
            suggestedByName: d.suggested_by_name,
            noteForCook: d.note_for_cook,
          };
          set((state) => ({
            suggestions: {
              ...state.suggestions,
              [mealType]: (state.suggestions[mealType] || []).map((s) =>
                s.id === suggestion.id ? enriched : s
              ),
            },
          }));
        }).catch(() => {});
      }
    }
  },
  finalizePlan: (dishName, dishes, hasCook) => {
    const state = get();
    const mealType = state.activeMealType;
    const plan = getActivePlan(state);
    const allSuggestions = state.suggestions[mealType] || [];
    const chosen = allSuggestions.find((s) => s.dishName === dishName);
    const needsPrep = chosen?.needsAdvancePrep || false;
    const backup = needsPrep ? findBackupMeal(allSuggestions) : undefined;

    const skippedIds = new Set(plan.votes.filter((v) => v.skipped).map((v) => v.memberId));
    const members = useHouseholdStore.getState().household?.members.filter((m) => m.isActive && m.isAvailable) || [];
    const participantIds = members.map((m) => m.id).filter((id) => !skippedIds.has(id));
    // Capture ALL non-skipped votes (real + proxy) so the past-day
    // modal can render proxy attribution like "Bimi proxy-voted Maggi
    // for Saumya". Fairness scoring filters proxies out via `isProxy`
    // so this doesn't inflate anyone's pick-rate.
    const capturedVotes = plan.votes.filter((v) => !v.skipped);

    const historyEntry: MealHistoryEntry = {
      date: plan.date,
      mealType,
      selectedMeal: dishName,
      participantIds,
      votes: capturedVotes.map((v) => ({
        memberId: v.memberId,
        dishName: v.dishName,
        rating: v.rating,
        isProxy: v.isProxy ?? false,
      })),
      ratings: [],
    };

    const updatedHistory = [...state.mealHistory, historyEntry];
    const memberList = members.map((m) => ({ id: m.id, name: m.name }));

    const updatedPlan = {
      ...plan,
      selectedMeal: dishName,
      dishes,
      status: "planned" as const,
      prepStatus: needsPrep ? (hasCook ? "assigned_cook" as const : "assigned_user" as const) : undefined,
      backupMealId: backup?.id,
      prepInstructions: chosen?.advancePrepNote || plan.prepInstructions,
    };

    set({
      tomorrowsPlans: updatePlanByMealType(state.tomorrowsPlans, mealType, () => updatedPlan),
      tomorrowsPlan: state.tomorrowsPlan.mealType === mealType ? updatedPlan : state.tomorrowsPlan,
      mealHistory: updatedHistory,
      fairnessScores: computeFairness(memberList, updatedHistory),
    });

    // P3 (PRD 4.8 outbound type 1): brief the cook on what was finalized.
    try {
      const cook = useHouseholdStore.getState().household?.cooks?.[0];
      if (cook && hasCook) {
        const { sendMealFinalizedToCook } = require("./cook-messages");
        sendMealFinalizedToCook({
          cookName: cook.name,
          cookPhone: cook.whatsappNumber,
          mealType: mealType as any,
          dishName,
          prepNote: chosen?.advancePrepNote,
          ingredientsReady: !chosen?.missingIngredients?.length,
        });
      }
    } catch {
      /* cook-messages module may not load in tests */
    }
  },
  lockInPlan: (mealType, hasCook) => {
    const state = get();
    const plan = state.tomorrowsPlans.find((p) => p.mealType === mealType);
    if (!plan) return;
    // Idempotent: already hard-locked, or no soft-pick to promote.
    if (plan.isLocked) return;
    if (!plan.selectedMeal) return;

    // Delegate the actual promotion (history + cook brief) to finalizePlan.
    // It reads activeMealType, so flip it momentarily if needed.
    const previousActive = state.activeMealType;
    if (previousActive !== mealType) {
      set({ activeMealType: mealType });
    }
    get().finalizePlan(plan.selectedMeal, plan.dishes, hasCook);
    if (previousActive !== mealType) {
      set({ activeMealType: previousActive });
    }

    // Mark the plan as hard-locked and clear the soft-lock window.
    set((s) => ({
      tomorrowsPlans: s.tomorrowsPlans.map((p) =>
        p.mealType === mealType ? { ...p, isLocked: true, lockInAt: undefined } : p,
      ),
      tomorrowsPlan:
        s.tomorrowsPlan.mealType === mealType
          ? { ...s.tomorrowsPlan, isLocked: true, lockInAt: undefined }
          : s.tomorrowsPlan,
    }));
  },
  setFairnessScores: (fairnessScores) => set({ fairnessScores }),
  recomputeFairness: () => {
    const members = useHouseholdStore.getState().household?.members
      .filter((m) => m.isActive)
      .map((m) => ({ id: m.id, name: m.name })) || [];
    const history = get().mealHistory;
    set({ fairnessScores: computeFairness(members, history) });
  },
  rateMeal: (planId, rating) => {
    const state = get();
    const plan = state.todaysPlans.find((p) => p.id === planId);
    set({
      todaysPlans: state.todaysPlans.map((p) =>
        p.id === planId ? { ...p, rating } : p
      ),
    });
    if (plan?.selectedMeal) {
      const existing = state.mealHistory.find((h) => h.date === plan.date && h.mealType === plan.mealType);
      if (existing) {
        const members = useHouseholdStore.getState().household?.members.filter((m) => m.isActive) || [];
        const memberId = members.find((m) => m.isAdmin)?.id || members[0]?.id;
        if (memberId) {
          const updatedRatings = existing.ratings.filter((r) => r.memberId !== memberId);
          updatedRatings.push({ memberId, rating });
          const updatedHistory = state.mealHistory.map((h) =>
            h === existing ? { ...h, ratings: updatedRatings } : h
          );
          set({ mealHistory: updatedHistory });
          const memberList = members.map((m) => ({ id: m.id, name: m.name }));
          set({ fairnessScores: computeFairness(memberList, updatedHistory) });
        }
      }

      if (rating >= 4) {
        const dishName = plan.selectedMeal;
        const hState = useHouseholdStore.getState();
        const cook = hState.household?.cooks?.[0];
        if (cook && !cook.repertoire.includes(dishName)) {
          hState.setCook({ ...cook, repertoire: [...cook.repertoire, dishName] });
          const { useNotificationStore } = require("./notifications");
          useNotificationStore.getState().addNotification({
            type: "cook_changed",
            title: "Repertoire updated",
            body: `"${dishName}" was rated ${rating}★ — added to ${cook.name}'s repertoire.`,
          });
        }
      }

      const { client } = require("./api");
      if (isRealAuth()) {
        client.post(`/meals/${planId}/feedback`, { rating }).catch(() => {});
      }
    }
  },
  confirmPrep: () => {
    const mt = get().activeMealType;
    set((state) => ({
      tomorrowsPlans: updatePlanByMealType(state.tomorrowsPlans, mt, (p) => ({ ...p, prepStatus: "confirmed" })),
      tomorrowsPlan: state.tomorrowsPlan.mealType === mt ? { ...state.tomorrowsPlan, prepStatus: "confirmed" } : state.tomorrowsPlan,
    }));
  },
  assignPrepToUser: () => {
    const mt = get().activeMealType;
    set((state) => ({
      tomorrowsPlans: updatePlanByMealType(state.tomorrowsPlans, mt, (p) => ({ ...p, prepStatus: "assigned_user" })),
      tomorrowsPlan: state.tomorrowsPlan.mealType === mt ? { ...state.tomorrowsPlan, prepStatus: "assigned_user" } : state.tomorrowsPlan,
    }));
  },
  failPrepAndSwitch: () => {
    const state = get();
    const plan = getActivePlan(state);
    const allSuggestions = state.suggestions[plan.mealType] || [];
    const backup = plan.backupMealId
      ? allSuggestions.find((s) => s.id === plan.backupMealId)
      : findBackupMeal(allSuggestions);

    if (!backup) return null;

    const updated = {
      ...plan,
      switchedFromMeal: plan.selectedMeal,
      selectedMeal: backup.dishName,
      dishes: [backup.dishName],
      prepStatus: "failed" as const,
      prepInstructions: undefined,
      backupMealId: undefined,
    };

    set({
      tomorrowsPlans: updatePlanByMealType(state.tomorrowsPlans, plan.mealType, () => updated),
      tomorrowsPlan: state.tomorrowsPlan.mealType === plan.mealType ? updated : state.tomorrowsPlan,
    });
    return backup.dishName;
  },
  votingStreak: 3,
  incrementStreak: () => set((state) => ({ votingStreak: state.votingStreak + 1 })),
  resetStreak: () => set({ votingStreak: 0 }),
  generateProxyVotes: () => {
    const state = get();
    const mt = state.activeMealType;
    const plan = state.tomorrowsPlans.find((p) => p.mealType === mt);
    if (!plan) return;
    const householdState = useHouseholdStore.getState();
    const activeMembers =
      householdState.household?.members.filter((m) => m.isActive && m.isAvailable) || [];
    const allSuggestions = state.suggestions[mt] || [];
    if (allSuggestions.length === 0) return;

    const existingVoteIds = new Set(
      plan.votes.filter((v) => !v.skipped).map((v) => v.memberId),
    );
    const missing = activeMembers.filter((m) => !existingVoteIds.has(m.id));
    if (missing.length === 0) return;

    // Score each suggestion per member using their personal history of
    // ratings on similar dishes. Falls back to global confidence when the
    // member has no relevant history.
    const proxyVotes: MealVote[] = missing.map((member) => {
      const memberRatings = state.mealHistory.flatMap((h) =>
        h.ratings.filter((r) => r.memberId === member.id).map((r) => ({ dish: h.selectedMeal, rating: r.rating })),
      );
      let bestScore = -Infinity;
      let bestSugg = allSuggestions[0];
      for (const s of allSuggestions) {
        // Match by dish-name keyword overlap (lightweight cosine-ish)
        const keywords = s.dishName.toLowerCase().split(/\s+/);
        const matches = memberRatings.filter((r) =>
          keywords.some((k) => r.dish.toLowerCase().includes(k)),
        );
        const personalAvg =
          matches.length > 0
            ? matches.reduce((sum, r) => sum + r.rating, 0) / matches.length / 5
            : 0.5; // neutral prior
        const score = 0.6 * personalAvg + 0.4 * (s.confidence ?? 0.5);
        if (score > bestScore) {
          bestScore = score;
          bestSugg = s;
        }
      }
      // Confidence: blend of model conf + how strongly history supports it
      const confidence = Math.max(0.55, Math.min(0.95, bestScore));
      return {
        id: `proxy-${member.id}-${bestSugg.id}-${Date.now()}`,
        memberId: member.id,
        memberName: member.name,
        dishId: bestSugg.id,
        dishName: bestSugg.dishName,
        rating: 4,
        timestamp: new Date().toISOString(),
        isProxy: true,
        proxyConfidence: confidence,
      };
    });

    set((s) => ({
      tomorrowsPlans: updatePlanByMealType(s.tomorrowsPlans, mt, (p) => ({
        ...p,
        votes: [...p.votes.filter((v) => !v.isProxy || existingVoteIds.has(v.memberId)), ...proxyVotes],
      })),
      tomorrowsPlan:
        s.tomorrowsPlan.mealType === mt
          ? {
              ...s.tomorrowsPlan,
              votes: [...s.tomorrowsPlan.votes.filter((v) => !v.isProxy || existingVoteIds.has(v.memberId)), ...proxyVotes],
            }
          : s.tomorrowsPlan,
    }));
  },
  setSuggestionsFromBackend: (backendSuggestions: any) => {
    const mapped: Record<string, MealSuggestion[]> = {};
    for (const [mealType, dishes] of Object.entries(backendSuggestions)) {
      mapped[mealType] = (dishes as any[]).map((d: any) => ({
        id: d.id || `s-${Math.random().toString(36).slice(2, 7)}`,
        dishName: d.dish_name || d.name,
        confidence: d.confidence || 0.8,
        fairnessScore: d.fairness_score || 0.8,
        noveltyBonus: d.novelty_bonus || 0,
        prepTime: d.prep_time || "30 min",
        needsAdvancePrep: d.needs_advance_prep || false,
        advancePrepNote: d.advance_prep_note,
        constraints: (d.constraints || []).map((c: any) => typeof c === "string" ? { description: c, severity: "info" } : c),
        ingredients: d.ingredients || [],
        missingIngredients: d.missing_ingredients || [],
        sourceUrl: d.source_url,
        sourcePlatform: d.source_platform,
        sourceThumbnail: d.source_thumbnail,
        suggestedById: d.suggested_by_id,
        suggestedByName: d.suggested_by_name,
        noteForCook: d.note_for_cook,
      }));
    }
    if (Object.keys(mapped).length > 0) {
      set({ suggestions: { ...get().suggestions, ...mapped } });
    }
  },
  /**
   * Replace local mealHistory with the cross-device server payload.
   *
   * Reconciliation rule: if the server returns at least one entry,
   * trust it as the source of truth. We deliberately do NOT merge
   * with the local mock array — that's seed data for the demo
   * session and would otherwise leak into authenticated households'
   * histories. Empty server response keeps whatever's in the store
   * (cold-start households, offline mode).
   *
   * Fairness scores are recomputed from the new history so the
   * settle-tab indicator stays consistent.
   */
  setMealHistoryFromBackend: (entries: MealHistoryEntry[]) => {
    if (!Array.isArray(entries) || entries.length === 0) return;
    const memberList = (BACHELOR_HOUSEHOLD.members ?? [])
      .filter((m: any) => m.isActive)
      .map((m: any) => ({ id: m.id, name: m.name }));
    set({
      mealHistory: entries,
      fairnessScores: computeFairness(memberList, entries),
    });
  },
  voteFutureDay: (date, mealType, dishName) => {
    const key = `${date}-${mealType}`;
    set((state) => {
      const existing = state.futureWeekPlans[key];
      const next: MealPlan = existing
        ? { ...existing, selectedMeal: dishName, dishes: [dishName] }
        : {
            id: `fwp-${key}`,
            date,
            mealType,
            selectedMeal: dishName,
            dishes: [dishName],
            status: "planned",
            votes: [],
            suggestions: state.suggestions[mealType] || [],
          };
      return {
        futureWeekPlans: { ...state.futureWeekPlans, [key]: next },
      };
    });
  },
}));

// ─── Order Store ───

interface OrderStore {
  orders: Order[];
  autoRules: AutoApprovalRule[];
  approveOrder: (orderId: string, approver: string) => void;
  rejectOrder: (orderId: string) => void;
  addRule: (rule: AutoApprovalRule) => void;
  updateRule: (id: string, data: Partial<AutoApprovalRule>) => void;
  removeRule: (id: string) => void;
  toggleRule: (id: string) => void;
}

export const useOrderStore = create<OrderStore & { setOrdersFromBackend: (carts: any[]) => void }>((set) => ({
  orders: MOCK_ORDERS,
  autoRules: MOCK_AUTO_RULES,
  approveOrder: (orderId, approver) => {
    set((state) => ({
      orders: state.orders.map((o) =>
        o.id === orderId
          ? { ...o, status: "approved", approvedBy: approver, approvedAt: new Date().toISOString() }
          : o
      ),
    }));
    const { useAuthStore } = require("./auth-store");
    const { client } = require("./api");
    const childId = useAuthStore.getState().childId;
    if (isRealAuth()) {
      client.post(`/carts/${orderId}/approve`, { child_id: childId }).catch(() => {});
    }
  },
  rejectOrder: (orderId) => {
    set((state) => ({
      orders: state.orders.map((o) => (o.id === orderId ? { ...o, status: "rejected" } : o)),
    }));
    const { client } = require("./api");
    if (isRealAuth()) {
      client.post(`/carts/${orderId}/skip`).catch(() => {});
    }
  },
  addRule: (rule) => set((state) => ({ autoRules: [...state.autoRules, rule] })),
  updateRule: (id, data) =>
    set((state) => ({
      autoRules: state.autoRules.map((r) => (r.id === id ? { ...r, ...data } : r)),
    })),
  removeRule: (id) =>
    set((state) => ({ autoRules: state.autoRules.filter((r) => r.id !== id) })),
  toggleRule: (id) =>
    set((state) => ({
      autoRules: state.autoRules.map((r) => (r.id === id ? { ...r, enabled: !r.enabled } : r)),
    })),
  setOrdersFromBackend: (carts) => {
    if (!carts || carts.length === 0) return;
    const mapped: Order[] = carts.map((c: any) => ({
      id: c.id,
      items: (c.items || []).map((i: any, idx: number) => ({
        id: i.id || `${c.id}-it-${idx}`,
        name: i.name || i.item_name,
        quantity: String(i.quantity ?? 1),
        estimatedPrice: i.price || i.estimated_price || 0,
        category: i.category,
      })),
      totalAmount: c.estimated_total || 0,
      status: c.status || "pending",
      requestedBy: c.requested_by_name || "Cook",
      requestedAt: c.created_at || new Date().toISOString(),
      approvedBy: c.approved_by,
      approvedAt: c.approved_at,
    }));
    set({ orders: mapped });
  },
}));

// ─── Inventory Store ───

interface InventoryStore {
  items: InventoryItem[];
  addItem: (item: InventoryItem) => void;
  refreshInventory: () => void;
  setItemsFromBackend: (items: any[]) => void;
  /**
   * Mark matching inventory items as freshly stocked (clears
   * `isLowStock`). Match heuristic is case-insensitive substring
   * (so `"atta"` matches `"Aashirvaad Atta"`). Called by
   * `useSwiggyDeliveryStore.markDelivered` once a Swiggy order
   * lands — no user confirmation step. Production path will use
   * structured product ids from MCP responses instead of name
   * substring; the API surface stays the same.
   */
  restock: (itemNames: string[]) => void;
}

export const useInventoryStore = create<InventoryStore>((set) => ({
  items: MOCK_INVENTORY,
  addItem: (item) => set((state) => ({ items: [...state.items, item] })),
  refreshInventory: () => set({ items: MOCK_INVENTORY }),
  restock: (itemNames) =>
    set((state) => {
      const needles = itemNames
        .map((n) => n.trim().toLowerCase())
        .filter(Boolean);
      if (needles.length === 0) return state;
      return {
        items: state.items.map((it) => {
          const hay = it.name.toLowerCase();
          const matches = needles.some((n) => hay.includes(n));
          return matches ? { ...it, isLowStock: false } : it;
        }),
      };
    }),
  setItemsFromBackend: (backendItems) => {
    const mapped: InventoryItem[] = backendItems.map((b: any) => {
      const qty = Number(b.quantity_remaining ?? 0);
      const rate = Number(b.estimated_depletion_rate ?? 0) || 0.001;
      const daysLeft = Math.max(0, Math.ceil(qty / rate));
      return {
        id: b.id,
        name: b.item_name,
        category: b.category || "other",
        currentQuantity: String(b.quantity_remaining ?? "0"),
        unit: b.unit,
        estimatedDaysLeft: daysLeft,
        isLowStock: daysLeft <= 3,
        lastRestocked: b.last_restocked,
        depletionRate: rate,
        expiryDate: b.expiry_date,
      };
    });
    if (mapped.length > 0) set({ items: mapped });
  },
}));

// ─── Chat Store ───

interface ChatStore {
  messages: CookMessage[];
  addMessage: (msg: CookMessage) => void;
  simulateCookMessage: () => void;
  resolveAction: (msgId: string, actionIdx: number) => void;
}

export const useChatStore = create<ChatStore>((set) => ({
  messages: MOCK_COOK_MESSAGES,
  addMessage: (msg) => {
    set((state) => ({ messages: [...state.messages, msg] }));

    // Cook-brief reply detection: any inbound cook message closes any
    // open onboarding brief for that cook's phone. Runs first so the
    // scheduled 24h notification gets cancelled before any other
    // side-effect runs. Lazy-required to avoid the chat-store ↔
    // cook-brief-tracking circular import at module-load time.
    if (msg.isFromCook) {
      try {
         
        const { markCookBriefReplied } = require("./cook-brief-tracking");
        const cookPhone = useHouseholdStore.getState().household?.cooks?.[0]?.whatsappNumber;
        if (cookPhone) {
          void markCookBriefReplied(cookPhone);
        }
      } catch {
        /* tracking module unavailable in tests */
      }
    }

    const hasPrepFailed = msg.isFromCook && msg.actionItems.some((a) => a.type === "prep_failed");
    if (hasPrepFailed) {
      const backupDish = useMealStore.getState().failPrepAndSwitch();
      if (backupDish) {
        const { useNotificationStore } = require("./notifications");
        useNotificationStore.getState().addNotification({
          type: "prep_failed_auto_switch",
          title: "Meal switched",
          body: `Prep wasn't done — I've switched to ${backupDish}. No advance prep needed.`,
          actionRoute: "/(tabs)",
        });
      }
    }
    const hasAbsence = msg.isFromCook && msg.actionItems.some((a) => a.type === "absence");
    if (hasAbsence) {
      const cookName = useHouseholdStore.getState().household?.cooks?.[0]?.name || "Cook";
      const content = msg.content.toLowerCase();
      // Explicit precedence: "kal" anywhere means tomorrow regardless of other tokens.
      const mentionsKal = content.includes("kal") || content.includes("tomorrow");
      const todayTokens =
        content.includes("aaj") ||
        content.includes("today") ||
        content.includes("abhi") ||
        content.includes("right now");
      const isSameDay = todayTokens && !mentionsKal;
      const absenceDate = isSameDay ? localIsoDate() : localIsoDatePlus(1);
      const dayLabel = isSameDay ? "today" : "tomorrow";
      // Deterministic absence id derived from cook + date to prevent duplicates
      // when the same message is re-processed (two tabs, Zustand rehydrate, etc.).
      const absenceId = `abs-${absenceDate}-${cookName.toLowerCase().replace(/\s+/g, "-")}`;
      const existing = useCookAbsenceStore.getState().absences.find((a) => a.id === absenceId);
      if (!existing) {
        useCookAbsenceStore.getState().addAbsence({
          id: absenceId, cookName, date: absenceDate,
          reason: msg.content, replacementBooked: false,
        });
        // P3 (PRD 4.8 outbound type 5): auto-acknowledge the absence to the cook.
        try {
          const cook = useHouseholdStore.getState().household?.cooks?.[0];
          const { sendAbsenceAckToCook } = require("./cook-messages");
          sendAbsenceAckToCook({ cookName, cookPhone: cook?.whatsappNumber });
        } catch {
          /* ignore */
        }
      }
      const { useNotificationStore } = require("./notifications");
      useNotificationStore.getState().addNotification({
        type: "cook_changed",
        title: `${cookName} is off ${dayLabel}`,
        body: msg.content,
        actionRoute: "/(tabs)",
      });
    }
  },
  simulateCookMessage: () =>
    set((state) => ({ messages: [...state.messages, generateCookMessage()] })),
  resolveAction: (msgId, actionIdx) =>
    set((state) => ({
      messages: state.messages.map((m) =>
        m.id === msgId
          ? { ...m, actionItems: m.actionItems.map((a, i) => (i === actionIdx ? { ...a, resolved: true } : a)) }
          : m
      ),
    })),
}));

// ─── Wishlist Store ───

interface WishlistStore {
  items: WishlistItem[];
  addItem: (item: WishlistItem) => void;
  removeItem: (id: string) => void;
  markOrdered: (ids: string[]) => void;
  markBought: (ids: string[]) => void;
  clearCompleted: () => void;
  totalEstimate: () => number;
}

export const useWishlistStore = create<WishlistStore>((set, get) => ({
  items: MOCK_WISHLIST,
  addItem: (item) => set((state) => ({ items: [...state.items, item] })),
  removeItem: (id) => set((state) => ({ items: state.items.filter((i) => i.id !== id) })),
  markOrdered: (ids) =>
    set((state) => ({
      items: state.items.map((i) => (ids.includes(i.id) ? { ...i, status: "ordered" } : i)),
    })),
  markBought: (ids) =>
    set((state) => ({
      items: state.items.map((i) => (ids.includes(i.id) ? { ...i, status: "bought_in_person" } : i)),
    })),
  clearCompleted: () =>
    set((state) => ({
      items: state.items.filter((i) => i.status === "pending" || i.status === "in_cart"),
    })),
  totalEstimate: () =>
    get()
      .items.filter((i) => i.status === "pending")
      .reduce((sum, i) => sum + (i.estimatedPrice || 0), 0),
}));

// ─── Expense Store ───

interface ExpenseStore {
  summary: MonthlyExpenseSummary;
  settleDebt: (fromId: string, toId: string) => void;
  unsettleDebt: (fromId: string, toId: string) => void;
  addOrderExpense: (params: {
    amount: number;
    platform: string;
    itemCount: number;
    category?: string;
    paidByMemberId?: string;
    paidByName?: string;
  }) => void;
}

export const useExpenseStore = create<ExpenseStore>((set) => ({
  summary: MOCK_EXPENSES,
  settleDebt: (fromId, toId) =>
    set((state) => {
      const settlement = state.summary.settlements.find(
        (s) => s.fromMemberId === fromId && s.toMemberId === toId
      );
      const activity = settlement
        ? {
            id: `act-${Date.now()}`,
            type: "settlement" as const,
            description: `${settlement.fromName} settled with ${settlement.toName}`,
            amount: settlement.amount,
            timestamp: new Date().toISOString(),
            involvedMembers: [settlement.fromName, settlement.toName],
          }
        : null;
      const settledAmount = settlement?.amount || 0;
      return {
        summary: {
          ...state.summary,
          settlements: state.summary.settlements.map((s) =>
            s.fromMemberId === fromId && s.toMemberId === toId
              ? { ...s, settled: true, settledAt: new Date().toISOString() }
              : s
          ),
          perPerson: state.summary.perPerson.map((p) => {
            if (p.memberId === fromId) return { ...p, balance: p.balance + settledAmount };
            if (p.memberId === toId) return { ...p, balance: p.balance - settledAmount };
            return p;
          }),
          activities: activity
            ? [activity, ...state.summary.activities]
            : state.summary.activities,
        },
      };
    }),
  unsettleDebt: (fromId, toId) =>
    set((state) => {
      const settlement = state.summary.settlements.find(
        (s) => s.fromMemberId === fromId && s.toMemberId === toId
      );
      return {
        summary: {
          ...state.summary,
          settlements: state.summary.settlements.map((s) =>
            s.fromMemberId === fromId && s.toMemberId === toId
              ? { ...s, settled: false, settledAt: undefined }
              : s
          ),
          activities: state.summary.activities.filter(
            (a) => !(a.type === "settlement" && a.description === `${settlement?.fromName} settled with ${settlement?.toName}`)
          ),
        },
      };
    }),
  addOrderExpense: ({ amount, platform, itemCount, category, paidByMemberId, paidByName }) =>
    set((state) => {
      const catName = category || "Groceries";
      const catIcon = catName === "Groceries" ? "🛒" : "📦";
      const existingCat = state.summary.categories.find((c) => c.name === catName);
      const newTotal = state.summary.totalAmount + amount;
      const newOrderCount = state.summary.orderCount + 1;

      const updatedCategories = existingCat
        ? state.summary.categories.map((c) =>
            c.name === catName
              ? {
                  ...c,
                  amount: c.amount + amount,
                  itemCount: c.itemCount + itemCount,
                  percentage: Math.round(((c.amount + amount) / newTotal) * 100),
                }
              : { ...c, percentage: Math.round((c.amount / newTotal) * 100) },
          )
        : [
            ...state.summary.categories.map((c) => ({
              ...c,
              percentage: Math.round((c.amount / newTotal) * 100),
            })),
            {
              name: catName,
              icon: catIcon,
              amount,
              itemCount,
              percentage: Math.round((amount / newTotal) * 100),
            },
          ];

      const payerCount = state.summary.perPerson.length || 1;
      const baseShare = Math.floor(amount / payerCount);
      const remainder = amount - baseShare * payerCount;
      const updatedPerPerson = state.summary.perPerson.map((p, idx) => {
        const isPayer = p.memberId === paidByMemberId;
        const thisShare = baseShare + (idx === 0 ? remainder : 0);
        return {
          ...p,
          totalPaid: isPayer ? p.totalPaid + amount : p.totalPaid,
          share: p.share + thisShare,
          balance: isPayer
            ? p.balance + (amount - thisShare)
            : p.balance - thisShare,
        };
      });

      const activity = {
        id: `act-${Date.now()}`,
        type: "order" as const,
        description: `${platform} order`,
        amount,
        timestamp: new Date().toISOString(),
        involvedMembers: paidByName ? [paidByName] : [],
      };

      return {
        summary: {
          ...state.summary,
          totalAmount: newTotal,
          orderCount: newOrderCount,
          categories: updatedCategories,
          perPerson: updatedPerPerson,
          activities: [activity, ...state.summary.activities],
        },
      };
    }),
}));

// ─── Onboarding Store ───
//
// Holds the in-progress onboarding scratch buffer. On finish, the
// orchestrator commits these into the long-lived stores
// (`useHouseholdStore`, `useTasteStore`, `useKitchenCapacityStore`) and
// calls `reset()`. The fields below extend the legacy v1 shape with the
// "minimum intelligence" data model defined in the redesigned flow:
//
//   • `dietByMember` — structured diet (veg / eggetarian / non-veg) +
//     hard allergies per member. Drives MealSuggestion safety filters.
//   • `cookRepertoireSlugs` — the seed list of dishes the cook actually
//     makes today, picked from the photo grid in step 5. Mapped into
//     `Cook.repertoire` (display-name strings) on commit.
//   • `tasteSeed` — what the household swiped on in step 6. Mapped into
//     `useTasteStore` on commit.
//   • `kitchen` — burners + which meals to orchestrate, captured in
//     step 3. Mapped into `useKitchenCapacityStore` on commit.

export type DietPreset = "veg" | "eggetarian" | "non_veg";

export interface MemberDiet {
  memberId: string;
  preset: DietPreset;
  /** Hard allergies — selected from a chip list, never typed. */
  allergies: string[];
}

export interface OnboardingTasteSeed {
  /** Slug → verdict, matches DISH_IMAGES keys + slugifyDishName(). */
  verdicts: Record<string, "loved" | "liked" | "disliked">;
}

export interface OnboardingKitchen {
  burners: 1 | 2 | 3 | 4;
  orchestratedMeals: ("breakfast" | "lunch" | "dinner")[];
  /** HH:mm 24-hour, per slot. */
  mealTimes: { breakfast: string; lunch: string; dinner: string };
}

// ─── New onboarding intelligence inputs (v3) ───
//
// Added during the "feels like a questionnaire" rewrite. These map to
// the missing critical inputs the previous flow ignored: cuisine
// tradition, household-level diet profile, day-x-meal eat-in pattern,
// and a richer cook profile that supports cook-via-WhatsApp briefing
// with SMS fallback.

export type CityKey = "bangalore" | "mumbai" | "delhi_ncr" | "hyderabad" | "chennai" | "pune" | "kolkata" | "other";

export type CuisineTradition =
  | "north_indian"
  | "south_indian"
  | "bengali"
  | "maharashtrian"
  | "gujarati"
  | "everything"
  | "continental";

/**
 * Household-level diet profile. Multi-select facets — a household can
 * be "eggs ok + non-veg weekends + no onion garlic" all at once. The
 * facets compose; we don't reduce them to a single preset because that
 * loses signal we'll use to rank suggestions per-day.
 */
export type DietFacet =
  | "pure_veg"          // no eggs, no meat
  | "eggs_ok"           // veg + eggs
  | "non_veg_weekends"  // chicken/fish on Sat/Sun
  | "non_veg_weekdays"  // anytime
  | "no_onion_garlic"   // sattvik
  | "no_beef"           // common Hindu households
  | "no_pork"           // common Muslim households
  | "jain";             // no root vegetables

/** Day x meal grid: 21 boolean cells. Default reflects a typical
 *  Bangalore working-couple cohort: weekday dinners + all weekend meals.
 */
export interface EatInPattern {
  /** Keys: "mon-breakfast" / "mon-lunch" / "mon-dinner" / ... / "sun-dinner" */
  cells: Record<string, boolean>;
}

export const DEFAULT_EAT_IN_PATTERN: EatInPattern = {
  cells: {
    "mon-breakfast": true,  "mon-lunch": false, "mon-dinner": true,
    "tue-breakfast": true,  "tue-lunch": false, "tue-dinner": true,
    "wed-breakfast": true,  "wed-lunch": false, "wed-dinner": true,
    "thu-breakfast": true,  "thu-lunch": false, "thu-dinner": true,
    "fri-breakfast": true,  "fri-lunch": false, "fri-dinner": false,
    "sat-breakfast": true,  "sat-lunch": true,  "sat-dinner": true,
    "sun-breakfast": true,  "sun-lunch": true,  "sun-dinner": true,
  },
};

export interface OnboardingCookProfile {
  /** What the household calls her at home — "Geeta" / "Akka" / "Didi" / "Aunty". */
  displayName: string;
  /** Optional first name if the user knows it. */
  realName?: string;
  whatsappNumber: string;
  hasWhatsapp: boolean;
  slot: "morning" | "evening" | "both";
  workingDays: string[];
}

export const DEFAULT_COOK_PROFILE: OnboardingCookProfile = {
  displayName: "",
  whatsappNumber: "",
  hasWhatsapp: true,
  slot: "evening",
  workingDays: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
};

interface OnboardingStore {
  step: number;
  householdType: HouseholdType | null;
  members: HouseholdMember[];
  cook: Cook | null;
  hasCook: boolean;
  dietByMember: Record<string, MemberDiet>;
  cookRepertoireSlugs: string[];
  tasteSeed: OnboardingTasteSeed;
  kitchen: OnboardingKitchen;

  // ── v3 conversational-flow inputs ──
  city: CityKey | null;
  cuisineTraditions: CuisineTradition[];
  dietProfile: DietFacet[];
  allergies: string[];
  eatInPattern: EatInPattern;
  cookProfile: OnboardingCookProfile;
  /** When true, the user explicitly tapped "I'll send the WhatsApp ask later". */
  cookBriefDeferred: boolean;

  setStep: (s: number) => void;
  setHouseholdType: (t: HouseholdType) => void;
  addOnboardMember: (m: HouseholdMember) => void;
  removeOnboardMember: (id: string) => void;
  setOnboardCook: (c: Cook) => void;
  setHasCook: (v: boolean) => void;
  setMemberDiet: (memberId: string, diet: Omit<MemberDiet, "memberId">) => void;
  toggleCookRepertoireSlug: (slug: string) => void;
  setTasteVerdict: (slug: string, verdict: "loved" | "liked" | "disliked") => void;
  clearTasteVerdict: (slug: string) => void;
  setKitchen: (k: Partial<OnboardingKitchen>) => void;

  setCity: (c: CityKey) => void;
  toggleCuisineTradition: (t: CuisineTradition) => void;
  toggleDietFacet: (f: DietFacet) => void;
  toggleAllergy: (a: string) => void;
  toggleEatInCell: (key: string) => void;
  setCookProfile: (p: Partial<OnboardingCookProfile>) => void;
  setCookBriefDeferred: (v: boolean) => void;

  reset: () => void;
}

const DEFAULT_KITCHEN: OnboardingKitchen = {
  burners: 2,
  orchestratedMeals: ["dinner"],
  mealTimes: { breakfast: "08:30", lunch: "13:30", dinner: "20:00" },
};

export const useOnboardingStore = create<OnboardingStore>((set) => ({
  step: 0,
  householdType: null,
  members: [],
  cook: null,
  hasCook: true,
  dietByMember: {},
  cookRepertoireSlugs: [],
  tasteSeed: { verdicts: {} },
  kitchen: { ...DEFAULT_KITCHEN },

  city: null,
  cuisineTraditions: [],
  dietProfile: [],
  allergies: [],
  eatInPattern: { cells: { ...DEFAULT_EAT_IN_PATTERN.cells } },
  cookProfile: { ...DEFAULT_COOK_PROFILE },
  cookBriefDeferred: false,

  setStep: (step) => set({ step }),
  setHouseholdType: (householdType) => set({ householdType }),
  addOnboardMember: (m) => set((state) => ({ members: [...state.members, m] })),
  removeOnboardMember: (id) =>
    set((state) => {
      const nextDiet = { ...state.dietByMember };
      delete nextDiet[id];
      return {
        members: state.members.filter((m) => m.id !== id),
        dietByMember: nextDiet,
      };
    }),
  setOnboardCook: (cook) => set({ cook }),
  setHasCook: (hasCook) => set({ hasCook }),
  setMemberDiet: (memberId, diet) =>
    set((state) => ({
      dietByMember: { ...state.dietByMember, [memberId]: { memberId, ...diet } },
    })),
  toggleCookRepertoireSlug: (slug) =>
    set((state) => ({
      cookRepertoireSlugs: state.cookRepertoireSlugs.includes(slug)
        ? state.cookRepertoireSlugs.filter((s) => s !== slug)
        : [...state.cookRepertoireSlugs, slug],
    })),
  setTasteVerdict: (slug, verdict) =>
    set((state) => ({
      tasteSeed: {
        verdicts: { ...state.tasteSeed.verdicts, [slug]: verdict },
      },
    })),
  clearTasteVerdict: (slug) =>
    set((state) => {
      const next = { ...state.tasteSeed.verdicts };
      delete next[slug];
      return { tasteSeed: { verdicts: next } };
    }),
  setKitchen: (k) => set((state) => ({ kitchen: { ...state.kitchen, ...k } })),

  setCity: (city) => set({ city }),
  toggleCuisineTradition: (t) =>
    set((state) => ({
      cuisineTraditions: state.cuisineTraditions.includes(t)
        ? state.cuisineTraditions.filter((x) => x !== t)
        : [...state.cuisineTraditions, t],
    })),
  toggleDietFacet: (f) =>
    set((state) => ({
      dietProfile: state.dietProfile.includes(f)
        ? state.dietProfile.filter((x) => x !== f)
        : [...state.dietProfile, f],
    })),
  toggleAllergy: (a) =>
    set((state) => ({
      allergies: state.allergies.includes(a)
        ? state.allergies.filter((x) => x !== a)
        : [...state.allergies, a],
    })),
  toggleEatInCell: (key) =>
    set((state) => ({
      eatInPattern: {
        cells: { ...state.eatInPattern.cells, [key]: !state.eatInPattern.cells[key] },
      },
    })),
  setCookProfile: (p) =>
    set((state) => ({ cookProfile: { ...state.cookProfile, ...p } })),
  setCookBriefDeferred: (cookBriefDeferred) => set({ cookBriefDeferred }),

  reset: () =>
    set({
      step: 0,
      householdType: null,
      members: [],
      cook: null,
      hasCook: true,
      dietByMember: {},
      cookRepertoireSlugs: [],
      tasteSeed: { verdicts: {} },
      kitchen: { ...DEFAULT_KITCHEN },
      city: null,
      cuisineTraditions: [],
      dietProfile: [],
      allergies: [],
      eatInPattern: { cells: { ...DEFAULT_EAT_IN_PATTERN.cells } },
      cookProfile: { ...DEFAULT_COOK_PROFILE },
      cookBriefDeferred: false,
    }),
}));

// ─── Recipe Source Store ───

interface RecipeSourceStore {
  recipes: RecipeSource[];
  addRecipe: (recipe: RecipeSource) => void;
  removeRecipe: (id: string) => void;
  setDefault: (id: string, dishName: string) => void;
  updateRecipe: (id: string, data: Partial<RecipeSource>) => void;
  getForDish: (dishName: string) => RecipeSource[];
  getDefaultForDish: (dishName: string) => RecipeSource | undefined;
}

export const useRecipeSourceStore = create<RecipeSourceStore>((set, get) => ({
  recipes: [
    { id: "r-001", dishName: "Chole Bhature", youtubeUrl: "https://youtube.com/watch?v=example1", channelName: "Ranveer Brar", videoTitle: "Perfect Chole Bhature Recipe", contributedByName: "Anjan", contributedByRole: "member", avgRating: 4.5, timesUsed: 3, isCookApproved: true, isDefault: true },
    { id: "r-002", dishName: "Chole Bhature", youtubeUrl: "https://youtube.com/watch?v=example2", channelName: "Kunal Kapur", videoTitle: "Restaurant Style Chole", contributedByName: "Mayank", contributedByRole: "member", avgRating: 4.0, timesUsed: 1, isCookApproved: false, isDefault: false },
    { id: "r-003", dishName: "Rajma Chawal", youtubeUrl: "https://youtube.com/watch?v=example3", channelName: "Nisha Madhulika", videoTitle: "Rajma Chawal - Dhabha Style", contributedByName: "Garvika", contributedByRole: "member", avgRating: 4.8, timesUsed: 5, isCookApproved: true, isDefault: true },
    { id: "r-004", dishName: "Dal Tadka", youtubeUrl: "https://youtube.com/watch?v=example4", channelName: "Sanjeev Kapoor", videoTitle: "Dal Tadka Restaurant Style", contributedByRole: "cook", contributedByName: "Malti Didi", avgRating: 4.2, timesUsed: 7, isCookApproved: true, isDefault: true },
  ],
  addRecipe: (recipe) => set((state) => ({ recipes: [...state.recipes, recipe] })),
  removeRecipe: (id) => set((state) => ({ recipes: state.recipes.filter((r) => r.id !== id) })),
  setDefault: (id, dishName) =>
    set((state) => ({
      recipes: state.recipes.map((r) =>
        r.dishName === dishName ? { ...r, isDefault: r.id === id } : r
      ),
    })),
  updateRecipe: (id, data) =>
    set((state) => ({
      recipes: state.recipes.map((r) => (r.id === id ? { ...r, ...data } : r)),
    })),
  getForDish: (dishName) => get().recipes.filter((r) => r.dishName === dishName),
  getDefaultForDish: (dishName) => get().recipes.find((r) => r.dishName === dishName && r.isDefault),
}));

// ─── Leftover Store ───

interface LeftoverStore {
  leftovers: LeftoverItem[];
  addLeftover: (item: LeftoverItem) => void;
  consumeLeftover: (id: string) => void;
  disposeLeftover: (id: string) => void;
  activeLeftovers: () => LeftoverItem[];
}

export const useLeftoverStore = create<LeftoverStore>((set, get) => ({
  leftovers: [
    { id: "lo-001", dishName: "Dal Tadka", mealDate: localIsoDate(), mealType: "dinner", portionsRemaining: 2, isConsumed: false, isDisposed: false, isSafe: true, notes: "Made extra" },
  ],
  addLeftover: (item) => set((state) => ({ leftovers: [...state.leftovers, item] })),
  consumeLeftover: (id) =>
    set((state) => ({
      leftovers: state.leftovers.map((lo) =>
        lo.id === id ? { ...lo, isConsumed: true } : lo
      ),
    })),
  disposeLeftover: (id) =>
    set((state) => ({
      leftovers: state.leftovers.map((lo) =>
        lo.id === id ? { ...lo, isDisposed: true } : lo
      ),
    })),
  activeLeftovers: () => get().leftovers.filter((lo) => !lo.isConsumed && !lo.isDisposed && lo.isSafe),
}));

// ─── Health Tracking Store ───

interface HealthStore {
  metrics: HealthMetric[];
  addMetric: (metric: HealthMetric) => void;
  getMetricsForPerson: (personId: string) => HealthMetric[];
  getLatestMetric: (personId: string, metricType: string) => HealthMetric | undefined;
}

export const useHealthStore = create<HealthStore>((set, get) => ({
  metrics: [
    { id: "hm-001", personId: "v-001", personName: "Anjan", metricType: "weight", value: 78, unit: "kg", dateRecorded: "2026-04-01", source: "manual", status: "normal" },
    { id: "hm-002", personId: "v-001", personName: "Anjan", metricType: "weight", value: 77.2, unit: "kg", dateRecorded: "2026-04-15", source: "manual", status: "normal" },
    { id: "hm-003", personId: "c-001", personName: "Arun", metricType: "a1c", value: 6.2, unit: "%", dateRecorded: "2026-01-15", source: "lab_report", status: "warning" },
    { id: "hm-004", personId: "c-001", personName: "Arun", metricType: "a1c", value: 5.9, unit: "%", dateRecorded: "2026-04-10", source: "lab_report", status: "warning" },
    { id: "hm-005", personId: "c-001", personName: "Arun", metricType: "bp_systolic", value: 132, unit: "mmHg", dateRecorded: "2026-04-10", source: "manual", status: "warning" },
  ],
  addMetric: (metric) => set((state) => ({ metrics: [...state.metrics, metric] })),
  getMetricsForPerson: (personId) => get().metrics.filter((m) => m.personId === personId),
  getLatestMetric: (personId, metricType) => {
    const filtered = get().metrics.filter((m) => m.personId === personId && m.metricType === metricType);
    return filtered.sort((a, b) => b.dateRecorded.localeCompare(a.dateRecorded))[0];
  },
}));

// ─── Guest Store ───

interface GuestStore {
  profiles: GuestProfile[];
  visits: GuestVisit[];
  addProfile: (profile: GuestProfile) => void;
  addVisit: (visit: GuestVisit) => void;
  cancelVisit: (id: string) => void;
  getActiveVisits: (mealDate: string) => GuestVisit[];
  totalGuestCount: (mealDate: string) => number;
}

export const useGuestStore = create<GuestStore>((set, get) => ({
  profiles: [
    { id: "gp-001", name: "Sharma Uncle", dietaryType: "vegetarian", allergies: ["nuts"], visitCount: 3, lastVisit: "2026-03-15" },
    { id: "gp-002", name: "Meera Aunty", dietaryType: "vegetarian", visitCount: 5, lastVisit: "2026-04-01" },
  ],
  visits: [],
  addProfile: (profile) => set((state) => ({ profiles: [...state.profiles, profile] })),
  addVisit: (visit) =>
    set((state) => ({
      visits: [...state.visits, visit],
      profiles: state.profiles.map((p) =>
        p.name.toLowerCase() === visit.guestName.toLowerCase()
          ? { ...p, visitCount: p.visitCount + 1, lastVisit: visit.mealDate }
          : p
      ),
    })),
  cancelVisit: (id) =>
    set((state) => ({
      visits: state.visits.map((v) => (v.id === id ? { ...v, isActive: false } : v)),
    })),
  getActiveVisits: (mealDate) => get().visits.filter((v) => v.mealDate === mealDate && v.isActive),
  totalGuestCount: (mealDate) =>
    get().visits
      .filter((v) => v.mealDate === mealDate && v.isActive)
      .reduce((sum, v) => sum + v.headCount, 0),
  setGuestsFromBackend: (backendGuests: any[]) => {
    const mapped: GuestProfile[] = backendGuests.map((g: any) => ({
      id: g.id,
      name: g.name,
      dietaryType: g.dietary_type || "not_set",
      allergies: g.allergies || [],
      healthConditions: g.health_conditions || [],
      notes: g.notes,
      visitCount: g.visit_count || 0,
      lastVisit: g.last_visit,
    }));
    if (mapped.length > 0) set({ profiles: mapped });
  },
}));

// ─── Notification Preferences Store ───

interface NotificationPrefsStore {
  prefs: Record<string, boolean>;
  togglePref: (key: string) => void;
}

export const useNotificationPrefsStore = create<NotificationPrefsStore>((set) => ({
  prefs: {
    morning_briefing: true,
    voting_reminders: true,
    order_updates: true,
    cook_messages: true,
    low_stock_alerts: true,
    expense_reminders: true,
  },
  togglePref: (key) =>
    set((state) => ({
      prefs: { ...state.prefs, [key]: !state.prefs[key] },
    })),
}));

// ─── Salary Store ───

interface SalaryStore {
  payments: Array<{ cookId: string; month: string; amount: number; paidAt: string; paidBy: string }>;
  markPaid: (cookId: string, month: string, amount: number, paidBy: string) => void;
  isPaid: (cookId: string, month: string) => boolean;
}

export const useSalaryStore = create<SalaryStore>((set, get) => ({
  payments: [],
  markPaid: (cookId, month, amount, paidBy) =>
    set((state) => ({
      payments: [...state.payments, { cookId, month, amount, paidAt: new Date().toISOString(), paidBy }],
    })),
  isPaid: (cookId, month) => get().payments.some((p) => p.cookId === cookId && p.month === month),
}));

// ─── Cook Absence Store ───

interface CookAbsenceStore {
  absences: CookAbsenceEvent[];
  addAbsence: (absence: CookAbsenceEvent) => void;
  /** Pass `null` for `fallback` to un-resolve (e.g., the "Change" link
   *  in the cook-off banner returns the absence to its action-needed
   *  state so the picker re-appears). */
  chooseFallback: (id: string, fallback: CookAbsenceFallback | null, details?: string) => void;
  getCookLeavesUsed: (month: string) => number;
  /** Replace local absences with the server's view, preserving local-only
   *  entries: synthetic `weekly:*` (recurring schedule materialisations)
   *  and in-flight `temp-*` (POSTs that haven't returned yet). */
  hydrateFromBackend: (serverAbsences: CookAbsenceEvent[]) => void;
  /** Swap a local sentinel id (`temp-*` / `weekly:*`) for the backend's
   *  UUID after a successful POST so subsequent PATCH calls have a real
   *  id to target. */
  swapAbsenceId: (oldId: string, newId: string) => void;
}

const _demoTomorrow = localIsoDatePlus(1);

// Demo seed only fires in dev builds (Expo dev client / Maestro flows).
// Production hydrates from `GET /api/absences` via useLiveSync — fresh
// installs start with an empty list, no fake "Malti off tomorrow".
const _initialAbsences: CookAbsenceEvent[] = __DEV__
  ? [
      { id: "demo-abs-1", cookName: "Malti Didi", date: _demoTomorrow, reason: "Kal nahi aa paungi — doctor appointment", replacementBooked: false },
    ]
  : [];

export const useCookAbsenceStore = create<CookAbsenceStore>((set, get) => ({
  absences: _initialAbsences,
  addAbsence: (absence) => {
    set((state) => ({ absences: [...state.absences, absence] }));
    const plan = getActivePlan(useMealStore.getState());
    if (plan.prepStatus === "assigned_cook") {
      useMealStore.getState().assignPrepToUser();
    }
  },
  chooseFallback: (id, fallback, details) =>
    set((state) => ({
      absences: state.absences.map((a) =>
        a.id === id
          ? {
              ...a,
              // `null` un-resolves the absence; spreading `undefined`
              // wouldn't delete the existing key, so we delete it
              // explicitly via destructuring.
              ...(fallback === null
                ? (() => {
                    const { fallbackChosen, fallbackDetails, ...rest } = a;
                    return rest;
                  })()
                : { fallbackChosen: fallback, fallbackDetails: details }),
            }
          : a,
      ),
    })),
  getCookLeavesUsed: (month: string) =>
    get().absences.filter((a) => a.date.startsWith(month)).length,
  hydrateFromBackend: (serverAbsences) => {
    const incomingIds = new Set(serverAbsences.map((a) => a.id));
    // Preserve local-only entries:
    //   - `weekly:*` — synthetic views of the recurring schedule that
    //     the backend doesn't track (POSTed only on user action).
    //   - `temp-*`   — optimistic in-flight POSTs that haven't been
    //     swapped to the real UUID yet.
    //   - any other local id the server hasn't returned (rare; usually
    //     means the network was down when it was added).
    const localPreserved = get().absences.filter(
      (a) =>
        a.id.startsWith("weekly:") ||
        a.id.startsWith("temp-") ||
        !incomingIds.has(a.id),
    );
    set({ absences: [...serverAbsences, ...localPreserved] });
  },
  swapAbsenceId: (oldId, newId) =>
    set((state) => ({
      absences: state.absences.map((a) =>
        a.id === oldId ? { ...a, id: newId } : a,
      ),
    })),
}));

// 2026-05-03 audit (FRONTEND-BACKEND-COORDINATION.md): the
// `useInstacookStore` Zustand slice was retired alongside the Insta
// Cook backend. It tracked active/recent bookings, fast-track
// enablement per absence window, and the 10-second undo countdown
// after an auto-book. None of those concepts apply now that Bimi
// only coordinates the household cook (no on-demand booking flow).
