/**
 * Dev-only helper that hydrates the local stores with the seeded pilot
 * family so the home greeting matches the real authenticated user
 * during pilot demos.
 *
 * Background (IC-P1-04)
 * ---------------------
 * `useHouseholdStore` boots with `BACHELOR_HOUSEHOLD` from `mock-data.ts`
 * which hard-codes "Anjan" as the first member. In a fresh dev build the
 * home screen therefore reads "Hey Anjan" even when the founder is
 * demoing the seeded pilot family ("Sharma Nuclear" / "Arjun Sharma").
 *
 * Behaviour
 * ---------
 * - Only runs when `__DEV__` is true. Production builds are no-ops.
 * - Only runs when the local household still equals the placeholder
 *   bachelor seed (so we never overwrite a real signup).
 * - Requires `EXPO_PUBLIC_PILOT_FOUNDER_TOKEN` in the build environment;
 *   without it we silently skip (back to placeholder rename below).
 * - Calls `GET /api/pilot/families/me` with `X-Pilot-Founder-Token` and
 *   maps the response into the household + auth stores.
 */

import { useAuthStore } from "./auth-store";
import { DEMO_TOKEN } from "./auth-flags";
import { useHouseholdStore } from "./store";
import { BACHELOR_HOUSEHOLD } from "./mock-data";
import type { Household, HouseholdMember } from "./types";
import { API_BASE } from "./api-config";

// SECURITY: only read the founder token when in dev. Although the
// hydratePilotFamilyIfDemoMode entry-check already guards on __DEV__,
// reading the env var at module top-level would still bake the token
// into the production bundle if the EXPO_PUBLIC_PILOT_FOUNDER_TOKEN
// env var is accidentally set during a release build. Wrapping the
// read inside a `__DEV__ ? : undefined` ternary lets Metro tree-shake
// the literal away in production.
const FOUNDER_TOKEN = __DEV__
  ? process.env.EXPO_PUBLIC_PILOT_FOUNDER_TOKEN
  : undefined;

interface FamilyMeResponse {
  id: string;
  name: string;
  cohort: string | null;
  family_type: string;
  members: Array<{
    id: string;
    name: string;
    role: string;
    is_admin: boolean;
    phone: string | null;
  }>;
}

function isStillPlaceholderHousehold(): boolean {
  const current = useHouseholdStore.getState().household;
  if (!current) return true;
  return current.id === BACHELOR_HOUSEHOLD.id
    || current.members.some((m) => m.id === "v-001" && m.name === "Anjan");
}

export async function hydratePilotFamilyIfDemoMode(): Promise<void> {
  if (!__DEV__) return;
  if (!FOUNDER_TOKEN) return;
  if (!isStillPlaceholderHousehold()) return;

  try {
    const res = await fetch(`${API_BASE}/pilot/families/me`, {
      headers: { "X-Pilot-Founder-Token": FOUNDER_TOKEN },
    });
    if (!res.ok) return;
    const data = (await res.json()) as FamilyMeResponse;

    const members: HouseholdMember[] = data.members.map((m, idx) => ({
      id: m.id,
      name: m.name,
      role: (m.role as HouseholdMember["role"]) || "flatmate",
      avatar: idx === 0 ? "👨" : idx === 1 ? "👩" : "🧒",
      isPayingMember: true,
      isAdmin: m.is_admin,
      isActive: true,
      isAvailable: true,
      joinedAt: new Date().toISOString(),
      dietaryPreferences: [],
      healthConditions: [],
    }));

    const household: Household = {
      ...BACHELOR_HOUSEHOLD,
      id: data.id,
      name: data.name,
      type: data.family_type === "couple" ? "couple" :
            data.family_type === "family" ? "nuclear_family" : "flatmates",
      members,
    };

    useHouseholdStore.getState().setHousehold(household);
    useHouseholdStore.getState().setOnboarded(true);

    const primary = members[0];
    if (primary) {
      const existingToken = useAuthStore.getState().token;
      const finalToken = existingToken || DEMO_TOKEN;
      useAuthStore.setState({
        familyId: data.id,
        childId: primary.id,
        childName: primary.name,
        isAuthenticated: true,
        token: finalToken,
        // Keep isDemo aligned with the actual token type — only the
        // sentinel string counts as demo. A real JWT here means the
        // dev-bypass was layered on top of a normal auth session.
        isDemo: finalToken === DEMO_TOKEN,
      });
    }
  } catch {
    // Network or backend down -- silently skip. Placeholder remains.
  }
}
