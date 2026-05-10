/**
 * Mobile-side product analytics.
 *
 * One-line API: `track('event_type', { property: value })`. Events are
 * buffered in 5-second windows and POSTed to `/api/events`, which fans
 * into the same `analytics.track` pipeline the backend uses.
 *
 * Demo mode never emits events (no auth token => nothing to attribute).
 *
 * Sentry is initialised here too -- it was installed in package.json but
 * dormant before this change.
 */

import { AppState } from "react-native";

import { client } from "./api";
import { isDemoMode } from "./auth-flags";

type EventProperties = Record<string, unknown>;

interface QueuedEvent {
  event_type: string;
  properties?: EventProperties;
  occurred_at: string;
}

const FLUSH_INTERVAL_MS = 5000;
const MAX_QUEUE_BEFORE_FORCE_FLUSH = 50;

let _queue: QueuedEvent[] = [];
let _flushTimer: ReturnType<typeof setInterval> | null = null;
let _appStateSub: { remove: () => void } | null = null;
let _initialised = false;

/**
 * Drop known-PII keys before sending. Mirrors the backend scrubber so
 * we never even put PII over the wire.
 */
const PII_KEY_PATTERNS = [
  /phone/i,
  /email/i,
  /aadhaar/i,
  /name/i,
  /address/i,
  /vpa/i,
  /token/i,
  /password/i,
  /condition/i,
  /allergy/i,
  /diagnosis/i,
  // Added per security audit medium finding — payment / OTP / signature
  // values must never reach analytics or Sentry.
  /\bpin\b/i,
  /\botp\b/i,
  /signature/i,
  /\bpa\b/i, // UPI VPA's `pa=...` query-param key
];

const PHONE_VALUE_RE = /^\+?\d[\d\s-]{7,}$/;

/**
 * Recursive scrubber. Drops keys that match PII_KEY_PATTERNS and
 * redacts string values that look like phone numbers. Walks nested
 * objects and arrays so a payload like
 *   { user: { phone: "+91…", email: "…" }, items: [{ vpa: "…" }] }
 * has the inner phone/email/vpa stripped, not just top-level keys.
 *
 * Caps recursion depth at 6 as a defence against deeply-nested or
 * cyclic input — anything beyond is replaced with a redacted marker.
 */
function scrubValue(v: unknown, depth: number): unknown {
  if (depth > 6) return "<redacted: depth>";
  if (v === null || v === undefined) return v;
  if (typeof v === "string") {
    return PHONE_VALUE_RE.test(v.trim()) ? "<redacted>" : v;
  }
  if (typeof v !== "object") return v;
  if (Array.isArray(v)) {
    return v.map((entry) => scrubValue(entry, depth + 1));
  }
  const out: Record<string, unknown> = {};
  for (const [k, vv] of Object.entries(v as Record<string, unknown>)) {
    if (PII_KEY_PATTERNS.some((re) => re.test(k))) continue;
    out[k] = scrubValue(vv, depth + 1);
  }
  return out;
}

function scrub(props?: EventProperties): EventProperties | undefined {
  if (!props) return undefined;
  return scrubValue(props, 0) as EventProperties;
}

async function flushQueue(): Promise<void> {
  if (!_queue.length || isDemoMode()) return;
  const batch = _queue;
  _queue = [];
  try {
    await client.post("/events", { events: batch });
  } catch {
    // Drop the batch silently -- analytics MUST NOT break product flow.
    // We accept losing up to ~5 seconds of telemetry on backend hiccups.
  }
}

/**
 * Public entry point. Fire-and-forget; never throws.
 */
export function track(event_type: string, properties?: EventProperties): void {
  try {
    if (isDemoMode()) return;
    _queue.push({
      event_type,
      properties: scrub(properties),
      occurred_at: new Date().toISOString(),
    });
    if (_queue.length >= MAX_QUEUE_BEFORE_FORCE_FLUSH) {
      void flushQueue();
    }
  } catch {
    // never throw from analytics
  }
}

/**
 * Idempotently start the flush timer + Sentry. Call once from the root
 * layout's effect. Re-calling is a no-op.
 */
export function initAnalytics(): void {
  if (_initialised) return;
  _initialised = true;

  _flushTimer = setInterval(() => {
    void flushQueue();
  }, FLUSH_INTERVAL_MS);

  // Flush opportunistically when the app backgrounds.
  _appStateSub = AppState.addEventListener("change", (state) => {
    if (state === "background" || state === "inactive") {
      void flushQueue();
    }
  });

  // Initialise Sentry -- previously installed-but-dormant. We pull dynamically
  // so test environments without the native module don't blow up.
  void initSentry();
}

/**
 * PII scrubber that runs over a Sentry event before it leaves the device.
 * Mirrors the analytics scrubber's PII_KEY_PATTERNS so we never leak
 * phone numbers, names, or tokens via Sentry breadcrumbs / extras.
 */
function scrubSentryEvent<T extends Record<string, any>>(event: T): T {
  const SENSITIVE_HEADERS = ["authorization", "cookie", "x-api-key"];
  // Strip Authorization + Cookie from request headers in any breadcrumb.
  if (event.breadcrumbs && Array.isArray(event.breadcrumbs)) {
    for (const crumb of event.breadcrumbs) {
      if (crumb?.data?.headers && typeof crumb.data.headers === "object") {
        for (const k of Object.keys(crumb.data.headers)) {
          if (SENSITIVE_HEADERS.includes(k.toLowerCase())) {
            crumb.data.headers[k] = "<redacted>";
          }
        }
      }
      if (typeof crumb?.message === "string") {
        crumb.message = redactStringInline(crumb.message);
      }
    }
  }
  // Strip phones / emails / names from extras.
  if (event.extra && typeof event.extra === "object") {
    for (const [k, v] of Object.entries(event.extra)) {
      if (PII_KEY_PATTERNS.some((re) => re.test(k))) {
        event.extra[k] = "<redacted>";
        continue;
      }
      if (typeof v === "string") {
        event.extra[k] = redactStringInline(v);
      }
    }
  }
  // Strip request body in Sentry's transaction request payload.
  if (event.request?.headers && typeof event.request.headers === "object") {
    for (const k of Object.keys(event.request.headers)) {
      if (SENSITIVE_HEADERS.includes(k.toLowerCase())) {
        event.request.headers[k] = "<redacted>";
      }
    }
  }
  // Drop the user.email (RN Sentry default-fills user object). Keep id.
  if (event.user && typeof event.user === "object") {
    if ("email" in event.user) delete event.user.email;
    if ("username" in event.user) delete event.user.username;
  }
  return event;
}

const PHONE_RE = /\+?\d[\d\s-]{7,}/g;
const EMAIL_RE = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g;
function redactStringInline(s: string): string {
  return s.replace(PHONE_RE, "<phone>").replace(EMAIL_RE, "<email>");
}

async function initSentry(): Promise<void> {
  try {
    const dsn = process.env.EXPO_PUBLIC_SENTRY_DSN;
    if (!dsn) return;
    const Sentry = await import("@sentry/react-native");
    Sentry.init({
      dsn,
      tracesSampleRate: 0.1,
      enableAutoSessionTracking: true,
      // Tag events so Sentry's UI can filter dev vs prod and so a single
      // release ties together the JS bundle + native crash dumps.
      environment: __DEV__ ? "development" : "production",
      release: process.env.EXPO_PUBLIC_SENTRY_RELEASE,
      // SECURITY: scrub PII before any event leaves the device. Mirrors
      // the analytics.ts scrubber so phone / email / token / cookie /
      // authorization-header values never reach Sentry's servers.
      beforeSend: (event) => scrubSentryEvent(event as any),
      beforeBreadcrumb: (breadcrumb) => {
        if (breadcrumb.message) {
          breadcrumb.message = redactStringInline(breadcrumb.message);
        }
        return breadcrumb;
      },
    });
  } catch {
    // Sentry is best-effort
  }
}

/**
 * Test/teardown helper -- not used in product code.
 */
export function _resetAnalyticsForTests(): void {
  _queue = [];
  if (_flushTimer) {
    clearInterval(_flushTimer);
    _flushTimer = null;
  }
  if (_appStateSub) {
    _appStateSub.remove();
    _appStateSub = null;
  }
  _initialised = false;
}
