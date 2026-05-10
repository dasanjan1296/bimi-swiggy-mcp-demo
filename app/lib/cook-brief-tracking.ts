/**
 * Cook-brief tracking — closes the loop on the WhatsApp brief Bimi
 * sends to the cook at the end of onboarding.
 *
 * The problem we're solving: tapping "Send via WhatsApp" calls
 * `Linking.openURL("whatsapp://send?…")` which hands off to WhatsApp
 * and we lose the user. We don't know if they tapped Send inside
 * WhatsApp; we don't know if the cook received it; we don't know if
 * she replied. The brief was the entire reason for that step — if it
 * silently fails, every Day-1 suggestion is built on a worse cook
 * repertoire than necessary.
 *
 * The loop has three states:
 *
 *   sent_pending  → user tapped "Send via WhatsApp" (intent recorded);
 *                   we haven't observed a reply yet
 *   cook_replied  → an inbound cook message arrived (any message — the
 *                   reply might be a voice note, a photo, or an
 *                   absence; we don't try to classify, just observe
 *                   that the channel is alive)
 *   nudged        → 24h elapsed without a reply; we surfaced an
 *                   in-app notification + (best-effort) system push
 *                   asking the user to resend
 *
 * Architecture:
 *
 *   • `useCookBriefStore` — Zustand list of briefs with status + the
 *     scheduled local-notification id so we can cancel.
 *   • `recordCookBriefSent()` — called by the onboarding step BEFORE
 *     `Linking.openURL`. Persists locally, fires-and-forgets a backend
 *     POST, schedules a local Expo notification at +24h.
 *   • `markCookBriefReplied()` — called by `chat-store.addMessage` on
 *     ANY inbound cook message. Cancels the scheduled notification,
 *     transitions status, no UI side-effect.
 *   • `useReconcileCookBriefs()` — called by `_layout.tsx` on app
 *     boot. Walks open briefs, checks for inbound cook messages
 *     received since `sentAt` (handles the case where the app was
 *     killed before `addMessage` could mark the brief replied), and
 *     for any brief older than 24h with no reply, surfaces the in-app
 *     reminder and marks `nudged`.
 *
 * Backend integration:
 *
 *   The backend POST is fire-and-forget. If `/families/{id}/cook-
 *   briefs` doesn't exist yet (it doesn't — this PR adds the client
 *   half only), the call 404s and we swallow it. Local store is
 *   sufficient for the MVP loop.
 *
 *   When the backend lands, two things change without touching client
 *   code:
 *     1. The POST will start returning a server brief ID (we already
 *        store it in `serverBriefId`).
 *     2. A server-side worker can take over scheduling the 24h push
 *        (more reliable than a local notification that requires the
 *        OS to keep the schedule).
 */

import { useEffect } from "react";
import { Platform } from "react-native";
import { create } from "zustand";

import { useChatStore } from "./store";
import { recordCookBrief } from "./family-api";
import { useAuthStore } from "./auth-store";

export type CookBriefStatus = "sent_pending" | "cook_replied" | "nudged";

export interface CookBriefRecord {
  id: string;
  cookName: string;
  /** Cleaned phone digits — same shape as `Cook.whatsappNumber.replace(/[^0-9]/g, "")`. */
  cookPhoneDigits: string;
  message: string;
  sentAt: string;
  status: CookBriefStatus;
  /** When `cook_replied` was set. */
  repliedAt?: string;
  /** When `nudged` was set. */
  nudgedAt?: string;
  /** Optional Expo local-notification id; we cancel this when the
   *  cook replies so the user doesn't get a redundant nudge. */
  localNotificationId?: string;
  /** Server-side id once the backend POST returns one. */
  serverBriefId?: string;
}

interface CookBriefStore {
  briefs: CookBriefRecord[];

  add: (b: CookBriefRecord) => void;
  patch: (id: string, patch: Partial<CookBriefRecord>) => void;
  /** Find the latest open brief for a phone-digit key. */
  findOpenByPhone: (cookPhoneDigits: string) => CookBriefRecord | undefined;
  /** All open (sent_pending) briefs, oldest first. */
  openBriefs: () => CookBriefRecord[];
  reset: () => void;
}

export const useCookBriefStore = create<CookBriefStore>((set, get) => ({
  briefs: [],
  add: (b) => set((state) => ({ briefs: [...state.briefs, b] })),
  patch: (id, p) =>
    set((state) => ({
      briefs: state.briefs.map((b) => (b.id === id ? { ...b, ...p } : b)),
    })),
  findOpenByPhone: (cookPhoneDigits) =>
    [...get().briefs]
      .filter((b) => b.status === "sent_pending" && b.cookPhoneDigits === cookPhoneDigits)
      .sort((a, b) => b.sentAt.localeCompare(a.sentAt))[0],
  openBriefs: () =>
    [...get().briefs]
      .filter((b) => b.status === "sent_pending")
      .sort((a, b) => a.sentAt.localeCompare(b.sentAt)),
  reset: () => set({ briefs: [] }),
}));

const FOLLOWUP_AFTER_MS = 24 * 60 * 60 * 1000; // 24 hours
/** Minimum gap between a brief send and the cook's first message that
 *  we'll count as "replied to the brief" — anything received before
 *  this is some other inbound (e.g., a chat that was already in
 *  flight). 60 seconds is generous enough to absorb message-bus delay. */
const REPLY_DEDUPE_GUARD_MS = 60 * 1000;

/**
 * Records that the user just tapped "Send via WhatsApp" for the cook
 * brief. Schedules the 24h follow-up + fires the backend POST. Safe
 * to call without notification permission — the Expo schedule call
 * is wrapped and the local record is sufficient for reconciliation
 * on app boot.
 */
export async function recordCookBriefSent(args: {
  cookName: string;
  cookPhone: string;
  message: string;
}): Promise<CookBriefRecord> {
  const cookPhoneDigits = args.cookPhone.replace(/[^0-9]/g, "");
  const briefId = `brief-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
  const sentAt = new Date().toISOString();

  const record: CookBriefRecord = {
    id: briefId,
    cookName: args.cookName,
    cookPhoneDigits,
    message: args.message,
    sentAt,
    status: "sent_pending",
  };

  useCookBriefStore.getState().add(record);

  // Best-effort backend POST. The endpoint may 404 today; we don't
  // surface the error because the local store is the source of truth.
  void (async () => {
    try {
      const familyId = useAuthStore.getState().familyId;
      if (!familyId) return;
      const result = await recordCookBrief(familyId, {
        cook_name: args.cookName,
        cook_phone: cookPhoneDigits,
        message: args.message,
        sent_at: sentAt,
      });
      if (result?.id) {
        useCookBriefStore.getState().patch(briefId, { serverBriefId: result.id });
      }
    } catch {
      /* fire-and-forget */
    }
  })();

  // Best-effort local notification at +24h. Requires the user to have
  // granted notification permission at some earlier point — we don't
  // request it here because that prompt would be jarring inside the
  // onboarding flow. Permission is requested once, post-onboarding,
  // by the existing notifications setup path.
  void (async () => {
    try {
      const Notifications = await loadExpoNotifications();
      if (!Notifications) return;
      const settings = await Notifications.getPermissionsAsync();
      if (settings.status !== "granted") return;

      const localId = await Notifications.scheduleNotificationAsync({
        content: {
          title: `Did ${args.cookName} reply?`,
          body: `If not, tap to resend the WhatsApp message I drafted yesterday.`,
          data: { briefId, deepLink: "/cook-chat" },
        },
        trigger: {
          seconds: Math.floor(FOLLOWUP_AFTER_MS / 1000),
          repeats: false,
        } as never,
      });
      useCookBriefStore.getState().patch(briefId, { localNotificationId: localId });
    } catch {
      /* notifications unavailable in dev / Expo Go without rebuild */
    }
  })();

  return record;
}

/**
 * Called by `chat-store.addMessage` whenever an inbound cook message
 * lands. If we have an open brief for this cook's phone, mark it
 * replied and cancel the scheduled local notification.
 *
 * Idempotent: returns silently if no open brief matches, or if the
 * matched brief is already `cook_replied` / `nudged`.
 */
export async function markCookBriefReplied(cookPhoneDigitsOrFull: string): Promise<void> {
  const digits = cookPhoneDigitsOrFull.replace(/[^0-9]/g, "");
  const open = useCookBriefStore.getState().findOpenByPhone(digits);
  if (!open) return;
  // Guard: ignore inbounds that landed within the dedupe window of
  // sending — those are almost always already-in-flight messages, not
  // a reply to our brief.
  if (Date.now() - new Date(open.sentAt).getTime() < REPLY_DEDUPE_GUARD_MS) return;

  useCookBriefStore.getState().patch(open.id, {
    status: "cook_replied",
    repliedAt: new Date().toISOString(),
  });

  if (open.localNotificationId) {
    try {
      const Notifications = await loadExpoNotifications();
      await Notifications?.cancelScheduledNotificationAsync(open.localNotificationId);
    } catch {
      /* ignore — best-effort cancel */
    }
  }
}

/**
 * Walks open briefs on app boot and reconciles them against (a)
 * inbound cook messages received in the meantime, and (b) the 24h
 * follow-up window. Two outcomes:
 *
 *   • Any open brief whose cook has sent at least one message after
 *     the brief's `sentAt` (plus the dedupe guard) → marked
 *     `cook_replied`. This handles the case where `addMessage` fired
 *     while the app was killed.
 *
 *   • Any remaining open brief older than 24h → marked `nudged` and
 *     a `cook_message`-typed in-app notification is enqueued asking
 *     the user to resend. This is the in-app twin of the local
 *     system notification — even if the system push was suppressed,
 *     the user sees the reminder when they next open the app.
 *
 * The hook runs once on mount. Cheap (linear in `briefs.length`).
 */
export function useReconcileCookBriefs(): void {
  const briefs = useCookBriefStore((s) => s.briefs);
  useEffect(() => {
    if (briefs.length === 0) return;
    void reconcile();
    // We deliberately don't depend on `briefs` — re-running this on
    // every brief change would loop with the patches it triggers.
    // Boot-time reconciliation is enough; runtime reconciliation
    // happens via `markCookBriefReplied` from chat-store.
     
  }, []);
}

async function reconcile(): Promise<void> {
  const store = useCookBriefStore.getState();
  const open = store.openBriefs();
  if (open.length === 0) return;

  // Pull cook messages from chat-store. We import lazily to avoid the
  // circular import (chat-store → cook-brief-tracking → chat-store).
  const messages = useChatStore.getState().messages;

  for (const brief of open) {
    const sentMs = new Date(brief.sentAt).getTime();

    // a) Any inbound cook message after the dedupe guard?
    const repliedMessage = messages.find(
      (m) =>
        m.isFromCook &&
        new Date(m.timestamp).getTime() > sentMs + REPLY_DEDUPE_GUARD_MS,
    );
    if (repliedMessage) {
      store.patch(brief.id, {
        status: "cook_replied",
        repliedAt: repliedMessage.timestamp,
      });
      if (brief.localNotificationId) {
        try {
          const Notifications = await loadExpoNotifications();
          await Notifications?.cancelScheduledNotificationAsync(brief.localNotificationId);
        } catch { /* ignore */ }
      }
      continue;
    }

    // b) Older than 24h with no reply → nudge once.
    if (Date.now() - sentMs >= FOLLOWUP_AFTER_MS) {
      store.patch(brief.id, { status: "nudged", nudgedAt: new Date().toISOString() });
      try {
         
        const { useNotificationStore } = require("./notifications");
        useNotificationStore.getState().addNotification({
          type: "cook_message",
          title: `Did ${brief.cookName} reply?`,
          body: `If not, tap to resend the WhatsApp message I drafted yesterday.`,
          actionRoute: "/cook-chat",
          actionLabel: "Resend",
        });
      } catch { /* ignore — notifications module unavailable */ }
    }
  }
}

// ────────────────────────────────────────────────────────────────────
// expo-notifications dynamic loader. We avoid a top-level import so a
// missing native module (Expo Go without the linked notification
// service, or a web build) never crashes the bundle. The loader
// returns `null` when notifications aren't available; every caller
// checks for that.
// ────────────────────────────────────────────────────────────────────

type ExpoNotificationsApi = {
  getPermissionsAsync: () => Promise<{ status: "granted" | "denied" | "undetermined" }>;
  scheduleNotificationAsync: (req: {
    content: { title: string; body: string; data?: Record<string, unknown> };
    trigger: unknown;
  }) => Promise<string>;
  cancelScheduledNotificationAsync: (id: string) => Promise<void>;
};

let cachedApi: ExpoNotificationsApi | null | undefined;

async function loadExpoNotifications(): Promise<ExpoNotificationsApi | null> {
  if (cachedApi !== undefined) return cachedApi;
  if (Platform.OS === "web") {
    cachedApi = null;
    return null;
  }
  try {
     
    const mod = require("expo-notifications");
    cachedApi = mod as ExpoNotificationsApi;
    return cachedApi;
  } catch {
    cachedApi = null;
    return null;
  }
}
