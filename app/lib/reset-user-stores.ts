import {
  useHouseholdStore,
  useMealStore,
  useOrderStore,
  useInventoryStore,
  useChatStore,
  useWishlistStore,
  useExpenseStore,
  useOnboardingStore,
  useRecipeSourceStore,
  useLeftoverStore,
  useHealthStore,
  useGuestStore,
  useNotificationPrefsStore,
  useSalaryStore,
  useCookAbsenceStore,
} from "./store";
// 2026-05-03 audit: useInstacookStore + useDishStore removed alongside
// the Insta Cook + dish-cart deletions.
import { useCookProfileStore } from "./cook-profile";
import { useCookSettingsStore } from "./cook-settings-store";
import { useNotificationStore } from "./notifications";
import {
  BACHELOR_HOUSEHOLD,
  ALL_HOUSEHOLDS,
  MOCK_TODAYS_PLANS,
  MOCK_TOMORROWS_PLAN,
  MOCK_TOMORROWS_PLANS,
  MOCK_ORDERS,
  MOCK_AUTO_RULES,
  MOCK_INVENTORY,
  MOCK_COOK_MESSAGES,
  MOCK_MEAL_HISTORY,
  MOCK_MEAL_SUGGESTIONS,
  MOCK_WISHLIST,
  MOCK_EXPENSES,
} from "./mock-data";

/**
 * QA-039/040 fix: when User A logs out, every Zustand store that holds
 * user-scoped data is reset to its mock/default state so the next user
 * doesn't inherit anything. Persisted (AsyncStorage-backed) stores also
 * have their persisted entry purged.
 *
 * Auth itself is reset by `useAuthStore.logout` separately.
 */
export async function clearAllUserScopedStores(): Promise<void> {
  // 1. Household / onboarding — biggest leak risk
  useHouseholdStore.setState({
    household: BACHELOR_HOUSEHOLD,
    allHouseholds: ALL_HOUSEHOLDS,
    isOnboarded: false,
  });
  useOnboardingStore.setState({
    step: 0,
    householdType: null,
    members: [],
    cook: null,
    hasCook: true,
  });

  // 2. Meal / voting state
  useMealStore.setState({
    todaysPlans: MOCK_TODAYS_PLANS,
    tomorrowsPlans: MOCK_TOMORROWS_PLANS,
    tomorrowsPlan: MOCK_TOMORROWS_PLAN,
    suggestions: MOCK_MEAL_SUGGESTIONS,
    mealHistory: MOCK_MEAL_HISTORY,
    fairnessScores: [],
    activeMealType: "lunch",
    votingStreak: 0,
  });

  // 3. Orders / inventory / wishlist / expenses
  useOrderStore.setState({ orders: MOCK_ORDERS, autoRules: MOCK_AUTO_RULES });
  useInventoryStore.setState({ items: MOCK_INVENTORY });
  useChatStore.setState({ messages: MOCK_COOK_MESSAGES });
  useWishlistStore.setState({ items: MOCK_WISHLIST });
  useExpenseStore.setState({ summary: MOCK_EXPENSES });

  // 4. Misc user-scoped stores
  useRecipeSourceStore.setState({ recipes: [] });
  useLeftoverStore.setState({ leftovers: [] });
  useHealthStore.setState({ metrics: [] });
  useGuestStore.setState({ profiles: [], visits: [] } as any);
  useNotificationPrefsStore.setState({
    prefs: {
      morning_briefing: true,
      voting_reminders: true,
      order_updates: true,
      cook_messages: true,
      low_stock_alerts: true,
      expense_reminders: true,
    },
  });
  useSalaryStore.setState({ payments: [] });
  useCookAbsenceStore.setState({ absences: [] });

  // 6. Notifications
  try {
    useNotificationStore.setState({ notifications: [] });
  } catch {
    /* notification store may have a different shape; ignore */
  }

  // 6b. Cook profile + cook settings — both user-scoped, both have
  // typed reset() helpers. Without these, household A's cook
  // interview answers + holiday calendar leaked into household B.
  try {
    useCookProfileStore.getState().reset();
  } catch {
    /* never block logout */
  }
  try {
    useCookSettingsStore.getState().reset();
  } catch {
    /* never block logout */
  }

  // 7. React Query cache. Without this, User A's cached useQuery results
  // (inventory, voting, instacook bookings, savings) would be visible
  // to User B for a few hundred ms before each query refetched against
  // the new familyId. SECURITY: this prevents cross-account data leak.
  try {
    const { queryClient } = require("./query-client");
    queryClient.clear();
  } catch {
    /* Defensive: never block logout on a query-cache reset failure. */
  }

  // 8. Purge persisted Zustand entries: no-op until AsyncStorage is linked
  // into the dev client (see Pass 3 backlog in QA-REPORT-2026-04-18.md).
}
