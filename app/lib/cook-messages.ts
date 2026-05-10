/**
 * P3 (PRD 4.8): Templated outbound cook messages.
 *
 * The PRD defines 5 outbound message types Bimi sends to the cook on
 * WhatsApp, in Hindi or Hinglish. We render them through `shareWithCook`
 * (deep links to WhatsApp) AND mirror them as non-cook bubbles in
 * `useChatStore` so the user sees what was sent.
 */

import { useChatStore } from "./store";
import { shareWithCook } from "./whatsapp-share";

export interface MealBriefingArgs {
  cookName?: string;
  cookPhone?: string;
  mealType: "breakfast" | "lunch" | "dinner" | "snack";
  dishName: string;
  prepNote?: string;
  ingredientsReady?: boolean;
}

function timeOfDay(mealType: string): string {
  if (mealType === "breakfast") return "subah ka breakfast";
  if (mealType === "lunch") return "kal ka lunch";
  if (mealType === "dinner") return "kal ka dinner";
  return "agle meal";
}

function mirrorToChat(content: string) {
  try {
    useChatStore.getState().addMessage({
      id: `out-${Date.now()}`,
      type: "text",
      content,
      timestamp: new Date().toISOString(),
      isFromCook: false,
      actionItems: [],
    } as any);
  } catch {
    /* chat store may not be ready in tests */
  }
}

/** PRD outbound type 1: Meal finalized → cook briefing with prep note. */
export function sendMealFinalizedToCook(args: MealBriefingArgs) {
  const prep = args.prepNote ? ` ${args.prepNote}.` : "";
  const ready = args.ingredientsReady ? " Ingredients ready hain." : "";
  const msg = `${timeOfDay(args.mealType).charAt(0).toUpperCase() + timeOfDay(args.mealType).slice(1)}: ${args.dishName}.${prep}${ready}`;
  shareWithCook(args.cookPhone, msg);
  mirrorToChat(msg);
}

/** PRD outbound type 2: Morning readiness check at cook arrival time. */
export function sendMorningReadinessToCook(args: { cookName?: string; cookPhone?: string; dishName: string; arrivalTime?: string }) {
  const t = args.arrivalTime ? ` ${args.arrivalTime} se start.` : "";
  const msg = `Good morning! Sab ready hai. ${args.dishName} banana hai —${t}`;
  shareWithCook(args.cookPhone, msg);
  mirrorToChat(msg);
}

/** PRD outbound type 3: Ingredient ordered (with delivery ETA window). */
export function sendIngredientsOrderedToCook(args: {
  cookPhone?: string;
  items: string[];
  etaWindow?: string; // e.g. "subah 7 baje tak"
}) {
  const eta = args.etaWindow || "subah 7 baje tak";
  const items = args.items.join(", ");
  const msg = `${items} order ho gaya, ${eta} aa jayega.`;
  shareWithCook(args.cookPhone, msg);
  mirrorToChat(msg);
}

/** PRD outbound type 4: Order delivered confirmation. */
export function sendOrderDeliveredToCook(args: { cookPhone?: string; items: string[] }) {
  const list = args.items.join(", ");
  const msg = `Saamaan aa gaya! ${list}`;
  shareWithCook(args.cookPhone, msg);
  mirrorToChat(msg);
}

/** PRD outbound type 5: Absence acknowledged (cook said "kal nahi aaungi"). */
export function sendAbsenceAckToCook(args: { cookPhone?: string; cookName?: string }) {
  const msg = `Theek hai${args.cookName ? ` ${args.cookName}` : ""}, chutti note kar li. Take care!`;
  shareWithCook(args.cookPhone, msg);
  mirrorToChat(msg);
}
