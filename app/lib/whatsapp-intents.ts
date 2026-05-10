/**
 * WhatsApp intent map — the source of truth for the eighth design
 * principle ("WhatsApp is a first-class surface, not a fallback").
 *
 * Every household-member action that exists in the app MUST also be
 * expressible as a WhatsApp message Bimi can parse. The mapping lives
 * here so:
 *
 *   - Future agents adding a feature can check whether the WhatsApp
 *     expression is missing — if it is, the feature isn't done.
 *   - The backend NLU pipeline (Sarvam/OpenAI) has a single canonical
 *     list of intents to extract from inbound messages.
 *   - Documentation (`design-system.md` §11, `UX-REDESIGN-*.md` §11b)
 *     can link to this file as the authoritative list.
 *
 * Status: skeleton. The actual NLU + dispatch wiring lives on the
 * backend. This file is the contract — additions here imply work on
 * the backend WhatsApp webhook handler.
 */

import type { ActionItem, MealType } from "./types";

/** Inbound WhatsApp intent. The backend NLU produces one of these. */
export type InboundIntent =
  // ── Member: dietary / meal decisions ──────────────────────────────
  | { kind: "vote_meal"; date: string; mealType: MealType; dishHint: string }
  | { kind: "vote_emoji_react"; pollId: string; emoji: string }
  | { kind: "decide_dinner_now"; dishName: string }
  | { kind: "skip_meal"; date: string; mealType: MealType }
  | { kind: "out_for_meal"; date: string; mealType: MealType }
  // ── Member: groceries ─────────────────────────────────────────────
  | { kind: "add_to_grocery"; items: { name: string; quantity?: string }[]; needBy?: string }
  | { kind: "ran_out"; itemName: string }
  // ── Member: rating ────────────────────────────────────────────────
  | { kind: "rate_meal"; date: string; mealType: MealType; rating: 1 | 2 | 3 | 4 | 5 }
  // ── Member: cook coordination ─────────────────────────────────────
  | { kind: "give_cook_off"; date: string }
  | { kind: "ack_cook_action"; messageId: string; actionIdx: number }
  // ── Cook: status reports ──────────────────────────────────────────
  | { kind: "cook_low_stock"; itemName: string; severity: "low" | "out" }
  | { kind: "cook_absence"; date: string; reason?: string }
  | { kind: "cook_running_late"; minutes: number }
  | { kind: "cook_meal_query"; question: string }
  | { kind: "cook_prep_failed"; reason: string }
  // ── Member or cook: free-text fallback ────────────────────────────
  | { kind: "unknown"; text: string };

/**
 * Outbound WhatsApp message types Bimi sends. Mirrors what's already
 * documented in PRD §4.8 ("5 PRD outbound message types") but extends
 * them to cover the new intents.
 */
export type OutboundMessage =
  // To the kitchen lead / household group
  | { kind: "dinner_poll"; pollId: string; dishes: { dishName: string; emoji: string }[] }
  | { kind: "grocery_added_confirmation"; items: string[]; total: number }
  | { kind: "auto_approval_notice"; orderId: string; total: number; items: string[] }
  | { kind: "absence_decision_required"; date: string; cookName: string }
  | { kind: "daily_digest"; today: string; tomorrow?: string; ordered?: string }
  // To the cook (in Hindi)
  | { kind: "cook_brief"; date: string; mealType: MealType; dishName: string; portions: number; advancePrep?: string }
  | { kind: "cook_absence_ack"; date: string }
  | { kind: "cook_meal_change"; date: string; mealType: MealType; oldDish: string; newDish: string };

/**
 * Shape of a parsed inbound message. The backend handler turns
 * incoming WhatsApp content (text / voice transcribed via Sarvam /
 * image OCR) into this shape, then routes to the right Zustand
 * action.
 */
export interface ParsedInbound {
  intent: InboundIntent;
  /** WhatsApp phone number that sent the message. */
  fromPhone: string;
  /** Resolved member id, if the phone matches a household member. */
  memberId?: string;
  /** "cook" if the phone matches a cook on file. */
  isFromCook: boolean;
  /** Original message text for audit / fallback display. */
  rawText: string;
  /** When the message landed. */
  receivedAt: string;
}

/**
 * Stable mapping of intent kind → app action. Used by the backend's
 * webhook handler and by future test fixtures. Keep this exhaustive —
 * the type system enforces that every InboundIntent variant has a
 * documented dispatch target.
 */
export const INTENT_DISPATCH: Record<InboundIntent["kind"], string> = {
  vote_meal: "useMealStore.submitVote",
  vote_emoji_react: "useMealStore.submitVote (resolved via pollId)",
  decide_dinner_now: "useMealStore.finalizePlan",
  skip_meal: "useMealStore.skipMeal",
  out_for_meal: "useMealStore.markAbsent",
  add_to_grocery: "useWishlistStore.addItem (×N)",
  ran_out: "useInventoryStore.markDepleted + useWishlistStore.addItem",
  rate_meal: "useMealStore.rateMeal",
  give_cook_off: "useCookAbsenceStore.addAbsence",
  ack_cook_action: "useChatStore.resolveAction",
  cook_low_stock: "useInventoryStore.markLowStock + useChatStore.addMessage",
  cook_absence: "useCookAbsenceStore.addAbsence",
  cook_running_late: "useChatStore.addMessage (delay)",
  cook_meal_query: "useChatStore.addMessage (action: meal_query)",
  cook_prep_failed: "useChatStore.addMessage (action: prep_failed)",
  unknown: "useChatStore.addMessage (verbatim, surfaces to lead for triage)",
};

/**
 * Maps cook ActionItem types to the WhatsApp prompt the cook sees
 * when Bimi's the one initiating. Used by the cook-side surface
 * generator and any backend test fixture.
 */
export const COOK_PROMPT_FOR_ACTION: Record<ActionItem["type"], string> = {
  supply_request: "Kya order karu? Reply with item names ya 'ok' agar standard list theek hai.",
  meal_query: "Aaj kya banaye? Reply with dish name.",
  low_stock: "Kya kam ho gaya? Item name bata do.",
  absence: "Kal aana hai ya nahi? Reply 'aaungi' / 'nahi aaungi'.",
  prep_note: "Note saved. No reply needed.",
  prep_failed: "Backup banayein? Reply yes / no — Bimi alternative bata degi.",
};

/**
 * Sanity check used by tests: every InboundIntent variant has an
 * INTENT_DISPATCH entry, and every ActionItem type has a cook prompt.
 * The TS exhaustive-record pattern enforces this at compile time.
 */
export const __TYPECHECK = (): boolean => {
  // Compile-time only — the Record<...> type signatures above already
  // enforce exhaustiveness. This is just documentation.
  return Object.keys(INTENT_DISPATCH).length > 0;
};
