/**
 * useSwiggyDeliveryStore — single-active-order state machine for the
 * Swiggy MCP grocery delivery lifecycle.
 *
 *   idle  ──placeOrder──▶  out_for_delivery  ──markDelivered──▶  delivered
 *                                ▲                                    │
 *                                │                              dismiss│
 *                                └──────────reset (dev)─── idle ◀─────┘
 *
 * The store is in-memory by design — fresh app launch always starts at
 * `idle` so the demo recording can re-run cleanly. AsyncStorage
 * persistence is explicitly out of scope (see plan §"Out of scope").
 *
 * Demo timing: `DEMO_ETA_SECONDS = 30`. The active-delivery hero polls
 * every second while `state === "out_for_delivery"` and calls
 * `markDelivered()` once `(now - placedAt) >= DEMO_ETA_SECONDS * 1000`.
 * In production this gets replaced by a Swiggy MCP webhook.
 *
 * `markDelivered` fires the inventory auto-restock side effect — the
 * trust-based design rule (no per-item user checklist).
 */

import { create } from "zustand";
import type { ActionItem } from "./types";
import { useInventoryStore } from "./store";

/**
 * Total seconds from `placeOrder` → `markDelivered` in demo mode.
 * Long enough to show off the tracking sheet's countdown; short enough
 * to land a recorded demo in <90s end-to-end.
 */
export const DEMO_ETA_SECONDS = 30;

/**
 * Generic delivery-partner label used in demo mode. We deliberately
 * avoid a real-sounding name like "Vivek" to comply with Swiggy
 * Builders Club rules — "misrepresenting prices, availability, or
 * delivery times" / "misattributing where data comes from". When MCP
 * access is granted, this gets replaced by the real partner name from
 * the Swiggy webhook.
 */
const DEFAULT_PARTNER_LABEL = "Your delivery partner";

export type DeliveryState = "idle" | "out_for_delivery" | "delivered";

export interface SwiggyOrder {
  /** Short user-facing id (e.g. "SW-A2B3C4"). */
  orderId: string;
  /** ISO timestamp when `placeOrder` ran. */
  placedAt: string;
  /** ETA window in minutes (derived from `DEMO_ETA_SECONDS / 60` for demo). */
  etaMinutes: number;
  /** The cart items, carried verbatim from the `CookActionsSheet` submission. */
  items: ActionItem[];
  /** Sum of `estimatedPriceInr` across `items`. */
  totalInr: number;
  /** Driver name for the active-delivery hero + tracking sheet. */
  driverName: string;
}

interface SwiggyDeliveryStore {
  state: DeliveryState;
  order: SwiggyOrder | null;
  /**
   * Snapshot the active cart, kick the lifecycle into `out_for_delivery`.
   * Captures `placedAt = now` so the active-delivery hero can compute
   * the live ETA countdown.
   */
  placeOrder: (items: ActionItem[]) => void;
  /**
   * Transition `out_for_delivery → delivered` AND fire the auto-restock
   * side effect against `useInventoryStore`. The `order` is intentionally
   * KEPT (not cleared) so the delivered hero can show the totals.
   */
  markDelivered: () => void;
  /**
   * User tapped "Got it" on the delivered hero — clear the order and
   * return to `idle` so the home falls back to its default hero.
   */
  dismiss: () => void;
  /** Dev convenience: full reset to `idle` regardless of current state. */
  reset: () => void;
}

function generateOrderId(): string {
  // 6-char A-Z0-9 suffix, e.g. "SW-A2B3C4". Looks like a real Swiggy
  // reference id without colliding with the actual format.
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  let suffix = "";
  for (let i = 0; i < 6; i++) {
    suffix += chars[Math.floor(Math.random() * chars.length)];
  }
  return `SW-${suffix}`;
}

export const useSwiggyDeliveryStore = create<SwiggyDeliveryStore>((set, get) => ({
  state: "idle",
  order: null,

  placeOrder: (items) => {
    const totalInr = items.reduce(
      (sum, a) => sum + (a.estimatedPriceInr ?? 0),
      0,
    );
    set({
      state: "out_for_delivery",
      order: {
        orderId: generateOrderId(),
        placedAt: new Date().toISOString(),
        etaMinutes: Math.max(1, Math.round(DEMO_ETA_SECONDS / 60)),
        items,
        totalInr,
        driverName: DEFAULT_PARTNER_LABEL,
      },
    });
  },

  markDelivered: () => {
    const { order, state } = get();
    if (state !== "out_for_delivery" || !order) return;
    set({ state: "delivered" });
    // Auto-restock. Match heuristic is case-insensitive substring on
    // each item's `itemName` against the inventory `name` field — see
    // `useInventoryStore.restock`. The cook will WhatsApp any
    // discrepancies; we don't ask the user to confirm.
    const itemNames = order.items
      .map((it) => it.itemName ?? "")
      .filter(Boolean);
    if (itemNames.length > 0) {
      useInventoryStore.getState().restock(itemNames);
    }
  },

  dismiss: () => set({ state: "idle", order: null }),

  reset: () => set({ state: "idle", order: null }),
}));
