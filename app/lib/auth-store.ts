import { create } from "zustand";
import { Platform } from "react-native";

interface AuthState {
  token: string | null;
  familyId: string | null;
  childId: string | null;
  childName: string | null;
  isAuthenticated: boolean;
  /**
   * Explicit demo flag — replaces the magic-string check
   * `token === "demo-token"` that lived inline across api.ts /
   * payment.ts / analytics.ts before the auth-flags consolidation.
   * Demo sessions never make authenticated network writes; they only
   * exist so the app can be exercised without the backend running.
   */
  isDemo: boolean;

  setAuth: (data: {
    token: string;
    familyId: string;
    childId: string;
    childName: string;
  }) => void;
  /** Mark the current session as a demo (no real backend writes). */
  setDemo: (familyId?: string, childId?: string, childName?: string) => void;
  logout: () => void;
  loadFromStorage: () => Promise<void>;
}

async function getSecureStore() {
  if (Platform.OS === "web") return null;
  try {
    const mod = await import("expo-secure-store");
    await mod.getItemAsync("_test");
    return mod;
  } catch {
    return null;
  }
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: null,
  familyId: null,
  childId: null,
  childName: null,
  isAuthenticated: false,
  isDemo: false,

  setAuth: async ({ token, familyId, childId, childName }) => {
    set({ token, familyId, childId, childName, isAuthenticated: true, isDemo: false });

    const secureStore = await getSecureStore();
    if (secureStore) {
      await secureStore.setItemAsync("bimi_token", token);
      await secureStore.setItemAsync("bimi_family_id", familyId);
      await secureStore.setItemAsync("bimi_child_id", childId);
      await secureStore.setItemAsync("bimi_child_name", childName);
    } else if (Platform.OS === "web") {
      localStorage.setItem("bimi_token", token);
      localStorage.setItem("bimi_family_id", familyId);
      localStorage.setItem("bimi_child_id", childId);
      localStorage.setItem("bimi_child_name", childName);
    }
  },

  setDemo: (familyId, childId, childName) => {
    // Imported here (not at module top) to avoid an import cycle with
    // auth-flags.ts.
    const { DEMO_TOKEN } = require("./auth-flags") as typeof import("./auth-flags");
    set({
      token: DEMO_TOKEN,
      familyId: familyId ?? null,
      childId: childId ?? null,
      childName: childName ?? null,
      isAuthenticated: true,
      isDemo: true,
    });
  },

  logout: async () => {
    set({ token: null, familyId: null, childId: null, childName: null, isAuthenticated: false, isDemo: false });

    const secureStore = await getSecureStore();
    if (secureStore) {
      await secureStore.deleteItemAsync("bimi_token");
      await secureStore.deleteItemAsync("bimi_family_id");
      await secureStore.deleteItemAsync("bimi_child_id");
      await secureStore.deleteItemAsync("bimi_child_name");
    } else if (Platform.OS === "web") {
      localStorage.removeItem("bimi_token");
      localStorage.removeItem("bimi_family_id");
      localStorage.removeItem("bimi_child_id");
      localStorage.removeItem("bimi_child_name");
    }

    // QA-039/040 fix: User A's household, onboarding, instacook, expenses, etc.
    // must NOT leak to User B who logs in next on the same device. Reset all
    // user-scoped Zustand stores via the centralized helper.
    try {
      const { clearAllUserScopedStores } = require("./reset-user-stores");
      await clearAllUserScopedStores();
    } catch {
      // Defensive: never block logout on a state-clear failure.
    }
  },

  loadFromStorage: async () => {
    const secureStore = await getSecureStore();
    let token: string | null = null;
    let familyId: string | null = null;
    let childId: string | null = null;
    let childName: string | null = null;

    if (secureStore) {
      token = await secureStore.getItemAsync("bimi_token");
      familyId = await secureStore.getItemAsync("bimi_family_id");
      childId = await secureStore.getItemAsync("bimi_child_id");
      childName = await secureStore.getItemAsync("bimi_child_name");
    } else if (Platform.OS === "web") {
      token = localStorage.getItem("bimi_token");
      familyId = localStorage.getItem("bimi_family_id");
      childId = localStorage.getItem("bimi_child_id");
      childName = localStorage.getItem("bimi_child_name");
    }

    if (token && familyId && childId) {
      // Re-derive isDemo on hydrate so isDemoMode()/isRealAuth() agree
      // after a cold boot from persistent storage. We don't persist
      // isDemo separately because the token sentinel is the wire format
      // anyway — but skipping this would leave hydrated demo sessions
      // looking 'real' until the next setAuth/setDemo call.
      const { DEMO_TOKEN } = require("./auth-flags") as typeof import("./auth-flags");
      set({
        token,
        familyId,
        childId,
        childName,
        isAuthenticated: true,
        isDemo: token === DEMO_TOKEN,
      });
    }
  },
}));
