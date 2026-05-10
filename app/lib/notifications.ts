import { create } from "zustand";
import type { NotificationType } from "./types";

export type { NotificationType } from "./types";

export interface AppNotification {
  id: string;
  type: NotificationType;
  title: string;
  body: string;
  timestamp: string;
  read: boolean;
  actionRoute?: string;
  actionLabel?: string;
}

interface NotificationStore {
  notifications: AppNotification[];
  /** @deprecated Derive via `notifications.filter(n => !n.read).length`. */
  unreadCount: number;
  addNotification: (n: Omit<AppNotification, "id" | "timestamp" | "read">) => void;
  markRead: (id: string) => void;
  markUnread: (id: string) => void;
  markAllRead: () => void;
  /** Dismiss a single notification (swipe-to-dismiss). */
  dismiss: (id: string) => void;
  clearAll: () => void;
}

export const useNotificationStore = create<NotificationStore>((set, get) => ({
  notifications: [
    // 2026-05-03 audit (FRONTEND-BACKEND-COORDINATION.md): the
    // /(tabs)/voting, /(tabs)/approvals, and /(tabs)/kitchen tabs are
    // DELETED (see app/app/(tabs)/_layout.tsx). Voting + approvals
    // folded into the Today tab as inline heroes; "Kitchen" was
    // re-cast as the standalone /your-kitchen stack. Any actionRoute
    // pointing at the dead tabs would dump the user onto Expo Router's
    // "Unmatched Route" screen on tap. The seeds below have been
    // re-routed to surviving destinations. The new +not-found.tsx
    // catch-all is a belt-and-braces safety net for any stale link
    // that slips through (push payloads from older app versions, etc).
    {
      id: "n-001", type: "order_pending",
      title: "New Order from Malti Didi",
      body: "₹729 — Atta, Toor Dal, Butter. Your share: ₹243.",
      timestamp: new Date(Date.now() - 3600000).toISOString(),
      read: false, actionRoute: "/(tabs)", actionLabel: "Review Order",
    },
    {
      id: "n-002", type: "cook_message",
      title: "Malti Didi sent a voice note",
      body: "Atta almost over, tomato and onion also very less.",
      timestamp: new Date(Date.now() - 7200000).toISOString(),
      read: false, actionRoute: "/cook-chat", actionLabel: "View Message",
    },
    {
      id: "n-003", type: "prep_reminder",
      title: "Prep Reminder for Tomorrow",
      body: "Soak chole tonight if Chole Bhature is selected.",
      timestamp: new Date(Date.now() - 1800000).toISOString(),
      read: false, actionRoute: "/(tabs)", actionLabel: "View Plan",
    },
    {
      id: "n-004", type: "low_stock",
      title: "8 Items Running Low",
      body: "Milk (1d), Paneer (2d), Tomato (2d) need restocking.",
      timestamp: new Date(Date.now() - 5400000).toISOString(),
      read: true, actionRoute: "/your-kitchen", actionLabel: "View Kitchen",
    },
    {
      id: "n-005", type: "vote_reminder",
      title: "Vote for Tomorrow's Meals",
      body: "Voting closes at 8 PM. 1/3 flatmates have voted.",
      timestamp: new Date(Date.now() - 900000).toISOString(),
      read: false, actionRoute: "/(tabs)", actionLabel: "Vote Now",
    },
    {
      id: "n-006", type: "order_auto_approved",
      title: "Order Auto-Approved",
      body: "₹140 (Onion, Tomato, Chillies) — under ₹500 rule. Your share: ₹47.",
      timestamp: new Date(Date.now() - 86400000).toISOString(),
      read: true, actionRoute: "/(tabs)", actionLabel: "View Order",
    },
    {
      id: "n-007", type: "proxy_vote_cast",
      title: "Bimi voted for Mayank",
      body: "Predicted: Dal Tadka (82% confident). Mayank can override.",
      timestamp: new Date(Date.now() - 7200000).toISOString(),
      read: false, actionRoute: "/(tabs)",
    },
    {
      id: "n-008", type: "you_owe",
      title: "Monthly Summary",
      body: "March groceries: ₹7,890. You owe Anjan ₹612.",
      timestamp: new Date(Date.now() - 604800000).toISOString(),
      read: true, actionRoute: "/(tabs)/expenses", actionLabel: "View Expenses",
    },
    {
      id: "n-009", type: "member_joined",
      title: "Garvika joined Flat 114, Tower 6",
      body: "New flatmate! Non-vegetarian, no allergies. Expense split updated.",
      timestamp: new Date(Date.now() - 172800000).toISOString(),
      read: true, actionRoute: "/(tabs)/settings", actionLabel: "View Members",
    },
    {
      id: "n-010", type: "morning_readiness",
      title: "All Ready for Today!",
      body: "Rajma Chawal ingredients confirmed. Cook arrives at 7 PM.",
      timestamp: new Date(Date.now() - 36000000).toISOString(),
      read: true, actionRoute: "/(tabs)", actionLabel: "View Today",
    },
    {
      id: "n-011", type: "prep_check",
      title: "Quick check",
      body: "Did you soak the chole for tomorrow's lunch? Tap to confirm, or I'll switch to a backup.",
      timestamp: new Date(Date.now() - 10800000).toISOString(),
      read: false, actionRoute: "/(tabs)", actionLabel: "Confirm Prep",
    },
    // The two `instacook_sunday_promo` demo notifications ("Try Insta Cook
    // this Sunday" and "No cook today?") were removed on user request — felt
    // pushy on a fresh load and didn't match the household-aware tone Bimi
    // is moving toward (PRD §4.13). The notification *type* and the backend
    // triggers (services/instacook_notifications.py + tasks/instacook_nudge.py)
    // are still in place for production behaviour; only the demo seeds are
    // gone here.
  ],
  unreadCount: 0,
  addNotification: (n) =>
    set((state) => ({
      notifications: [
        { ...n, id: `n-${Date.now()}`, timestamp: new Date().toISOString(), read: false },
        ...state.notifications,
      ],
    })),
  markRead: (id) =>
    set((state) => ({
      notifications: state.notifications.map((n) => (n.id === id ? { ...n, read: true } : n)),
    })),
  markUnread: (id) =>
    set((state) => ({
      notifications: state.notifications.map((n) => (n.id === id ? { ...n, read: false } : n)),
    })),
  markAllRead: () =>
    set((state) => ({
      notifications: state.notifications.map((n) => ({ ...n, read: true })),
    })),
  dismiss: (id) =>
    set((state) => ({
      notifications: state.notifications.filter((n) => n.id !== id),
    })),
  clearAll: () => set({ notifications: [] }),
}));
