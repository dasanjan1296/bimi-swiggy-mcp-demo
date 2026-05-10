/**
 * Dev-only auto-login helper.
 *
 * When the app boots in __DEV__ mode with either no token or a placeholder
 * "demo-token", this helper completes the real OTP login flow against the
 * seeded pilot phone number (reads `dev_otp` from the backend response).
 * Primes `useAuthStore` with the returned JWT so all authenticated API
 * calls succeed.
 *
 * Production builds are a no-op. Skipped silently if the backend is
 * unreachable or the OTP flow doesn't return `dev_otp`.
 *
 * Enable by setting the seeded phone in env (or leaving the default):
 *   EXPO_PUBLIC_DEV_LOGIN_PHONE=+919000000002
 *
 * Intended for Maestro-driven tests and local pilot demos. Never ships
 * credentials; every OTP is freshly minted against the running backend.
 */

import { useAuthStore } from "./auth-store";
import { API_BASE } from "./api-config";

// Matches the phone seeded in backend/seed.py for Priya (the demo approver).
const DEFAULT_PHONE = process.env.EXPO_PUBLIC_DEV_LOGIN_PHONE || "+919900000002";

export async function maybeDevAutoLogin(): Promise<void> {
  if (!__DEV__) return;
  // Opt-out switch for design / login-screen review:
  //   EXPO_PUBLIC_SKIP_DEV_LOGIN=1 → land on the login screen instead of
  //   the home tabs. Useful when iterating on welcome-screen visuals.
  if (process.env.EXPO_PUBLIC_SKIP_DEV_LOGIN === "1") return;

  // In dev we always refresh the JWT against the seeded phone on boot.
  // Checking "is there a token already" doesn't work because a stale/expired
  // JWT from a prior session can sit in AsyncStorage and cause 401s that
  // trigger logout + redirect-to-login before the app is usable.

  // Clear any stale token FIRST so no in-flight requests fire with it and
  // trigger the 401 interceptor -> logout -> stuck-on-login loop.
  useAuthStore.setState({
    token: null,
    childId: null,
    familyId: null,
    childName: null,
    isAuthenticated: false,
    isDemo: false,
  });

  try {
    // Prefer the dev-only direct-mint endpoint — no rate limit, no OTP.
    const devRes = await fetch(`${API_BASE}/families/auth/dev-login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ phone: DEFAULT_PHONE }),
    });
    if (!devRes.ok) {
      return;
    }
    const verifyData = (await devRes.json()) as {
      status: string;
      access_token?: string;
      child_id?: string;
      family_id?: string;
      child_name?: string;
    };
    if (!verifyData.access_token) return;

    useAuthStore.setState({
      token: verifyData.access_token,
      childId: verifyData.child_id ?? null,
      familyId: verifyData.family_id ?? null,
      childName: verifyData.child_name ?? null,
      isAuthenticated: true,
      isDemo: false,
    });
     
    console.log(
      "[dev-auto-login] authenticated as",
      verifyData.child_name,
      verifyData.child_id,
    );
  } catch {
    // Backend unreachable — fall through to demo mode so the dev shell
    // still lands on the home tab. setDemo() doesn't require network.
    useAuthStore.getState().setDemo("fam-001", "child-001", "Anjan");
    console.log("[dev-auto-login] backend unreachable — using demo session");
  }
}
