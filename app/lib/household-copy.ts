import type { HouseholdType } from "./types";

type CopyKey =
  | "appTitle"
  | "votePrompt"
  | "voteDeadline"
  | "mealFinalized"
  | "orderApproved"
  | "orderPending"
  | "fairnessLabel"
  | "tomorrowPlan"
  | "tiebreaker"
  | "expenseLabel"
  | "settlementPrompt"
  | "cookSection"
  | "noCookMessage"
  | "addMemberPrompt"
  | "leavePrompt"
  | "proxyVoteLabel"
  | "prepReminder"
  | "wishlistTitle"
  | "morningReadiness";

const COPY: Record<HouseholdType, Record<CopyKey, string>> = {
  self_use: {
    appTitle: "Your Kitchen",
    votePrompt: "What are you in the mood for?",
    voteDeadline: "Decide by {time} for tomorrow",
    mealFinalized: "{dish} is set for tomorrow!",
    orderApproved: "Order placed — ₹{amount}",
    orderPending: "New order ready to place",
    fairnessLabel: "Your preferences",
    tomorrowPlan: "Tomorrow's plan",
    tiebreaker: "",
    expenseLabel: "This month's groceries",
    settlementPrompt: "",
    cookSection: "Your cook",
    noCookMessage: "Self-cooking mode — Bimi suggests, you cook!",
    addMemberPrompt: "",
    leavePrompt: "",
    proxyVoteLabel: "",
    prepReminder: "Prep tonight: {instruction}",
    wishlistTitle: "Shopping list",
    morningReadiness: "All set for {dish}!",
  },
  couple: {
    appTitle: "{name}'s Kitchen",
    votePrompt: "Decide together what to eat",
    voteDeadline: "Both vote by {time}",
    mealFinalized: "You both agreed on {dish}!",
    orderApproved: "{approver} approved — ₹{amount}",
    orderPending: "New order from cook — review together",
    fairnessLabel: "Meal balance",
    tomorrowPlan: "Tomorrow's plan",
    tiebreaker: "You disagree! Bimi suggests {dish} — it's {name}'s turn (fairness: {score}%)",
    expenseLabel: "Household spend",
    settlementPrompt: "",
    cookSection: "Your cook",
    noCookMessage: "Cooking together — Bimi suggests, you decide!",
    addMemberPrompt: "Invite your partner",
    leavePrompt: "Leave this household? Your partner will keep the cook and history.",
    proxyVoteLabel: "{name} is busy — Bimi predicts: {dish}",
    prepReminder: "Prep tonight: {instruction}",
    wishlistTitle: "Wishlist",
    morningReadiness: "All set for {dish}! Cook arrives at {time}.",
  },
  flatmates: {
    appTitle: "{name}",
    votePrompt: "Pick what everyone eats tomorrow",
    voteDeadline: "{voted}/{total} voted · closes at {time}",
    mealFinalized: "Majority picked {dish}!",
    orderApproved: "{approver} approved — your share: ₹{share}",
    orderPending: "New order — ₹{amount}. Tap to approve.",
    fairnessLabel: "Fairness across flatmates",
    tomorrowPlan: "Tomorrow's plan",
    tiebreaker: "Tie! Bimi picks {dish} — fairness-weighted for {name}",
    expenseLabel: "This month",
    settlementPrompt: "{from} owes {to}: ₹{amount}",
    cookSection: "House cook",
    noCookMessage: "Self-cooking mode — who's cooking tonight?",
    addMemberPrompt: "Invite a new flatmate",
    leavePrompt: "Leave {household}? Settle ₹{amount} first?",
    proxyVoteLabel: "{name} is busy — Bimi predicts: {dish} ({confidence}%)",
    prepReminder: "Prep tonight: {instruction}",
    wishlistTitle: "Wishlist ({count})",
    morningReadiness: "All set for {dish}! Cook arrives at {time}.",
  },
  pg_hostel: {
    appTitle: "My Food",
    votePrompt: "Rate today's mess food",
    voteDeadline: "",
    mealFinalized: "Ordering {dish} to supplement today",
    orderApproved: "Order placed — ₹{amount}",
    orderPending: "Order ready to place",
    fairnessLabel: "Your taste profile",
    tomorrowPlan: "Tomorrow's mess menu",
    tiebreaker: "",
    expenseLabel: "Extra food spend",
    settlementPrompt: "",
    cookSection: "Mess",
    noCookMessage: "No mess today — order something?",
    addMemberPrompt: "",
    leavePrompt: "",
    proxyVoteLabel: "",
    prepReminder: "",
    wishlistTitle: "Order list",
    morningReadiness: "",
  },
  nuclear_family: {
    appTitle: "{name}",
    votePrompt: "Family voting is open",
    voteDeadline: "Vote by {time} — parents finalize",
    mealFinalized: "{dish} is set for tomorrow",
    orderApproved: "Order approved by {approver}",
    orderPending: "Cook needs supplies — ₹{amount}",
    fairnessLabel: "Fairness this week",
    tomorrowPlan: "Tomorrow's plan",
    tiebreaker: "Parents to decide: {dish1} or {dish2}",
    expenseLabel: "Monthly groceries",
    settlementPrompt: "",
    cookSection: "Our cook",
    noCookMessage: "No cook today — order or self-cook?",
    addMemberPrompt: "Add family member",
    leavePrompt: "Leave this family household?",
    proxyVoteLabel: "{name} hasn't voted — Bimi suggests they'd like {dish}",
    prepReminder: "Cook: {instruction} tonight",
    wishlistTitle: "Shopping list",
    morningReadiness: "Kitchen ready for {dish}! Cook arrives at {time}.",
  },
  joint_family: {
    appTitle: "{name}",
    votePrompt: "Family meal selection",
    voteDeadline: "Suggestions close at {time}",
    mealFinalized: "Tomorrow: Veg — {vegDish}, Non-veg — {nonVegDish}",
    orderApproved: "Order approved by {approver}",
    orderPending: "Kitchen supplies needed — ₹{amount}",
    fairnessLabel: "Fairness across family",
    tomorrowPlan: "Tomorrow's plates",
    tiebreaker: "Elders' preferences weighted — {dish} selected",
    expenseLabel: "Monthly kitchen budget",
    settlementPrompt: "",
    cookSection: "Kitchen staff",
    noCookMessage: "Cook is off — arrange replacement?",
    addMemberPrompt: "Add family member",
    leavePrompt: "Leave the family household?",
    proxyVoteLabel: "{name} hasn't voted — predicted: {dish}",
    prepReminder: "Tonight's prep: {instruction}",
    wishlistTitle: "Kitchen needs",
    morningReadiness: "Both kitchens ready! Main: {vegDish}, Non-veg: {nonVegDish}.",
  },
  single_parent: {
    appTitle: "{name}'s Kitchen",
    votePrompt: "Bimi suggests for tomorrow",
    voteDeadline: "Auto-finalizing at {time}",
    mealFinalized: "{dish} is set — cook will be notified",
    orderApproved: "Auto-ordered — ₹{amount}",
    orderPending: "Supplies needed — auto-approve?",
    fairnessLabel: "Kids' variety",
    tomorrowPlan: "Tomorrow's plan",
    tiebreaker: "",
    expenseLabel: "Monthly groceries",
    settlementPrompt: "",
    cookSection: "Your cook",
    noCookMessage: "No cook today — quick meal suggestions ready",
    addMemberPrompt: "Add your child",
    leavePrompt: "",
    proxyVoteLabel: "Auto-selected: {dish} (kid-friendly, quick)",
    prepReminder: "Cook: {instruction}",
    wishlistTitle: "Shopping list",
    morningReadiness: "All set for {dish}! Cook at {time}.",
  },
};

export function getHouseholdCopy(
  type: HouseholdType,
  key: CopyKey,
  params?: Record<string, string | number>
): string {
  let text = COPY[type]?.[key] || COPY.nuclear_family[key] || "";
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      text = text.replace(new RegExp(`\\{${k}\\}`, "g"), String(v));
    }
  }
  return text;
}

export function getHouseholdTypeLabel(type: HouseholdType): string {
  const labels: Record<HouseholdType, string> = {
    self_use: "Solo",
    couple: "Couple",
    flatmates: "Flatmates",
    pg_hostel: "PG / Hostel",
    nuclear_family: "Family",
    joint_family: "Joint Family",
    single_parent: "Single Parent",
  };
  return labels[type] || type;
}

export function getHouseholdTypeIcon(type: HouseholdType): string {
  const icons: Record<HouseholdType, string> = {
    self_use: "🧑",
    couple: "💑",
    flatmates: "🏠",
    pg_hostel: "🏢",
    nuclear_family: "👨‍👩‍👧‍👦",
    joint_family: "👨‍👩‍👧‍👦",
    single_parent: "👩‍👧",
  };
  return icons[type] || "🏠";
}

export function getRoleLabel(role: string): string {
  const labels: Record<string, string> = {
    partner: "Partner",
    flatmate: "Flatmate",
    parent: "Parent",
    child: "Child",
    member: "Member",
  };
  return labels[role] || role;
}

export function getDefaultRolesForType(type: HouseholdType): { value: string; label: string }[] {
  switch (type) {
    case "couple": return [{ value: "partner", label: "Partner" }];
    case "flatmates": return [{ value: "flatmate", label: "Flatmate" }];
    case "nuclear_family":
    case "joint_family": return [
      { value: "parent", label: "Parent" },
      { value: "child", label: "Child" },
      { value: "member", label: "Other Member" },
    ];
    case "single_parent": return [
      { value: "parent", label: "Parent" },
      { value: "child", label: "Child" },
    ];
    default: return [{ value: "member", label: "Member" }];
  }
}
