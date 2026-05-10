import type { Cook, CookSlot, MealType } from "./types";

/**
 * P3 (PRD 4.11): Prep-aware voting deadlines.
 *
 * Rules:
 * - Tomorrow's BREAKFAST and LUNCH need overnight prep instructions to
 *   reach the cook during their evening visit TODAY → deadline is the
 *   evening-slot arrival_time minus a 60-min briefing buffer.
 * - Tomorrow's DINNER can be briefed during the morning visit tomorrow,
 *   so the deadline is the morning-slot arrival_time minus 60 min
 *   (effectively last night's 9-10 PM cutoff with default morning slot
 *   of 8 AM).
 * - Households with no `cook.slots` fall back to a fixed clock time from
 *   `config.votingDeadlineHour`.
 */

const BRIEFING_BUFFER_MIN = 60;

function findSlot(cook: Cook | undefined, type: CookSlot["type"]): CookSlot | undefined {
  return cook?.slots?.find((s) => s.type === type);
}

function setHHmm(date: Date, hhmm: string): Date {
  const [h, m] = hhmm.split(":").map((n) => parseInt(n, 10));
  const out = new Date(date);
  out.setHours(h || 0, m || 0, 0, 0);
  return out;
}

function todayLocal(): Date {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d;
}

function tomorrowLocal(): Date {
  const d = todayLocal();
  d.setDate(d.getDate() + 1);
  return d;
}

function tomorrowAtHour(hour: number): Date {
  const d = tomorrowLocal();
  d.setHours(hour - 1, 0, 0, 0); // hour BEFORE tomorrow's plan, e.g. 19→18:00
  return d;
}

export interface ComputedDeadline {
  /** Absolute deadline as a Date — null if no slot available. */
  date: Date | null;
  /** Source: "evening-slot" / "morning-slot" / "config-fallback". */
  source: "evening-slot" | "morning-slot" | "config-fallback";
  /** Human-readable explanation for tooltips. */
  rationale: string;
}

export function computeDeadline(
  mealType: MealType,
  cook: Cook | undefined,
  fallbackHour: number = 20,
): ComputedDeadline {
  // Tomorrow's breakfast & lunch — prep happens during today's evening slot
  if (mealType === "breakfast" || mealType === "lunch") {
    const eveningSlot = findSlot(cook, "evening");
    if (eveningSlot?.arrivalTime) {
      const today = todayLocal();
      const dl = new Date(setHHmm(today, eveningSlot.arrivalTime).getTime() - BRIEFING_BUFFER_MIN * 60 * 1000);
      return {
        date: dl,
        source: "evening-slot",
        rationale: `${cook?.name || "Your cook"} arrives at ${eveningSlot.arrivalTime} for the evening shift — overnight prep brief must reach them by then.`,
      };
    }
    // No evening slot — fall back to morning slot of TOMORROW (less ideal)
    const morningSlot = findSlot(cook, "morning");
    if (morningSlot?.arrivalTime) {
      const tomorrow = tomorrowLocal();
      const dl = new Date(setHHmm(tomorrow, morningSlot.arrivalTime).getTime() - BRIEFING_BUFFER_MIN * 60 * 1000);
      return {
        date: dl,
        source: "morning-slot",
        rationale: `Brief reaches ${cook?.name || "the cook"} ${BRIEFING_BUFFER_MIN} min before their ${morningSlot.arrivalTime} arrival.`,
      };
    }
  }

  // Tomorrow's dinner — brief tomorrow morning
  if (mealType === "dinner") {
    const morningSlot = findSlot(cook, "morning");
    if (morningSlot?.arrivalTime) {
      const tomorrow = tomorrowLocal();
      const dl = new Date(setHHmm(tomorrow, morningSlot.arrivalTime).getTime() - BRIEFING_BUFFER_MIN * 60 * 1000);
      return {
        date: dl,
        source: "morning-slot",
        rationale: `${cook?.name || "Your cook"} gets the dinner plan during their morning visit (${morningSlot.arrivalTime}).`,
      };
    }
  }

  // No structured cook slots — fall back to fixed hour TODAY
  const today = todayLocal();
  today.setHours(fallbackHour, 0, 0, 0);
  // If that's already past, push to tomorrow at the same hour
  const final = today.getTime() > Date.now() ? today : tomorrowAtHour(fallbackHour + 1);
  return {
    date: final,
    source: "config-fallback",
    rationale: "No cook schedule set — using household default voting cutoff.",
  };
}

export function formatRemaining(deadline: Date | null): {
  label: string;
  expired: boolean;
  urgent: boolean;
} {
  if (!deadline) return { label: "—", expired: false, urgent: false };
  const ms = deadline.getTime() - Date.now();
  if (ms <= 0) return { label: "Closed", expired: true, urgent: false };
  const totalMin = Math.floor(ms / 60000);
  const h = Math.floor(totalMin / 60);
  const m = totalMin % 60;
  let label: string;
  if (h >= 24) {
    const days = Math.floor(h / 24);
    label = `${days}d ${h % 24}h left`;
  } else if (h >= 1) {
    label = `${h}h ${m}m left`;
  } else {
    label = `${m}m left`;
  }
  return { label, expired: false, urgent: totalMin <= 30 };
}
