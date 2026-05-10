/**
 * Single source of truth for the backend base URL. Imported by api.ts,
 * dev-bypass.ts, and dev-auto-login.ts so a config change lands in one
 * place — they previously each declared their own copy and could drift.
 *
 * - Dev: EXPO_PUBLIC_API_BASE_URL env override, falling back to local
 *   FastAPI on port 8000.
 * - Prod: hard-coded Fly.io URL. HTTPS only — never ship http:// to a
 *   release build.
 */

export const API_BASE = __DEV__
  ? (process.env.EXPO_PUBLIC_API_BASE_URL || "http://localhost:8000/api")
  : "https://bimi.fly.dev/api";

/** Host (no /api suffix) — used for serving /static/... assets. */
export const API_HOST = API_BASE.replace(/\/api$/, "");
