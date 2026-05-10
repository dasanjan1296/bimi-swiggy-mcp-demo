// H6: per-screen empty-state copy. Hinglish where the elder persona reads.
// Imported by every screen alongside the EmptyState component so the copy
// stays consistent + auditable.

export const EMPTY_COPY = {
  home_no_plan: {
    emoji: "🍳",
    title: "Aaj ka plan banao",
    message: "Voting kholiye -- 30 second mein kal ka khana plan ho jayega.",
    actionLabel: "Vote shuru karein",
  },
  voting_no_options: {
    emoji: "🗳️",
    title: "Loading suggestions",
    message: "Bimi aapke ghar ke liye options taiyaar kar rahi hai. 5 second...",
  },
  voting_paused: {
    emoji: "⏸️",
    title: "Suggestions paused",
    message: "Pilot lead ne aapke ghar ke liye suggestions ko pause kar diya hai. Hum jaldi hi resume karenge.",
    variant: "paused" as const,
  },
  approvals_empty: {
    emoji: "✅",
    title: "Sab cleared",
    message: "Koi pending cart nahi hai. Bimi naya cart banayegi to yahan dikhayi dega.",
  },
  cook_no_messages: {
    emoji: "💬",
    title: "Cook se baat shuru karein",
    message: "Type karein -- Hindi ya English -- aur Bimi cook ko WhatsApp pe bhej degi.",
    actionLabel: "Pehla message bhejein",
  },
  expenses_no_data: {
    emoji: "💸",
    title: "Is mahine kuch nahi",
    message: "Jab cart approve karenge, expenses yahan track ho jayega.",
  },
  health_no_metrics: {
    emoji: "🩺",
    title: "Pehla reading log karein",
    message: "A1c / BP / wajan likh dijiye -- Bimi 2 hafte mein patterns bata degi.",
    actionLabel: "Reading add karein",
  },
  insights_cold_start: {
    emoji: "📊",
    title: "Patterns thodi der mein",
    message: "Ek hafta data jama ho jaye, fir Bimi insights dikhayegi. Abhi sirf 3 din ka data hai.",
  },
  recap_pending: {
    emoji: "📨",
    title: "Sunday tak ruk jaiye",
    message: "Har Sunday subah Bimi ek recap bhej degi -- 'is hafte humne kya seekha' ke saath.",
  },
  prep_timeline_no_dish: {
    emoji: "🕐",
    title: "Pehle dish select karein",
    message: "Ek baar kal ka khana finalize ho jaye, prep timeline yahan dikh jayegi.",
  },
  meal_calendar_empty: {
    emoji: "📅",
    title: "Calendar khali hai",
    message: "Aage ke 7 din ka khana plan karne ke liye Voting screen kholiye.",
    actionLabel: "Voting kholiye",
  },
  notifications_empty: {
    emoji: "🔔",
    title: "Sab shaant",
    message: "Naya alert aane par yahan dikh jayega.",
  },
} as const;

export type EmptyCopyKey = keyof typeof EMPTY_COPY;
