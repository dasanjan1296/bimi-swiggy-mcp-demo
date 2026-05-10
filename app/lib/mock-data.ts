import type {
  Household,
  MealPlan,
  MealSuggestion,
  Order,
  AutoApprovalRule,
  InventoryItem,
  CookMessage,
  FairnessScore,
  WishlistItem,
  MonthlyExpenseSummary,
  HouseholdType,
} from "./types";
import { HOUSEHOLD_DEFAULTS } from "./types";
import { localIsoDate, localIsoDatePlus } from "./local-day";

// ─── Bachelor Pad ───

export const BACHELOR_HOUSEHOLD: Household = {
  id: "flat-114",
  type: "flatmates",
  name: "Flat 114, Tower 6, SPP",
  hasCook: true,
  hasRegularCook: true,
  config: { ...HOUSEHOLD_DEFAULTS.flatmates },
  inviteCode: "A7F2C1",
  inviteCodeExpiresAt: new Date(Date.now() + 5 * 86400000).toISOString(),
  members: [
    { id: "v-001", name: "Anjan", role: "flatmate", avatar: "👨‍💻", isPayingMember: true, isAdmin: true, isActive: true, isAvailable: true, joinedAt: "2025-12-01", dietaryPreferences: [], healthConditions: [] },
    { id: "v-002", name: "Mayank", role: "flatmate", avatar: "🧔", isPayingMember: true, isAdmin: false, isActive: true, isAvailable: true, joinedAt: "2026-01-15", dietaryPreferences: [], healthConditions: [] },
    { id: "v-003", name: "Garvika", role: "flatmate", avatar: "👩", isPayingMember: true, isAdmin: false, isActive: true, isAvailable: true, joinedAt: "2026-03-01", dietaryPreferences: [{ item: "Mushroom", type: "avoidance", safetyClass: "preference" }], healthConditions: [] },
  ],
  cooks: [{ id: "c-flat", name: "Malti Didi", whatsappNumber: "+919876543210", schedule: "Mon-Sat, 7PM-8PM", repertoire: ["Dal Tadka", "Rajma", "Chole", "Aloo Gobi", "Paneer Butter Masala", "Jeera Rice", "Roti", "Poha", "Egg Curry", "Kadhi", "Bhindi Masala", "Palak Paneer", "Mix Veg", "Pulao", "Paratha"], payDay: 1, salary: 5000, slots: [{ type: "evening", arrivalTime: "19:00", departureTime: "20:00", workingDays: ["Mon","Tue","Wed","Thu","Fri","Sat"] }], monthlyLeaves: 4, dietaryRestrictions: [], brandPreferences: { "Atta": "Aashirvaad", "Oil": "Fortune", "Dal": "Toor dal" } }],
};

// ─── Couple ───

export const COUPLE_HOUSEHOLD: Household = {
  id: "arun-sneha",
  type: "couple",
  name: "Arun & Sneha's Kitchen",
  hasCook: true,
  hasRegularCook: true,
  config: { ...HOUSEHOLD_DEFAULTS.couple },
  members: [
    { id: "c-001", name: "Arun", role: "partner", avatar: "👨", isPayingMember: true, isAdmin: true, isActive: true, isAvailable: true, joinedAt: "2025-11-01", dietaryPreferences: [], healthConditions: [] },
    { id: "c-002", name: "Sneha", role: "partner", avatar: "👩", isPayingMember: true, isAdmin: false, isActive: true, isAvailable: true, joinedAt: "2025-11-01", dietaryPreferences: [{ item: "Meat", type: "avoidance", safetyClass: "preference", notes: "Vegetarian" }], healthConditions: [] },
  ],
  cooks: [{ id: "c-couple", name: "Sunita Didi", whatsappNumber: "+919876543211", schedule: "Mon-Fri, 8AM-9AM", repertoire: ["Paneer Butter Masala", "Dal Tadka", "Chole Bhature", "Aloo Paratha", "Poha", "Idli", "Roti", "Rajma Chawal", "Pulao", "Khichdi"], payDay: 5, salary: 6000, slots: [{ type: "morning", arrivalTime: "08:00", departureTime: "09:00", workingDays: ["Mon","Tue","Wed","Thu","Fri"] }], monthlyLeaves: 4, dietaryRestrictions: [], brandPreferences: { "Atta": "Aashirvaad", "Oil": "Fortune", "Dal": "Toor dal" } }],
};

// ─── Nuclear Family ───

export const FAMILY_HOUSEHOLD: Household = {
  id: "sharma-family",
  type: "nuclear_family",
  name: "The Sharma Family",
  hasCook: true,
  hasRegularCook: true,
  config: { ...HOUSEHOLD_DEFAULTS.nuclear_family },
  members: [
    { id: "f-001", name: "Rahul", role: "parent", avatar: "👨", isPayingMember: true, isAdmin: true, isActive: true, isAvailable: true, joinedAt: "2025-10-01", dietaryPreferences: [], healthConditions: ["cholesterol"] },
    { id: "f-002", name: "Priya", role: "parent", avatar: "👩", isPayingMember: true, isAdmin: false, isActive: true, isAvailable: true, joinedAt: "2025-10-01", dietaryPreferences: [{ item: "Mushroom", type: "avoidance", safetyClass: "preference" }], healthConditions: [] },
    { id: "f-003", name: "Arjun", role: "child", avatar: "👦", isPayingMember: false, isAdmin: false, isActive: true, isAvailable: true, joinedAt: "2025-10-01", dietaryPreferences: [], healthConditions: [] },
    { id: "f-004", name: "Ananya", role: "child", avatar: "👧", isPayingMember: false, isAdmin: false, isActive: true, isAvailable: true, joinedAt: "2025-10-01", dietaryPreferences: [{ item: "Peanuts", type: "allergy", safetyClass: "critical", notes: "Severe allergic reaction" }], healthConditions: [] },
  ],
  cooks: [{ id: "c-fam", name: "Geeta Didi", whatsappNumber: "+919876543212", schedule: "Mon-Sat, 8AM-9AM", repertoire: ["Dal Tadka", "Rajma", "Chole", "Aloo Gobi", "Paneer Butter Masala", "Jeera Rice", "Roti", "Paratha", "Poha", "Upma", "Dosa", "Idli", "Pulao", "Kadhi", "Bhindi Masala", "Palak Paneer", "Mix Veg", "Egg Curry", "Aloo Paratha", "Methi Thepla"], payDay: 1, salary: 8000, slots: [{ type: "morning", arrivalTime: "08:00", departureTime: "09:00", workingDays: ["Mon","Tue","Wed","Thu","Fri","Sat"] }], monthlyLeaves: 4, dietaryRestrictions: [], brandPreferences: { "Atta": "Aashirvaad", "Oil": "Fortune", "Dal": "Toor dal" } }],
};

export const ALL_HOUSEHOLDS: Household[] = [BACHELOR_HOUSEHOLD, COUPLE_HOUSEHOLD, FAMILY_HOUSEHOLD];

// ─── Meal Suggestions (shared across household types) ───

export const MOCK_MEAL_SUGGESTIONS: Record<string, MealSuggestion[]> = {
  breakfast: [
    { id: "s-b1", dishName: "Aloo Paratha with Curd", confidence: 0.87, fairnessScore: 0.92, noveltyBonus: 0.1, constraints: [], prepTime: "25 min", needsAdvancePrep: false, ingredients: ["Wheat flour", "Potato", "Spices", "Curd", "Butter"], missingIngredients: [] },
    { id: "s-b2", dishName: "Poha with Chai", confidence: 0.79, fairnessScore: 0.88, noveltyBonus: 0.3, constraints: [], prepTime: "15 min", needsAdvancePrep: false, ingredients: ["Poha", "Onion", "Peanuts", "Curry leaves"], missingIngredients: ["Curry leaves"] },
    { id: "s-b3", dishName: "Idli Sambar", confidence: 0.71, fairnessScore: 0.95, noveltyBonus: 0.5, constraints: [{ type: "repertoire", description: "Cook rarely makes South Indian", memberName: "", severity: "info" }], prepTime: "30 min", needsAdvancePrep: true, advancePrepNote: "Soak urad dal overnight", ingredients: ["Rice", "Urad dal", "Toor dal"], missingIngredients: ["Urad dal"] },
  ],
  lunch: [
    { id: "s-l1", dishName: "Chole Bhature", confidence: 0.91, fairnessScore: 0.85, noveltyBonus: 0.2, constraints: [], prepTime: "45 min", needsAdvancePrep: true, advancePrepNote: "Soak chole overnight", ingredients: ["Chickpeas", "Onion", "Tomato", "Spices", "Maida", "Curd"], missingIngredients: [] },
    { id: "s-l2", dishName: "Rajma Chawal", confidence: 0.84, fairnessScore: 0.90, noveltyBonus: 0.15, constraints: [], prepTime: "40 min", needsAdvancePrep: true, advancePrepNote: "Soak rajma overnight", ingredients: ["Rajma", "Rice", "Onion", "Tomato"], missingIngredients: [] },
    { id: "s-l3", dishName: "Paneer Butter Masala", confidence: 0.82, fairnessScore: 0.78, noveltyBonus: 0.05, constraints: [{ type: "health", description: "High fat — cholesterol concern", memberName: "", severity: "warning" }], prepTime: "35 min", needsAdvancePrep: false, ingredients: ["Paneer", "Butter", "Cream", "Tomato", "Rice"], missingIngredients: ["Cream"] },
  ],
  dinner: [
    { id: "s-d1", dishName: "Dal Tadka", confidence: 0.88, fairnessScore: 0.94, noveltyBonus: 0.1, constraints: [], prepTime: "30 min", needsAdvancePrep: false, ingredients: ["Toor dal", "Wheat flour", "Ghee", "Spices"], missingIngredients: [] },
    { id: "s-d2", dishName: "Aloo Gobi", confidence: 0.80, fairnessScore: 0.87, noveltyBonus: 0.25, constraints: [], prepTime: "35 min", needsAdvancePrep: false, ingredients: ["Potato", "Cauliflower", "Wheat flour"], missingIngredients: [] },
    { id: "s-d3", dishName: "Khichdi", confidence: 0.76, fairnessScore: 0.91, noveltyBonus: 0.4, constraints: [], prepTime: "25 min", needsAdvancePrep: false, ingredients: ["Rice", "Moong dal", "Ghee"], missingIngredients: [] },
  ],
};

// ─── Today's/Tomorrow's Plans ───

const TODAY = localIsoDate();

// Demo vote + rating fixtures so today's row in Meals History shows
// realistic per-member attribution + ratings + a couple of proxy
// votes. Without these, the past-day modal would render empty
// "no votes recorded" placeholders for today, which obscures the
// design intent of the surface. Three members: Anjan (admin),
// Mayank, Garvika; one Bimi-proxy vote on breakfast and one on
// dinner so the proxy-attribution UX is exercised.
const TODAY_TIMESTAMP = `${TODAY}T08:00:00.000Z`;

export const MOCK_TODAYS_PLANS: MealPlan[] = [
  {
    id: "mp-today-breakfast",
    date: TODAY,
    mealType: "breakfast",
    selectedMeal: "Poha",
    dishes: ["Poha", "Chai"],
    status: "cooked",
    votes: [
      { memberId: "v-001", memberName: "Anjan", dishId: "s-b1", dishName: "Poha", rating: 5, timestamp: TODAY_TIMESTAMP, isProxy: false },
      { memberId: "v-002", memberName: "Mayank", dishId: "s-b2", dishName: "Idli Sambar", rating: 4, timestamp: TODAY_TIMESTAMP, isProxy: false },
      { memberId: "v-003", memberName: "Garvika", dishId: "s-b1", dishName: "Poha", rating: 4, timestamp: TODAY_TIMESTAMP, isProxy: true, proxyConfidence: 0.78 },
    ],
    suggestions: [],
  },
  {
    id: "mp-today-lunch",
    date: TODAY,
    mealType: "lunch",
    selectedMeal: "Rajma Chawal",
    dishes: ["Rajma", "Steamed Rice", "Raita"],
    status: "cooking",
    votes: [
      { memberId: "v-001", memberName: "Anjan", dishId: "s-l1", dishName: "Rajma Chawal", rating: 5, timestamp: TODAY_TIMESTAMP, isProxy: false },
      { memberId: "v-002", memberName: "Mayank", dishId: "s-l1", dishName: "Rajma Chawal", rating: 4, timestamp: TODAY_TIMESTAMP, isProxy: false },
      { memberId: "v-003", memberName: "Garvika", dishId: "s-l2", dishName: "Chole Bhature", rating: 4, timestamp: TODAY_TIMESTAMP, isProxy: false },
    ],
    suggestions: [],
  },
  {
    id: "mp-today-dinner",
    date: TODAY,
    mealType: "dinner",
    selectedMeal: "Dal Tadka",
    dishes: ["Dal Tadka", "Roti", "Salad"],
    status: "planned",
    votes: [
      { memberId: "v-001", memberName: "Anjan", dishId: "s-d1", dishName: "Dal Tadka", rating: 5, timestamp: TODAY_TIMESTAMP, isProxy: false },
      { memberId: "v-002", memberName: "Mayank", dishId: "s-d1", dishName: "Dal Tadka", rating: 5, timestamp: TODAY_TIMESTAMP, isProxy: true, proxyConfidence: 0.84 },
      { memberId: "v-003", memberName: "Garvika", dishId: "s-d2", dishName: "Aloo Gobi", rating: 4, timestamp: TODAY_TIMESTAMP, isProxy: false },
    ],
    suggestions: [],
  },
];

// Keep single reference for backward compat
export const MOCK_TODAYS_PLAN: MealPlan = MOCK_TODAYS_PLANS[1];

const TOMORROW = localIsoDatePlus(1);

export const MOCK_TOMORROWS_PLANS: MealPlan[] = [
  {
    id: "mp-tmrw-breakfast",
    date: TOMORROW,
    mealType: "breakfast",
    selectedMeal: undefined,
    dishes: [],
    status: "planned",
    votes: [],
    suggestions: MOCK_MEAL_SUGGESTIONS.breakfast,
  },
  {
    id: "mp-tmrw-lunch",
    date: TOMORROW,
    mealType: "lunch",
    selectedMeal: undefined,
    dishes: [],
    status: "planned",
    prepInstructions: "Soak chole tonight if Chole Bhature is selected",
    prepStatus: "assigned_cook",
    backupMealId: "s-l3",
    votes: [],
    suggestions: MOCK_MEAL_SUGGESTIONS.lunch,
  },
  {
    id: "mp-tmrw-dinner",
    date: TOMORROW,
    mealType: "dinner",
    selectedMeal: undefined,
    dishes: [],
    status: "planned",
    votes: [],
    suggestions: MOCK_MEAL_SUGGESTIONS.dinner,
  },
];

export const MOCK_TOMORROWS_PLAN: MealPlan = MOCK_TOMORROWS_PLANS[1];

// ─── Orders ───

export const MOCK_ORDERS: Order[] = [
  {
    id: "ord-001",
    items: [
      { id: "i1", name: "Aashirvaad Atta 5kg", quantity: "1", estimatedPrice: 289, platform: "Swiggy Instamart", category: "Staples" },
      { id: "i2", name: "Toor Dal 1kg", quantity: "1", estimatedPrice: 165, platform: "Swiggy Instamart", category: "Pulses" },
      { id: "i3", name: "Amul Butter 500g", quantity: "1", estimatedPrice: 275, platform: "Swiggy Instamart", category: "Dairy" },
    ],
    totalAmount: 729,
    status: "pending",
    requestedBy: "Malti Didi",
    requestedAt: new Date(Date.now() - 3600000).toISOString(),
    perPersonShare: { "v-001": 243, "v-002": 243, "v-003": 243 },
  },
  {
    id: "ord-002",
    items: [
      { id: "i4", name: "Onion 2kg", quantity: "1", estimatedPrice: 80, category: "Vegetables" },
      { id: "i5", name: "Tomato 1kg", quantity: "1", estimatedPrice: 45, category: "Vegetables" },
      { id: "i6", name: "Green Chillies 100g", quantity: "1", estimatedPrice: 15, category: "Vegetables" },
    ],
    totalAmount: 140,
    status: "auto_approved",
    requestedBy: "Malti Didi",
    requestedAt: new Date(Date.now() - 86400000).toISOString(),
    approvedAt: new Date(Date.now() - 86400000 + 60000).toISOString(),
    autoApprovalReason: "Under ₹500 and 6 days since last order",
    perPersonShare: { "v-001": 47, "v-002": 47, "v-003": 46 },
  },
  {
    id: "ord-003",
    items: [
      { id: "i7", name: "Paneer 200g", quantity: "2", estimatedPrice: 180, category: "Dairy" },
      { id: "i8", name: "Cream 200ml", quantity: "1", estimatedPrice: 65, category: "Dairy" },
    ],
    totalAmount: 245,
    status: "delivered",
    requestedBy: "Malti Didi",
    requestedAt: new Date(Date.now() - 172800000).toISOString(),
    approvedBy: "Anjan",
    approvedAt: new Date(Date.now() - 172800000 + 300000).toISOString(),
    deliveryEta: "Delivered",
    perPersonShare: { "v-001": 82, "v-002": 82, "v-003": 81 },
  },
];

// ─── Auto Rules ───

export const MOCK_AUTO_RULES: AutoApprovalRule[] = [
  { id: "rule-001", maxAmount: 500, minDaysSinceLastOrder: 5, trustedItems: ["Atta", "Rice", "Dal", "Oil", "Salt", "Sugar", "Milk"], enabled: true, createdBy: "Anjan" },
];

// ─── Inventory ───

export const MOCK_INVENTORY: InventoryItem[] = [
  { id: "inv-01", name: "Aashirvaad Atta", category: "Staples", currentQuantity: "2", unit: "kg", estimatedDaysLeft: 4, isLowStock: true, lastRestocked: "2026-04-10", depletionRate: 0.5 },
  { id: "inv-02", name: "Basmati Rice", category: "Staples", currentQuantity: "3", unit: "kg", estimatedDaysLeft: 10, isLowStock: false, lastRestocked: "2026-04-08", depletionRate: 0.3 },
  { id: "inv-03", name: "Toor Dal", category: "Pulses", currentQuantity: "0.5", unit: "kg", estimatedDaysLeft: 3, isLowStock: true, lastRestocked: "2026-04-05", depletionRate: 0.15 },
  { id: "inv-04", name: "Rajma", category: "Pulses", currentQuantity: "1", unit: "kg", estimatedDaysLeft: 12, isLowStock: false, lastRestocked: "2026-04-01", depletionRate: 0.08 },
  { id: "inv-05", name: "Chickpeas", category: "Pulses", currentQuantity: "0.8", unit: "kg", estimatedDaysLeft: 8, isLowStock: false, lastRestocked: "2026-04-03", depletionRate: 0.1 },
  { id: "inv-06", name: "Cooking Oil", category: "Oils", currentQuantity: "1.5", unit: "L", estimatedDaysLeft: 7, isLowStock: false, lastRestocked: "2026-04-07", depletionRate: 0.2 },
  { id: "inv-07", name: "Amul Butter", category: "Dairy", currentQuantity: "200", unit: "g", estimatedDaysLeft: 5, isLowStock: true, lastRestocked: "2026-04-09", depletionRate: 40 },
  { id: "inv-08", name: "Paneer", category: "Dairy", currentQuantity: "400", unit: "g", estimatedDaysLeft: 2, isLowStock: true, lastRestocked: "2026-04-13", depletionRate: 200, expiryDate: "2026-04-16" },
  { id: "inv-09", name: "Onion", category: "Vegetables", currentQuantity: "1.5", unit: "kg", estimatedDaysLeft: 4, isLowStock: true, lastRestocked: "2026-04-11", depletionRate: 0.4 },
  { id: "inv-10", name: "Tomato", category: "Vegetables", currentQuantity: "0.5", unit: "kg", estimatedDaysLeft: 2, isLowStock: true, lastRestocked: "2026-04-12", depletionRate: 0.25 },
  { id: "inv-11", name: "Potato", category: "Vegetables", currentQuantity: "2", unit: "kg", estimatedDaysLeft: 8, isLowStock: false, lastRestocked: "2026-04-10", depletionRate: 0.25 },
  { id: "inv-12", name: "Milk (Amul)", category: "Dairy", currentQuantity: "1", unit: "L", estimatedDaysLeft: 1, isLowStock: true, lastRestocked: "2026-04-14", depletionRate: 1 },
  { id: "inv-13", name: "Tea (Tata Gold)", category: "Beverages", currentQuantity: "100", unit: "g", estimatedDaysLeft: 5, isLowStock: true, lastRestocked: "2026-04-08", depletionRate: 20 },
  { id: "inv-14", name: "Sugar", category: "Staples", currentQuantity: "1", unit: "kg", estimatedDaysLeft: 15, isLowStock: false, lastRestocked: "2026-04-01", depletionRate: 0.07 },
];

// ─── Cook Messages ───

export const MOCK_COOK_MESSAGES: CookMessage[] = [
  {
    id: "msg-001",
    type: "voice",
    content: "Good morning. Atta lagbhag khatam hai, sirf 2 kg bacha hai. Toor dal bhi sirf 200 g bachi hai aur tamatar kal khatam ho gaye.",
    originalHindi: "Good morning. Atta lagbhag khatam hai, sirf 2 kg bacha hai. Toor dal bhi sirf 200 g bachi hai aur tamatar kal khatam ho gaye.",
    translation: "Good morning. Atta is almost over, only 2 kg left. Toor dal also down to 200 g and we ran out of tomatoes yesterday.",
    timestamp: new Date(Date.now() - 7200000).toISOString(),
    // Three structured grocery items — the curated demo seed for the
    // Swiggy MCP showcase. `itemName`/`quantity`/`unit` together form
    // the row title; `reasoning` is the smaller subtitle line.
    actionItems: [
      {
        type: "supply_request",
        description: "Order Atta — only 2 kg left",
        resolved: false,
        itemName: "Atta",
        quantity: 5,
        unit: "kg",
        reasoning: "Only 2 kg left and Malti Didi already requested for tomorrow's rotis.",
        requestedBy: "Malti Didi",
        estimatedPriceInr: 285,
        etaMinutes: 12,
      },
      {
        type: "supply_request",
        description: "Order Toor dal — pantry down to 200 g",
        resolved: false,
        itemName: "Toor dal",
        quantity: 1,
        unit: "kg",
        reasoning: "Tonight's plan is dal-chawal; pantry shows 200 g.",
        requestedBy: "Malti Didi",
        estimatedPriceInr: 185,
        etaMinutes: 12,
      },
      {
        type: "supply_request",
        description: "Order Tomatoes — sabzi rotation needs them",
        resolved: false,
        itemName: "Tomatoes",
        quantity: 2,
        unit: "kg",
        reasoning: "Yesterday's curry used the last batch; need for sabzi rotation.",
        requestedBy: "Malti Didi",
        estimatedPriceInr: 70,
        etaMinutes: 12,
      },
    ],
    isFromCook: true,
  },
  {
    id: "msg-002",
    type: "text",
    content: "Aaj kya banau lunch mein? Chole raat ko bhigone padenge agar kal banana hai.",
    originalHindi: "Aaj kya banau lunch mein? Chole raat ko bhigone padenge agar kal banana hai.",
    translation: "What should I make for lunch today? Chole need to be soaked tonight if making tomorrow.",
    timestamp: new Date(Date.now() - 5400000).toISOString(),
    // The `prep_note` ("soak chole") still flows through the chat tab
    // for cook–household visibility, but it's hidden from the user-
    // facing CookActionsSheet — soaking is something the cook handles
    // herself during the previous-meal prep window, not a household
    // decision.
    actionItems: [
      { type: "meal_query", description: "What to cook for lunch?", resolved: true },
      { type: "prep_note", description: "Soak chole tonight for tomorrow", resolved: false },
    ],
    isFromCook: true,
  },
  { id: "msg-003", type: "text", content: "Ok, rajma chawal bana deti hoon. Raita bhi bana doon?", translation: "Ok, I'll make rajma chawal. Should I also make raita?", timestamp: new Date(Date.now() - 4800000).toISOString(), actionItems: [], isFromCook: true },
  { id: "msg-004", type: "text", content: "Haan raita bhi please. And soak chole for tomorrow 🙏", timestamp: new Date(Date.now() - 4200000).toISOString(), actionItems: [], isFromCook: false },
  {
    id: "msg-005",
    type: "voice",
    content: "Milk bhi khatam ho gaya. Kal subah chai ke liye chahiye. Doodh order kar dijiye.",
    originalHindi: "Milk bhi khatam ho gaya hai. Kal subah chai ke liye chahiye. Doodh order kar dijiye please.",
    translation: "Milk is also finished. Need it for tea tomorrow morning. Please order milk.",
    timestamp: new Date(Date.now() - 1800000).toISOString(),
    actionItems: [
      {
        type: "supply_request",
        description: "Order milk — finished, need for morning tea",
        resolved: false,
        itemName: "Full-cream milk",
        quantity: 2,
        unit: "L",
        reasoning: "Out for tomorrow's chai. Malti starts at 6:30 AM.",
        requestedBy: "Malti Didi",
        estimatedPriceInr: 126,
        etaMinutes: 12,
      },
    ],
    isFromCook: true,
  },
];

// ─── Fairness Scores (per household type) ───

// Compute YESTERDAY at module-load time so the demo always has a
// "yesterday" with rich data to surface in the past-day modal even
// before the user pages back through months. Same TODAY-derivation
// pattern used for plans above.
const YESTERDAY = localIsoDatePlus(-1);

export const MOCK_MEAL_HISTORY: import("./types").MealHistoryEntry[] = [
  // ── Today ──
  // Pre-filled per-member ratings + a Bimi-proxy vote on breakfast
  // and dinner so the past-day modal can demonstrate the full
  // attribution + ratings + proxy UX without waiting for the
  // household to actually rate / vote during the demo session.
  { date: TODAY, mealType: "breakfast", selectedMeal: "Poha", participantIds: ["v-001", "v-002", "v-003"], votes: [{ memberId: "v-001", dishName: "Poha", rating: 5, isProxy: false }, { memberId: "v-002", dishName: "Idli Sambar", rating: 4, isProxy: false }, { memberId: "v-003", dishName: "Poha", rating: 4, isProxy: true }], ratings: [{ memberId: "v-001", rating: 5 }, { memberId: "v-002", rating: 4 }, { memberId: "v-003", rating: 5 }] },
  { date: TODAY, mealType: "lunch", selectedMeal: "Rajma Chawal", participantIds: ["v-001", "v-002", "v-003"], votes: [{ memberId: "v-001", dishName: "Rajma Chawal", rating: 5, isProxy: false }, { memberId: "v-002", dishName: "Rajma Chawal", rating: 4, isProxy: false }, { memberId: "v-003", dishName: "Chole Bhature", rating: 4, isProxy: false }], ratings: [{ memberId: "v-001", rating: 4 }, { memberId: "v-002", rating: 5 }] },
  { date: TODAY, mealType: "dinner", selectedMeal: "Dal Tadka", participantIds: ["v-001", "v-002", "v-003"], votes: [{ memberId: "v-001", dishName: "Dal Tadka", rating: 5, isProxy: false }, { memberId: "v-002", dishName: "Dal Tadka", rating: 5, isProxy: true }, { memberId: "v-003", dishName: "Aloo Gobi", rating: 4, isProxy: false }], ratings: [] },
  // ── Yesterday ──
  { date: YESTERDAY, mealType: "breakfast", selectedMeal: "Bread Omelette", participantIds: ["v-001", "v-002", "v-003"], votes: [{ memberId: "v-001", dishName: "Bread Omelette", rating: 4, isProxy: false }, { memberId: "v-002", dishName: "Bread Omelette", rating: 5, isProxy: false }, { memberId: "v-003", dishName: "Poha", rating: 3, isProxy: true }], ratings: [{ memberId: "v-001", rating: 4 }, { memberId: "v-002", rating: 5 }, { memberId: "v-003", rating: 3 }] },
  { date: YESTERDAY, mealType: "lunch", selectedMeal: "Chole Bhature", participantIds: ["v-001", "v-002", "v-003"], votes: [{ memberId: "v-001", dishName: "Chole Bhature", rating: 5, isProxy: false }, { memberId: "v-002", dishName: "Rajma Chawal", rating: 3, isProxy: false }, { memberId: "v-003", dishName: "Chole Bhature", rating: 4, isProxy: false }], ratings: [{ memberId: "v-001", rating: 5 }, { memberId: "v-002", rating: 3 }, { memberId: "v-003", rating: 4 }] },
  { date: YESTERDAY, mealType: "dinner", selectedMeal: "Khichdi", participantIds: ["v-001", "v-002", "v-003"], votes: [{ memberId: "v-001", dishName: "Khichdi", rating: 4, isProxy: false }, { memberId: "v-002", dishName: "Khichdi", rating: 5, isProxy: false }, { memberId: "v-003", dishName: "Khichdi", rating: 5, isProxy: true }], ratings: [{ memberId: "v-001", rating: 4 }, { memberId: "v-002", rating: 5 }, { memberId: "v-003", rating: 4 }] },
  // ── April archive (older history retained for fairness scoring) ──
  { date: "2026-04-10", mealType: "lunch", selectedMeal: "Dal Tadka", participantIds: ["v-001", "v-002", "v-003"], votes: [{ memberId: "v-001", dishName: "Dal Tadka", rating: 5 }, { memberId: "v-002", dishName: "Rajma Chawal", rating: 4 }, { memberId: "v-003", dishName: "Dal Tadka", rating: 3 }], ratings: [{ memberId: "v-001", rating: 5 }, { memberId: "v-002", rating: 3 }, { memberId: "v-003", rating: 4 }] },
  { date: "2026-04-10", mealType: "dinner", selectedMeal: "Aloo Gobi", participantIds: ["v-001", "v-002", "v-003"], votes: [{ memberId: "v-001", dishName: "Aloo Gobi", rating: 3 }, { memberId: "v-002", dishName: "Aloo Gobi", rating: 5 }, { memberId: "v-003", dishName: "Paneer Masala", rating: 4 }], ratings: [{ memberId: "v-001", rating: 3 }, { memberId: "v-002", rating: 5 }, { memberId: "v-003", rating: 3 }] },
  { date: "2026-04-11", mealType: "lunch", selectedMeal: "Rajma Chawal", participantIds: ["v-001", "v-002", "v-003"], votes: [{ memberId: "v-001", dishName: "Chole", rating: 4 }, { memberId: "v-002", dishName: "Rajma Chawal", rating: 5 }, { memberId: "v-003", dishName: "Rajma Chawal", rating: 4 }], ratings: [{ memberId: "v-001", rating: 3 }, { memberId: "v-002", rating: 5 }, { memberId: "v-003", rating: 4 }] },
  { date: "2026-04-11", mealType: "dinner", selectedMeal: "Paneer Butter Masala", participantIds: ["v-001", "v-003"], votes: [{ memberId: "v-001", dishName: "Paneer Butter Masala", rating: 5 }, { memberId: "v-003", dishName: "Paneer Butter Masala", rating: 5 }], ratings: [{ memberId: "v-001", rating: 5 }, { memberId: "v-003", rating: 5 }] },
  { date: "2026-04-12", mealType: "lunch", selectedMeal: "Chole Bhature", participantIds: ["v-001", "v-002", "v-003"], votes: [{ memberId: "v-001", dishName: "Chole Bhature", rating: 5 }, { memberId: "v-002", dishName: "Chole Bhature", rating: 4 }, { memberId: "v-003", dishName: "Dal Tadka", rating: 3 }], ratings: [{ memberId: "v-001", rating: 5 }, { memberId: "v-002", rating: 4 }, { memberId: "v-003", rating: 2 }] },
  { date: "2026-04-13", mealType: "lunch", selectedMeal: "Kadhi", participantIds: ["v-002", "v-003"], votes: [{ memberId: "v-002", dishName: "Kadhi", rating: 3 }, { memberId: "v-003", dishName: "Kadhi", rating: 5 }], ratings: [{ memberId: "v-002", rating: 3 }, { memberId: "v-003", rating: 5 }] },
  { date: "2026-04-13", mealType: "dinner", selectedMeal: "Egg Curry", participantIds: ["v-001", "v-002", "v-003"], votes: [{ memberId: "v-001", dishName: "Egg Curry", rating: 4 }, { memberId: "v-002", dishName: "Biryani", rating: 5 }, { memberId: "v-003", dishName: "Egg Curry", rating: 4 }], ratings: [{ memberId: "v-001", rating: 4 }, { memberId: "v-002", rating: 2 }, { memberId: "v-003", rating: 4 }] },
  { date: "2026-04-14", mealType: "lunch", selectedMeal: "Palak Paneer", participantIds: ["v-001", "v-002", "v-003"], votes: [{ memberId: "v-001", dishName: "Biryani", rating: 5 }, { memberId: "v-002", dishName: "Palak Paneer", rating: 4 }, { memberId: "v-003", dishName: "Palak Paneer", rating: 5 }], ratings: [{ memberId: "v-001", rating: 3 }, { memberId: "v-002", rating: 4 }, { memberId: "v-003", rating: 5 }] },
  { date: "2026-04-15", mealType: "lunch", selectedMeal: "Biryani", participantIds: ["v-001", "v-002", "v-003"], votes: [{ memberId: "v-001", dishName: "Biryani", rating: 5 }, { memberId: "v-002", dishName: "Biryani", rating: 5 }, { memberId: "v-003", dishName: "Dal Tadka", rating: 3 }], ratings: [{ memberId: "v-001", rating: 5 }, { memberId: "v-002", rating: 5 }, { memberId: "v-003", rating: 3 }] },
  { date: "2026-04-16", mealType: "lunch", selectedMeal: "Rajma Chawal", participantIds: ["v-001", "v-002", "v-003"], votes: [{ memberId: "v-001", dishName: "Chole", rating: 4 }, { memberId: "v-002", dishName: "Rajma Chawal", rating: 5 }, { memberId: "v-003", dishName: "Rajma Chawal", rating: 4 }], ratings: [{ memberId: "v-001", rating: 3 }, { memberId: "v-002", rating: 5 }, { memberId: "v-003", rating: 4 }] },
  { date: "2026-04-16", mealType: "dinner", selectedMeal: "Poha", participantIds: ["v-001", "v-002"], votes: [{ memberId: "v-001", dishName: "Poha", rating: 4 }, { memberId: "v-002", dishName: "Poha", rating: 3 }], ratings: [{ memberId: "v-001", rating: 4 }, { memberId: "v-002", rating: 4 }] },
  { date: "2026-04-17", mealType: "breakfast", selectedMeal: "Poha", participantIds: ["v-001", "v-002", "v-003"], votes: [], ratings: [{ memberId: "v-001", rating: 5 }, { memberId: "v-002", rating: 4 }, { memberId: "v-003", rating: 4 }] },
];

export const BACHELOR_FAIRNESS: FairnessScore[] = [
  { memberId: "v-001", memberName: "Anjan", satisfactionScore: 0.72, mealsServed: 12, avgSatisfaction: 3.8, isUnderserved: false },
  { memberId: "v-002", memberName: "Mayank", satisfactionScore: 0.58, mealsServed: 9, avgSatisfaction: 3.2, isUnderserved: true },
  { memberId: "v-003", memberName: "Garvika", satisfactionScore: 0.65, mealsServed: 11, avgSatisfaction: 3.5, isUnderserved: true },
];

export const COUPLE_FAIRNESS: FairnessScore[] = [
  { memberId: "c-001", memberName: "Arun", satisfactionScore: 0.82, mealsServed: 14, avgSatisfaction: 4.1, isUnderserved: false },
  { memberId: "c-002", memberName: "Sneha", satisfactionScore: 0.62, mealsServed: 10, avgSatisfaction: 3.4, isUnderserved: true },
];

export const FAMILY_FAIRNESS: FairnessScore[] = [
  { memberId: "f-001", memberName: "Rahul", satisfactionScore: 0.72, mealsServed: 12, avgSatisfaction: 3.8, isUnderserved: false },
  { memberId: "f-002", memberName: "Priya", satisfactionScore: 0.85, mealsServed: 14, avgSatisfaction: 4.2, isUnderserved: false },
  { memberId: "f-003", memberName: "Arjun", satisfactionScore: 0.58, mealsServed: 9, avgSatisfaction: 3.2, isUnderserved: true },
  { memberId: "f-004", memberName: "Ananya", satisfactionScore: 0.65, mealsServed: 11, avgSatisfaction: 3.5, isUnderserved: true },
];

// ─── Wishlist ───

export const MOCK_WISHLIST: WishlistItem[] = [
  { id: "w-01", name: "Milk 1L", brand: "Amul", quantity: 1, unit: "L", estimatedPrice: 68, source: "cook", addedBy: "Malti Didi", addedAt: new Date(Date.now() - 7200000).toISOString(), priority: "urgent", status: "pending", category: "Dairy" },
  { id: "w-02", name: "Tomato 1kg", quantity: 1, unit: "kg", estimatedPrice: 45, source: "inventory_prediction", addedBy: "Bimi", addedAt: new Date(Date.now() - 3600000).toISOString(), priority: "urgent", status: "pending", category: "Vegetables", notes: "Depletes today" },
  { id: "w-03", name: "Atta 5kg", brand: "Aashirvaad", quantity: 5, unit: "kg", estimatedPrice: 289, source: "cook", addedBy: "Malti Didi", addedAt: new Date(Date.now() - 7200000).toISOString(), priority: "normal", status: "pending", category: "Staples" },
  { id: "w-04", name: "Cream 200ml", brand: "Amul", quantity: 1, unit: "pack", estimatedPrice: 65, source: "ingredient_check", addedBy: "Bimi", addedAt: new Date(Date.now() - 1800000).toISOString(), priority: "normal", status: "pending", category: "Dairy", notes: "For tomorrow's Paneer Masala" },
  { id: "w-05", name: "Haldi 100g", quantity: 1, unit: "pack", estimatedPrice: 35, source: "advisor", addedBy: "Mom", addedAt: new Date(Date.now() - 86400000).toISOString(), priority: "normal", status: "pending", category: "Spices", notes: "Beta haldi order karo" },
  { id: "w-06", name: "Curd 400g", brand: "Amul", quantity: 1, unit: "pack", estimatedPrice: 42, source: "schedule", addedBy: "Auto-rule", addedAt: new Date(Date.now() - 900000).toISOString(), priority: "normal", status: "pending", category: "Dairy", notes: "Every 3 days" },
  { id: "w-07", name: "Cashews 250g", quantity: 1, unit: "pack", estimatedPrice: 390, source: "user", addedBy: "Anjan", addedAt: new Date(Date.now() - 43200000).toISOString(), priority: "low", status: "pending", category: "Dry Fruits" },
];

// ─── Monthly Expenses ───

export const MOCK_EXPENSES: MonthlyExpenseSummary = {
  month: "2026-04",
  totalAmount: 8450,
  orderCount: 12,
  categories: [
    { name: "Vegetables", icon: "🥬", amount: 1840, itemCount: 18, percentage: 21.8 },
    { name: "Dairy", icon: "🥛", amount: 1560, itemCount: 12, percentage: 18.5 },
    { name: "Staples", icon: "🌾", amount: 1420, itemCount: 6, percentage: 16.8 },
    { name: "Pulses", icon: "🫘", amount: 890, itemCount: 5, percentage: 10.5 },
    { name: "Cleaning", icon: "🧴", amount: 680, itemCount: 8, percentage: 8.0 },
    { name: "Beverages", icon: "🍵", amount: 520, itemCount: 4, percentage: 6.2 },
    { name: "Dry Fruits", icon: "🥜", amount: 480, itemCount: 2, percentage: 5.7 },
    { name: "Spices", icon: "🌶️", amount: 340, itemCount: 7, percentage: 4.0 },
    { name: "Fruits", icon: "🍌", amount: 320, itemCount: 3, percentage: 3.8 },
    { name: "Other", icon: "📦", amount: 400, itemCount: 4, percentage: 4.7 },
  ],
  perPerson: [
    { memberId: "v-001", memberName: "Anjan", totalPaid: 5200, share: 2816, balance: 2384 },
    { memberId: "v-002", memberName: "Mayank", totalPaid: 2000, share: 2817, balance: -817 },
    { memberId: "v-003", memberName: "Garvika", totalPaid: 1250, share: 2817, balance: -1567 },
  ],
  settlements: [
    { fromMemberId: "v-002", fromName: "Mayank", toMemberId: "v-001", toName: "Anjan", amount: 817, settled: false },
    { fromMemberId: "v-003", fromName: "Garvika", toMemberId: "v-001", toName: "Anjan", amount: 1567, settled: false },
  ],
  activities: [
    { id: "act-1", type: "order", description: "Swiggy Instamart order", amount: 729, timestamp: new Date(Date.now() - 2 * 86400000).toISOString(), involvedMembers: ["Anjan"] },
    { id: "act-2", type: "order", description: "Zepto order", amount: 312, timestamp: new Date(Date.now() - 4 * 86400000).toISOString(), involvedMembers: ["Mayank"] },
    { id: "act-3", type: "order", description: "Blinkit order", amount: 189, timestamp: new Date(Date.now() - 6 * 86400000).toISOString(), involvedMembers: ["Anjan"] },
    { id: "act-4", type: "order", description: "Swiggy Instamart order", amount: 1450, timestamp: new Date(Date.now() - 8 * 86400000).toISOString(), involvedMembers: ["Garvika"] },
    { id: "act-5", type: "order", description: "BigBasket order", amount: 2100, timestamp: new Date(Date.now() - 10 * 86400000).toISOString(), involvedMembers: ["Anjan"] },
  ],
};

// ─── Cook Simulator ───

const COOK_SIMULATOR_MESSAGES = [
  { hindi: "Madam, aaj sabzi mein kya banau?", english: "Madam, what vegetable should I make today?", type: "meal_query" as const },
  { hindi: "Namak khatam ho gaya hai, order kar dijiye", english: "Salt is finished, please order", type: "supply_request" as const },
  { hindi: "Paneer bahut purana ho gaya hai, naya mangwa lijiye", english: "Paneer has gone old, please get fresh", type: "supply_request" as const },
  { hindi: "Kal chutti chahiye, beti ki school mein function hai", english: "Need leave tomorrow, daughter has school function", type: "absence" as const },
  { hindi: "Dahi jamane ke liye doodh rakh diya hai", english: "Kept milk for setting curd", type: "prep_note" as const },
  { hindi: "Ghee bhi khatam hone wala hai, 2-3 din mein", english: "Ghee is about to finish in 2-3 days", type: "low_stock" as const },
  { hindi: "Madam, chole bhigona bhool gayi thi raat ko", english: "Madam, I forgot to soak the chole last night", type: "prep_failed" as const },
];

export function generateCookMessage(): CookMessage {
  const template = COOK_SIMULATOR_MESSAGES[Math.floor(Math.random() * COOK_SIMULATOR_MESSAGES.length)];
  return {
    id: `msg-sim-${Date.now()}`,
    type: Math.random() > 0.5 ? "voice" : "text",
    content: template.english,
    originalHindi: template.hindi,
    translation: template.english,
    timestamp: new Date().toISOString(),
    actionItems: [{ type: template.type, description: template.english, resolved: false }],
    isFromCook: true,
  };
}
