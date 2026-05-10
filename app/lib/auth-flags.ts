/**
 * Single source of truth for "is the user in demo mode?". Three call sites
 * (api.ts, payment.ts, analytics.ts) had their own copy of the same logic
 * that compared against the magic string `"demo-token"`. The audit
 * flagged this as fragile — a typo or rename in one copy would silently
 * desync.
 *
 * Demo mode is when the auth-store has no token at all OR the token is
 * the seeded sentinel `DEMO_TOKEN`. In demo mode, all API hooks fall
 * back to mock data instead of hitting the backend.
 */

import { useAuthStore } from "./auth-store";

/** Sentinel value used by dev-bypass to mark a "logged in for demo" auth
 *  state. Never sent to a real backend; the demo-mode helpers below
 *  short-circuit before any network call. */
export const DEMO_TOKEN = "demo-token";

/**
 * True when the user is unauthenticated or holds the demo sentinel.
 * Reads useAuthStore.getState() so it works both inside and outside
 * React render trees. Prefers the explicit `isDemo` flag set by
 * setDemo()/setAuth(); falls back to the token-string compare for
 * legacy callers that haven't migrated yet.
 */
export function isDemoMode(): boolean {
  const state = useAuthStore.getState();
  if (state.isDemo) return true;
  const token = state.token;
  return !token || token === DEMO_TOKEN;
}

/**
 * Inverse for code that's clearer with a positive name. Equivalent to
 * `!isDemoMode() && token`.
 */
export function isRealAuth(): boolean {
  const state = useAuthStore.getState();
  if (state.isDemo) return false;
  const token = state.token;
  return !!token && token !== DEMO_TOKEN;
}
