/**
 * Time-of-day utilities — gives the home greeting (and any contextual surface)
 * a sense of being _alive_ to the moment instead of a timeless "Hey Anjan".
 *
 * The 4 bands map to:
 *
 *   morning  (5–10) → "Good morning"  → warm orange
 *   midday  (11–16) → "Hey"            → orange-coral
 *   evening (17–20) → "Good evening"   → coral
 *   night   (21–4)  → "Up late?"       → cool violet
 *
 * Uses the same band ranges as `getTimeOfDayColor()` in `theme.ts` so the
 * brand-mark ambient glow and the greeting agree.
 */

export type TimeOfDayBand = "morning" | "midday" | "evening" | "night";

export function getTimeOfDayBand(now: Date = new Date()): TimeOfDayBand {
  const h = now.getHours();
  if (h >= 5 && h < 11) return "morning";
  if (h >= 11 && h < 17) return "midday";
  if (h >= 17 && h < 21) return "evening";
  return "night";
}

const GREETINGS: Record<TimeOfDayBand, (name: string) => string> = {
  morning: (n) => `Good morning, ${n}`,
  midday:  (n) => `Hey ${n}`,
  evening: (n) => `Good evening, ${n}`,
  // Night should still feel friendly and not chiding — same playful Hinglish-light tone.
  night:   (n) => `Up late, ${n}?`,
};

export function getGreetingFor(name: string, now?: Date): string {
  return GREETINGS[getTimeOfDayBand(now)](name);
}

/**
 * Time-of-day glow — formerly drove a colored shadow behind the brand mark
 * on the dark theme. The light theme uses photography and whitespace for
 * atmosphere instead; this returns transparent so callers can keep the
 * import without producing a visible effect. Remove call sites during the
 * screen sweep.
 */
export function getTimeOfDayGlow(_now?: Date): string {
  return "transparent";
}
