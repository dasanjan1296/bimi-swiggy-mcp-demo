/**
 * P4.4 (PRD 4.4) — Ingredient Pre-Check Pipeline.
 *
 * After a meal is finalized, automatically:
 *   1. Extract ingredients from the chosen suggestion
 *   2. Diff against current kitchen inventory
 *   3. Add missing items to the wishlist with `source: "ingredient_check"`
 *   4. Evaluate auto-approval rules (under-threshold + trusted items + window)
 *      → either auto-approve OR raise an approval request notification
 *   5. Notify the user + brief the cook with a delivery-window message
 *
 * Pure-ish: takes the stores + cook-message helper as parameters so it can
 * be exercised from a unit test without React Native imports.
 */

import type {
  AutoApprovalRule,
  InventoryItem,
  MealSuggestion,
  WishlistItem,
} from "./types";

export interface PrecheckResult {
  /** Items detected as missing from kitchen inventory. */
  missing: string[];
  /** Items already in the wishlist (added previously by another source). */
  alreadyOnList: string[];
  /** Total estimated cost of missing items, ₹. */
  estimatedTotal: number;
  /** True iff the ingredient set was auto-approved against the rules. */
  autoApproved: boolean;
  /** Which rule triggered the auto-approval, if any. */
  matchedRule?: AutoApprovalRule;
  /** Human-readable summary for the user notification. */
  summary: string;
}

const DEFAULT_PRICE_PER_ITEM = 50; // rough estimate when no price hint exists

function normalize(name: string): string {
  return name.toLowerCase().trim().replace(/\s+/g, " ");
}

function inventoryHas(inventory: InventoryItem[], ingredient: string): boolean {
  const target = normalize(ingredient);
  return inventory.some((item) => {
    const inv = normalize(item.name);
    if (item.isLowStock) return false;
    return inv.includes(target) || target.includes(inv);
  });
}

function wishlistHas(wishlist: WishlistItem[], ingredient: string): boolean {
  const target = normalize(ingredient);
  return wishlist.some((w) => {
    if (w.status !== "pending" && w.status !== "in_cart") return false;
    return normalize(w.name).includes(target) || target.includes(normalize(w.name));
  });
}

function isWithinWindow(rule: AutoApprovalRule, now: Date = new Date()): boolean {
  if (!rule.timeWindowStart || !rule.timeWindowEnd) return true;
  const [sh, sm] = rule.timeWindowStart.split(":").map((n) => parseInt(n, 10));
  const [eh, em] = rule.timeWindowEnd.split(":").map((n) => parseInt(n, 10));
  const minutesNow = now.getHours() * 60 + now.getMinutes();
  const startMin = (sh || 0) * 60 + (sm || 0);
  const endMin = (eh || 0) * 60 + (em || 0);
  return minutesNow >= startMin && minutesNow <= endMin;
}

function trustedItemsAllow(rule: AutoApprovalRule, missing: string[]): boolean {
  if (!rule.trustedItems || rule.trustedItems.length === 0) return true;
  const trusted = rule.trustedItems.map(normalize);
  return missing.every((m) => {
    const n = normalize(m);
    return trusted.some((t) => t.includes(n) || n.includes(t));
  });
}

export function evaluateAutoApproval(
  missing: string[],
  estimatedTotal: number,
  rules: AutoApprovalRule[],
): { matched?: AutoApprovalRule; reason: string } {
  for (const rule of rules) {
    if (!rule.enabled) continue;
    if (estimatedTotal > rule.maxAmount) continue;
    if (!trustedItemsAllow(rule, missing)) continue;
    if (!isWithinWindow(rule)) continue;
    return { matched: rule, reason: `under ₹${rule.maxAmount} rule` };
  }
  return { reason: "no auto-approval rule matched" };
}

export interface PrecheckDeps {
  /** Read-only inventory snapshot at the time of pre-check. */
  inventory: InventoryItem[];
  /** Read-only wishlist snapshot. */
  wishlist: WishlistItem[];
  /** Active auto-approval rules. */
  rules: AutoApprovalRule[];
  /** Add a new wishlist entry. */
  addWishlistItem: (item: WishlistItem) => void;
  /** Notify user (e.g. "12 missing items added to your cart"). */
  notify: (notif: { title: string; body: string; type?: string; actionRoute?: string }) => void;
  /** Brief the cook on what was ordered + ETA. */
  briefCook?: (params: { items: string[]; etaWindow?: string }) => void;
}

/**
 * Runs the full pre-check pipeline. Idempotent: re-running for the same
 * dish skips items already on the wishlist.
 */
export function runIngredientPrecheck(
  chosen: MealSuggestion,
  mealLabel: string,
  deps: PrecheckDeps,
): PrecheckResult {
  const ingredients = chosen.ingredients || [];
  if (ingredients.length === 0) {
    return {
      missing: [],
      alreadyOnList: [],
      estimatedTotal: 0,
      autoApproved: false,
      summary: `No ingredient list for ${chosen.dishName} — skipping pre-check.`,
    };
  }

  const missing: string[] = [];
  const alreadyOnList: string[] = [];
  for (const ing of ingredients) {
    if (inventoryHas(deps.inventory, ing)) continue;
    if (wishlistHas(deps.wishlist, ing)) {
      alreadyOnList.push(ing);
      continue;
    }
    missing.push(ing);
  }

  const estimatedTotal = missing.length * DEFAULT_PRICE_PER_ITEM;

  // Add each missing ingredient to the wishlist with the right source.
  for (const item of missing) {
    deps.addWishlistItem({
      id: `wi-precheck-${Date.now()}-${item}`,
      name: item,
      quantity: 1,
      unit: "pack",
      estimatedPrice: DEFAULT_PRICE_PER_ITEM,
      source: "ingredient_check",
      addedBy: "Bimi",
      addedAt: new Date().toISOString(),
      priority: "normal",
      status: "pending",
      notes: `For ${mealLabel}: ${chosen.dishName}`,
    });
  }

  // Auto-approval evaluation
  const { matched, reason } = evaluateAutoApproval(missing, estimatedTotal, deps.rules);
  const autoApproved = !!matched;

  if (missing.length > 0) {
    if (autoApproved) {
      deps.notify({
        type: "order_auto_approved",
        title: "Ingredients ordered",
        body: `${missing.length} item${missing.length === 1 ? "" : "s"} for ${chosen.dishName} (₹${estimatedTotal}, ${reason}).`,
        actionRoute: "/(tabs)/approvals",
      });
      deps.briefCook?.({
        items: missing,
        etaWindow: "subah 7 baje tak",
      });
    } else {
      deps.notify({
        type: "order_pending",
        title: "Approve ingredients?",
        body: `${missing.length} item${missing.length === 1 ? "" : "s"} for ${chosen.dishName} need approval (₹${estimatedTotal}).`,
        actionRoute: "/(tabs)/approvals",
      });
    }
  }

  return {
    missing,
    alreadyOnList,
    estimatedTotal,
    autoApproved,
    matchedRule: matched,
    summary:
      missing.length === 0
        ? `All ingredients for ${chosen.dishName} already in your kitchen.`
        : `${missing.length} ingredients needed for ${chosen.dishName} — ${autoApproved ? "auto-approved" : "awaiting approval"} (₹${estimatedTotal}).`,
  };
}
