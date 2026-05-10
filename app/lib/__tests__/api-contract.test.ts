/**
 * Frontend ↔ backend contract test.
 *
 * Why: the frontend and backend evolved on parallel tracks. The 2026-05-03
 * UX redesign brief promises "Backend, data model, every Zustand store,
 * every API stays untouched" — but in reality 16 backend hardening loops
 * retired Instacook, multi-platform commerce, etc. Without an automated
 * check, drift goes unnoticed until a user taps something in production.
 *
 * What this does:
 *   1. Statically scans every `client.METHOD("/path")` call site under
 *      `lib/` + `app/` + `components/`.
 *   2. Compares against the union of routes defined in three "snapshot"
 *      files:
 *        - `BACKEND_ROUTES`: paths the backend currently exposes
 *        - `RETIRED_ROUTES`: paths that USED to exist (should fail loud)
 *        - `KNOWN_GAPS`: paths the frontend calls that have never had a
 *          backend implementation (these are tracked TODOs)
 *   3. Fails the test if a frontend call hits a route that's:
 *        - In RETIRED_ROUTES → "you're calling deleted code"
 *        - Not in any list → "new endpoint without contract update"
 *
 * To regenerate `BACKEND_ROUTES`, run from the backend:
 *   .venv/bin/python -c "from app.main import app; \
 *     [print(f'{list(r.methods - {\"HEAD\",\"OPTIONS\"})[0]} {r.path}') \
 *      for r in app.routes if hasattr(r, 'methods') and r.methods]" \
 *     | sort
 */

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, test } from "vitest";

const ROOT = join(__dirname, "..", "..");

// ─── Snapshot 1: routes the backend EXPOSES (Loops 0-16, 2026-05-03). ───
// Patterns are the path templates as FastAPI registers them, prefixed
// with `/api` (because that's what the frontend baseURL adds via /api).

const BACKEND_ROUTES = new Set<string>([
  // Auth + family setup
  "POST /families/auth/send-otp",
  "POST /families/auth/verify-otp",
  "POST /families/auth/complete-profile",
  "POST /families/auth/dev-login",
  "POST /families/auth/register",
  "POST /families/auth/token",
  "POST /families/",
  "POST /families/parents",
  "POST /families/children",
  "GET /families/{family_id}",
  "PUT /families/{family_id}/settings",
  "PATCH /families/{family_id}/cook-answer",
  "PUT /families/children/{child_id}/fcm-token",
  "GET /families/automation",
  "PATCH /families/automation",

  // Households (pre-auth onboarding)
  "GET /households/cook-status/{phone}",
  "GET /households/invite/{code}",
  "POST /households/join",
  "POST /households/register-cook",

  // Inventory (alias under /families/{id} + bare /inventory)
  "GET /inventory",
  "POST /inventory",
  "GET /inventory/low-stock",
  "POST /inventory/restock",
  "DELETE /inventory/{item_id}",
  "PUT /inventory/{item_id}",
  "GET /families/{family_id}/inventory",
  "POST /families/{family_id}/inventory",
  "GET /families/{family_id}/inventory/low-stock",
  "POST /families/{family_id}/inventory/restock",
  "DELETE /families/{family_id}/inventory/{item_id}",
  "PUT /families/{family_id}/inventory/{item_id}",

  // Voting
  "GET /families/{family_id}/voting/tomorrow",
  "POST /families/{family_id}/voting/vote",
  "GET /families/{family_id}/voting/results",
  "POST /families/{family_id}/voting/finalize",
  "POST /families/{family_id}/dish-suggestions",

  // HCG / persons
  "GET /persons/{family_id}",
  "POST /persons/{family_id}/add",
  "GET /persons/{family_id}/group-context",
  "GET /persons/{family_id}/meal-resolution",
  "GET /persons/{family_id}/{person_id}",
  "PUT /persons/{family_id}/{person_id}",
  "DELETE /persons/{family_id}/{person_id}",
  "GET /hcg/preferences/{family_id}",
  "GET /hcg/preferences/{family_id}/{person_id}",
  "GET /hcg/context/{family_id}",
  "GET /hcg/fairness/{family_id}",
  "GET /hcg/meals/suggest/{family_id}",
  "POST /hcg/evolve/{family_id}",
  "POST /hcg/know-me/start/{family_id}/{person_id}",
  "POST /hcg/know-me/answer/{family_id}/{person_id}",
  "POST /hcg/know-me/recalibrate/{family_id}/{person_id}",

  // Auto-rules
  "GET /families/{family_id}/auto-rules",
  "POST /families/{family_id}/auto-rules",
  "PUT /families/{family_id}/auto-rules/{rule_id}",
  "DELETE /families/{family_id}/auto-rules/{rule_id}",
  "POST /families/{family_id}/auto-rules/evaluate",

  // Instructions
  "GET /families/{family_id}/instructions",
  "POST /families/{family_id}/instructions",
  "POST /families/{family_id}/instructions/extract",
  "GET /families/{family_id}/instructions/today",
  "PATCH /families/{family_id}/instructions/{instruction_id}",
  "DELETE /families/{family_id}/instructions/{instruction_id}",
  "POST /families/{family_id}/instructions/{instruction_id}/compliance",

  // Leftovers, recipes, expenses, health, guests, calls, absences,
  // substitutions
  "GET /families/{family_id}/leftovers",
  "POST /families/{family_id}/leftovers",
  "POST /families/{family_id}/leftovers/{leftover_id}/consume",
  "POST /families/{family_id}/leftovers/{leftover_id}/dispose",
  "GET /families/{family_id}/recipes",
  "POST /families/{family_id}/recipes",
  "PATCH /families/{family_id}/recipes/{recipe_id}",
  "DELETE /families/{family_id}/recipes/{recipe_id}",
  "GET /families/{family_id}/recipes/for-dish/{dish_name}",
  "POST /families/{family_id}/expenses",
  "POST /families/{family_id}/expenses/budget",
  "POST /families/{family_id}/expenses/settle",
  "GET /families/{family_id}/expenses/summary/{month}",
  "GET /families/{family_id}/health/metrics",
  "POST /families/{family_id}/health/metrics",
  "GET /families/{family_id}/health/metric-types",
  "GET /families/{family_id}/health/trends/{person_id}/{metric_type}",
  "GET /families/{family_id}/guests",
  "POST /families/{family_id}/guests",
  "POST /families/{family_id}/guests/visits",
  "GET /families/{family_id}/guests/visits/{meal_date}",
  "DELETE /families/{family_id}/guests/visits/{visit_id}",
  "GET /calls",
  "POST /calls",
  "POST /calls/{call_id}/schedule",
  "POST /calls/{call_id}/complete",
  "POST /calls/{call_id}/reschedule",
  "GET /absences",
  "GET /absences/today",
  "GET /absences/upcoming",
  "POST /absences/{absence_id}/book-replacement",
  "GET /substitutions/{ingredient}",
  "POST /substitutions/seed",
  "POST /families/{family_id}/substitutions",

  // Carts (approvals)
  "GET /carts/",
  "GET /carts/{cart_id}",
  "POST /carts/{cart_id}/approve",
  "POST /carts/{cart_id}/skip",
  "POST /carts/{cart_id}/edit",
  "POST /carts/{cart_id}/mark-ordered",
  "POST /carts/{cart_id}/delivery-update",

  // Meals (legacy single-meal flow)
  "GET /meals",
  "POST /meals",
  "GET /meals/pending-feedback",
  "GET /meals/preplan",
  "POST /meals/preplan",
  "GET /meals/preplan/suggest",
  "GET /meals/preplan/{plan_id}",
  "POST /meals/select",
  "GET /meals/suggest",
  "POST /meals/{meal_id}/feedback",

  // Context
  "GET /context/{family_id}",
  "PUT /context/{family_id}",
  "GET /context/{family_id}/rejections",
  "DELETE /context/{family_id}/rejections/{rejection_id}",

  // Your Kitchen
  "GET /your-kitchen",
  "GET /your-kitchen/dish/{slug_or_id}",
  "POST /your-kitchen/notes",
  "GET /your-kitchen/notes/{slug_or_id}",
  "DELETE /your-kitchen/notes/{note_id}",
  "GET /your-kitchen/queue",
  "POST /your-kitchen/queue",
  "DELETE /your-kitchen/queue/{queue_id}",
  "POST /your-kitchen/react",

  // Recipe archive
  "GET /recipe-archive",
  "GET /recipe-archive/search",
  "GET /recipe-archive/{slug}",
  "GET /recipe-archive/{slug}/scale",
  "GET /recipe-archive/families/{family_id}/match",

  // Grocery baskets (Loop 4)
  "GET /grocery/baskets/topup",
  "POST /grocery/baskets/topup/{basket_id}/accept",
  "GET /grocery/baskets/weekly",
  "POST /grocery/baskets/weekly/{basket_id}/completed",

  // Swiggy MCP (Loop 5 — replaces multi-platform)
  "GET /swiggy/auth/start",
  "GET /swiggy/auth/callback",
  "GET /swiggy/auth/status",
  "POST /swiggy/auth/refresh",
  "DELETE /swiggy/auth/disconnect",
  "GET /swiggy/search/products",
  "GET /swiggy/search/restaurants",
  "GET /orders/platforms",
  "POST /orders/place",
  "POST /orders/swiggy/instamart/search",
  "POST /orders/swiggy/food/search",

  // Telemetry + webhook
  "POST /events",
  "GET /webhook",
  "POST /webhook",
]);

// ─── Snapshot 2: routes that USED to exist and were retired. ───
// Calls to these are bugs — the test fails loud so they get fixed.

const RETIRED_ROUTES = new Set<string>([
  // Phase 0.3 — Instacook retirement
  "POST /instacook/matches",
  "POST /instacook/menu-suggestions",
  "GET /instacook/bookings",
  "GET /instacook/bookings/{id}",
  "POST /instacook/bookings",
  "PATCH /instacook/bookings/{id}/status",
  "POST /instacook/bookings/{id}/feedback",
  "GET /instacook/household-cooks",
  "POST /instacook/estimate",
  "POST /instacook/assist-estimate",
  "POST /instacook/plan",
  "POST /instacook/voting-trigger",
  "GET /instacook/slots",
  "GET /instacook/promotions",
  "POST /instacook/bookings/{id}/verify-otp",
  "POST /instacook/bookings/dish",
  "POST /instacook/absence-rescue/prefill",
  "POST /instacook/absence-rescue/confirm",

  // Phase 0.4 — Razorpay + multi-platform retirement
  "POST /instacook/refund",
  "POST /instacook/create-order",
  "POST /instacook/verify-payment",
  "POST /orders/compare-prices",
  "POST /orders/{platformId}/auth/start",
  "POST /orders/{platformId}/auth/verify",
  "DELETE /orders/{platformId}/auth",
]);

// ─── Snapshot 3: known unimplemented routes. Each one is a TODO. ───
// Listing them here suppresses the "ghost call" failure but logs the
// gap so they're visible. Move to BACKEND_ROUTES once shipped.

const KNOWN_GAPS = new Set<string>([
  // 2026-05-03 founder calls + cleanup PR:
  //   - Bimi Gold UI deleted → membership / savings / credits
  //     hooks removed entirely
  //   - "No Insta Cook for now" → all instacook callers deleted
  //   - "Dish Catalog = Recipe Archive" → /dishes hooks repointed
  //     to /recipe-archive; the gap closes because the call site
  //     now hits a real backend route
  //   - Multi-platform retired → /orders/* hooks deleted, replaced
  //     with /swiggy/auth/*
  // Surviving documented gaps:

  // AI proxy votes — algorithm exists in tasks/ but no router endpoint.
  // Frontend calls it with a try/catch that falls back to a local
  // heuristic — see lib/api.ts:useGenerateProxyVotes.
  "POST /families/{family_id}/voting/proxy",
  // Password reset — frontend hooks exist but backend never built. Caller
  // returns success-message-on-failure to avoid leaking which numbers are
  // registered, so silent gap is currently OK.
  "POST /families/auth/reset-request",
  "POST /families/auth/reset-confirm",
  // Cook brief recording — frontend swallows the error and continues. See
  // family-api.ts:recordCookBrief for the documented gap.
  "POST /families/{family_id}/cook-briefs",
]);

// ─── Path normalization: turn template-string interpolations into
// FastAPI-style {param} placeholders so we can compare against the
// BACKEND_ROUTES snapshot. ───

function normalizePath(raw: string): string {
  let p = raw;
  // `${familyId}` → `{family_id}` etc. We don't try to be precise about
  // the parameter NAME — only the SHAPE matters for contract matching.
  p = p.replace(/\$\{[^}]+\}/g, "{p}");
  // encodeURIComponent(slug) → just `{p}` placeholder
  p = p.replace(/\$\{encodeURIComponent\([^)]+\)\}/g, "{p}");
  // Compact placeholder normalization: collapse all `{...}` to `{p}`
  p = p.replace(/\{[^/}]+\}/g, "{p}");
  return p;
}

function templateFromBackend(path: string): string {
  // Backend already uses {family_id} style. Normalize to {p} for compare.
  return path.replace(/\{[^/}]+\}/g, "{p}");
}

function asKey(method: string, path: string): string {
  return `${method.toUpperCase()} ${path}`;
}

// ─── Walk the source tree and extract every client.METHOD("path") call. ───

const CALL_RE = /client\.(get|post|put|patch|delete)\(\s*([`"'])((?:\\.|(?!\2).)+)\2/g;

function* walk(dir: string): Generator<string> {
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry === ".expo") continue;
    if (entry === "android" || entry === "ios") continue;
    const full = join(dir, entry);
    const st = statSync(full);
    if (st.isDirectory()) yield* walk(full);
    else if (/\.(ts|tsx)$/.test(entry) && !/__tests__/.test(full)) yield full;
  }
}

function extractCalls(): Array<{ file: string; line: number; method: string; path: string }> {
  const calls: Array<{ file: string; line: number; method: string; path: string }> = [];
  for (const dir of ["lib", "app", "components"]) {
    for (const file of walk(join(ROOT, dir))) {
      const text = readFileSync(file, "utf8");
      let match: RegExpExecArray | null;
      CALL_RE.lastIndex = 0;
      while ((match = CALL_RE.exec(text))) {
        const method = match[1];
        const path = match[3];
        // Skip absolute URLs (e.g. external API calls)
        if (path.startsWith("http")) continue;
        // Skip dynamically-built paths (no leading slash)
        if (!path.startsWith("/")) continue;
        const line = text.slice(0, match.index).split("\n").length;
        calls.push({
          file: file.replace(ROOT + "/", ""),
          line,
          method,
          path: normalizePath(path),
        });
      }
    }
  }
  return calls;
}

// ─── Tests ───

const ALL_BACKEND = new Set<string>(
  [...BACKEND_ROUTES].map((entry) => {
    const [method, path] = entry.split(" ");
    return asKey(method, templateFromBackend(path));
  }),
);
const ALL_RETIRED = new Set<string>(
  [...RETIRED_ROUTES].map((entry) => {
    const [method, path] = entry.split(" ");
    return asKey(method, templateFromBackend(path));
  }),
);
const ALL_KNOWN_GAPS = new Set<string>(
  [...KNOWN_GAPS].map((entry) => {
    const [method, path] = entry.split(" ");
    return asKey(method, templateFromBackend(path));
  }),
);

describe("Frontend ↔ backend API contract", () => {
  const calls = extractCalls();

  test("there are calls to extract (sanity)", () => {
    expect(calls.length).toBeGreaterThan(0);
  });

  test("no frontend call hits a RETIRED backend route", () => {
    const offenders = calls.filter((c) =>
      ALL_RETIRED.has(asKey(c.method, c.path)),
    );
    if (offenders.length === 0) return;
    const grouped = offenders.reduce<Record<string, string[]>>((acc, o) => {
      const key = asKey(o.method, o.path);
      acc[key] = acc[key] || [];
      acc[key].push(`${o.file}:${o.line}`);
      return acc;
    }, {});
    const summary = Object.entries(grouped)
      .map(
        ([key, sites]) =>
          `  ${key}\n${sites.map((s) => `      • ${s}`).join("\n")}`,
      )
      .join("\n");
    throw new Error(
      `Frontend calls ${offenders.length} retired backend route(s):\n` +
        summary +
        "\n\nThese calls 404 in production. Either (a) delete the call " +
        "site, or (b) restore the backend route + remove from RETIRED_ROUTES.",
    );
  });

  test("no frontend call hits an UNKNOWN route", () => {
    const offenders = calls.filter((c) => {
      const key = asKey(c.method, c.path);
      return (
        !ALL_BACKEND.has(key) &&
        !ALL_RETIRED.has(key) &&
        !ALL_KNOWN_GAPS.has(key)
      );
    });
    if (offenders.length === 0) return;
    const grouped = offenders.reduce<Record<string, string[]>>((acc, o) => {
      const key = asKey(o.method, o.path);
      acc[key] = acc[key] || [];
      acc[key].push(`${o.file}:${o.line}`);
      return acc;
    }, {});
    const summary = Object.entries(grouped)
      .map(
        ([key, sites]) =>
          `  ${key}\n${sites.map((s) => `      • ${s}`).join("\n")}`,
      )
      .join("\n");
    throw new Error(
      `Frontend calls ${offenders.length} route(s) not in any contract list:\n` +
        summary +
        "\n\nEither (a) add the route to BACKEND_ROUTES if it exists, " +
        "(b) add to KNOWN_GAPS if it's a documented TODO, or " +
        "(c) fix the call site if it's a typo.",
    );
  });

  // Soft check: log known gaps so they stay visible
  test("known gaps are documented", () => {
    const usedGaps = calls
      .filter((c) => ALL_KNOWN_GAPS.has(asKey(c.method, c.path)))
      .map((c) => asKey(c.method, c.path));
    const unique = new Set(usedGaps);
    // No assertion — just ensure the snapshot reflects reality. If the
    // frontend stops calling a known-gap route, you can clean it from
    // KNOWN_GAPS to keep the list honest.
    expect(unique.size).toBeLessThanOrEqual(KNOWN_GAPS.size);
  });
});
