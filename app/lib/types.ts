// ─── Household Configuration ───

export type HouseholdType =
  | "self_use"
  | "couple"
  | "flatmates"
  | "pg_hostel"
  | "nuclear_family"
  | "joint_family"
  | "single_parent";

export type MemberRole = "partner" | "flatmate" | "parent" | "child" | "member";

export type VotingMode = "solo" | "consensus" | "majority" | "hierarchical";
export type ExpenseMode = "none" | "equal_split" | "custom_split" | "budget";
export type KitchenMode = "self_cook" | "shared_cook" | "multi_cook" | "mess_supplement";
export type MemberFluidity = "static" | "semi_fluid" | "managed";
export type AutomationLevel = "manual" | "suggested" | "semi_auto" | "full_auto";

export type ApprovalMode = "any-payer" | "all-payers";

export interface HouseholdConfig {
  votingMode: VotingMode;
  expenseMode: ExpenseMode;
  kitchenMode: KitchenMode;
  memberFluidity: MemberFluidity;
  automationLevel: AutomationLevel;
  votingDeadlineHour: number;
  approvalMode: ApprovalMode;
}

export const HOUSEHOLD_DEFAULTS: Record<HouseholdType, HouseholdConfig> = {
  self_use:       { votingMode: "solo",          expenseMode: "none",         kitchenMode: "self_cook",       memberFluidity: "static",     automationLevel: "suggested",  votingDeadlineHour: 20, approvalMode: "any-payer" },
  couple:         { votingMode: "consensus",     expenseMode: "equal_split",  kitchenMode: "shared_cook",     memberFluidity: "semi_fluid", automationLevel: "suggested",  votingDeadlineHour: 20, approvalMode: "any-payer" },
  flatmates:      { votingMode: "majority",      expenseMode: "equal_split",  kitchenMode: "shared_cook",     memberFluidity: "semi_fluid", automationLevel: "suggested",  votingDeadlineHour: 19, approvalMode: "any-payer" },
  pg_hostel:      { votingMode: "solo",          expenseMode: "none",         kitchenMode: "mess_supplement", memberFluidity: "managed",    automationLevel: "manual",     votingDeadlineHour: 20, approvalMode: "any-payer" },
  nuclear_family: { votingMode: "hierarchical",  expenseMode: "budget",       kitchenMode: "shared_cook",     memberFluidity: "static",     automationLevel: "semi_auto",  votingDeadlineHour: 20, approvalMode: "any-payer" },
  joint_family:   { votingMode: "hierarchical",  expenseMode: "budget",       kitchenMode: "multi_cook",      memberFluidity: "static",     automationLevel: "semi_auto",  votingDeadlineHour: 20, approvalMode: "any-payer" },
  single_parent:  { votingMode: "solo",          expenseMode: "none",         kitchenMode: "shared_cook",     memberFluidity: "static",     automationLevel: "full_auto",  votingDeadlineHour: 20, approvalMode: "any-payer" },
};

// ─── Core Data Models ───

export type MealType = "breakfast" | "lunch" | "dinner" | "snack";
export type SafetyClass = "critical" | "health" | "preference";

export type MealPlanStatus =
  | "planned"
  | "ingredients_ordered"
  | "ingredients_delivered"
  | "cooking"
  | "cooked"
  | "cancelled";

export interface HouseholdMember {
  id: string;
  name: string;
  role: MemberRole;
  avatar?: string;
  isPayingMember: boolean;
  isAdmin: boolean;
  isActive: boolean;
  isAvailable: boolean;
  joinedAt: string;
  dietaryPreferences: DietaryPreference[];
  healthConditions: string[];
  /** UPI VPA used by the Settle-Up "Pay via UPI" deep-link in Expenses. */
  upiId?: string;
}

export interface DietaryPreference {
  item: string;
  type: "allergy" | "intolerance" | "avoidance" | "preference";
  safetyClass: SafetyClass;
  notes?: string;
}

export interface CookSlot {
  type: "morning" | "evening";
  arrivalTime: string;
  departureTime: string;
  workingDays: string[];
}

export interface Cook {
  id: string;
  name: string;
  whatsappNumber: string;
  schedule: string;
  repertoire: string[];
  payDay?: number;
  salary?: number;
  kitchen?: string;
  slots?: CookSlot[];
  monthlyLeaves?: number;
  dietaryRestrictions?: string[];
  brandPreferences?: Record<string, string>;
}

export interface Household {
  id: string;
  type: HouseholdType;
  name: string;
  members: HouseholdMember[];
  cooks: Cook[];
  hasCook: boolean;
  config: HouseholdConfig;
  inviteCode?: string;
  inviteCodeExpiresAt?: string;
  /**
   * @deprecated Bimi serves cook households only as of 2026-05-03.
   *
   * Persisted to the backend Family row (migration 033). Always treat as
   * `true` going forward — the no-cook ICP fork was removed when the app
   * scope narrowed. The field is kept here for legacy local-store payloads
   * and backend-row compatibility but no UI or routing branch reads it
   * anymore. Remove in a future cleanup once all clients have migrated.
   */
  hasRegularCook?: boolean | null;
  /**
   * P3: Used by progressive disclosure to gate features by tenure
   * (week 0 = all hidden except essentials, week 2 = expenses, etc.).
   */
  createdAt?: string;
  /**
   * P3: Set when a household is archived (e.g. after couple breakup).
   * Archived households render an empty surface with create/join CTAs.
   */
  archivedAt?: string;
  /**
   * Coordination-first pilot cohort tag. When set to "pilot_v1", the app
   * shows the simplified pilot surface via `usePilotMode()`. Mirrors the
   * backend `families.cohort` column (see investor/PILOT-PLAYBOOK.md §1).
   */
  cohort?: string;
}

// ─── Meal Intelligence ───

export interface MealSuggestion {
  id: string;
  dishName: string;
  confidence: number;
  fairnessScore: number;
  noveltyBonus: number;
  constraints: MealConstraint[];
  prepTime: string;
  needsAdvancePrep: boolean;
  advancePrepNote?: string;
  ingredients: string[];
  missingIngredients: string[];
  plateType?: "veg" | "non_veg" | "shared";
  sourceUrl?: string;
  sourcePlatform?: "youtube" | "instagram" | "other";
  sourceThumbnail?: string;
  suggestedById?: string;
  suggestedByName?: string;
  noteForCook?: string;
}

export interface MealConstraint {
  type: "allergy" | "health" | "repertoire";
  description: string;
  memberName: string;
  severity: "block" | "warning" | "info";
}

export type PrepStatus = "assigned_cook" | "assigned_user" | "confirmed" | "failed";

export interface MealPlan {
  id: string;
  date: string;
  mealType: MealType;
  /**
   * Current winning dish. Set when the voting threshold is first met (a
   * "soft pick" that's still mutable during the lock-in window) AND remains
   * after hard-lock fires.
   */
  selectedMeal?: string;
  dishes: string[];
  status: MealPlanStatus;
  prepInstructions?: string;
  prepStatus?: PrepStatus;
  backupMealId?: string;
  switchedFromMeal?: string;
  votes: MealVote[];
  suggestions: MealSuggestion[];
  ingredientChecks?: IngredientCheck[];
  rating?: number;

  /**
   * Soft-lock window: when the household's voting threshold is first crossed,
   * we set this to `min(now + 5min, votingDeadline)`. Until this moment passes,
   * users can still switch their pick (the timer does NOT reset on changes —
   * "settle down, don't drag forever") and the cook is NOT yet briefed.
   *
   * Cleared once the hard-lock has fired (or unset entirely if the user resets
   * the plan via "Change meal").
   */
  lockInAt?: string;

  /**
   * Hard-lock flag. True once `lockInPlan(mealType)` has fired — at this point
   * the cook brief has been mirrored into the cook chat exactly once, the
   * winner is final, and the screen flips to "Locked in. Tell cook directly
   * if you change your mind."
   */
  isLocked?: boolean;
}

export interface MealVote {
  memberId: string;
  memberName: string;
  dishId: string;
  dishName: string;
  rating: number;
  timestamp: string;
  isProxy: boolean;
  proxyConfidence?: number;
  skipped?: boolean;
}

export interface FairnessScore {
  memberId: string;
  memberName: string;
  satisfactionScore: number;
  mealsServed: number;
  avgSatisfaction: number;
  isUnderserved: boolean;
}

export interface MealHistoryEntry {
  date: string;
  mealType: MealType;
  selectedMeal: string;
  participantIds: string[];
  /**
   * Per-member votes captured at finalize time. `isProxy` is set when
   * Bimi auto-cast a vote on the member's behalf (proxy-vote deadline,
   * absent member, etc.) — used by the past-day modal to render
   * "Bimi proxy-voted Maggi for Saumya" with attribution. Optional /
   * defaults false so older serialised entries (pre this field) still
   * deserialise cleanly.
   */
  votes: { memberId: string; dishName: string; rating: number; isProxy?: boolean }[];
  ratings: { memberId: string; rating: number }[];
}

// ─── Ingredient Pre-Check ───

export interface IngredientCheck {
  ingredient: string;
  quantity: string;
  unit: string;
  status: "in_stock" | "low_stock" | "missing" | "ordered" | "delivered";
  source?: string;
  eta?: string;
}

export interface PrepTimeline {
  mealName: string;
  date: string;
  mealType: MealType;
  prepSteps: { time: string; instruction: string }[];
  ingredientChecks: IngredientCheck[];
  cookArrivalTime: string;
  estimatedCookTime: string;
  allIngredientsReady: boolean;
}

// ─── Orders ───

export interface OrderItem {
  id: string;
  name: string;
  quantity: string;
  estimatedPrice: number;
  platform?: string;
  category?: string;
}

export interface Order {
  id: string;
  items: OrderItem[];
  totalAmount: number;
  status: "pending" | "auto_approved" | "approved" | "rejected" | "ordered" | "delivered";
  requestedBy: string;
  requestedAt: string;
  approvedBy?: string;
  approvedAt?: string;
  autoApprovalReason?: string;
  deliveryEta?: string;
  perPersonShare?: Record<string, number>;
}

export interface AutoApprovalRule {
  id: string;
  maxAmount: number;
  minDaysSinceLastOrder: number;
  trustedItems: string[];
  timeWindowStart?: string;
  timeWindowEnd?: string;
  enabled: boolean;
  createdBy: string;
}

// ─── Smart Wishlist ───

export type WishlistSource = "cook" | "user" | "advisor" | "inventory_prediction" | "schedule" | "ingredient_check";
export type WishlistPriority = "urgent" | "normal" | "low";
export type WishlistStatus = "pending" | "in_cart" | "ordered" | "bought_in_person" | "cancelled";

export interface WishlistItem {
  id: string;
  name: string;
  brand?: string;
  quantity: number;
  unit: string;
  estimatedPrice?: number;
  source: WishlistSource;
  addedBy: string;
  addedAt: string;
  priority: WishlistPriority;
  status: WishlistStatus;
  notes?: string;
  category?: string;
}

// ─── Kitchen Inventory ───

export interface InventoryItem {
  id: string;
  name: string;
  category: string;
  currentQuantity: string;
  unit: string;
  estimatedDaysLeft: number;
  isLowStock: boolean;
  lastRestocked?: string;
  depletionRate: number;
  expiryDate?: string;
}

// ─── Expense Ledger ───

export interface ExpenseCategory {
  name: string;
  icon: string;
  amount: number;
  itemCount: number;
  percentage: number;
}

export interface PersonExpense {
  memberId: string;
  memberName: string;
  totalPaid: number;
  share: number;
  balance: number;
}

export interface Settlement {
  fromMemberId: string;
  fromName: string;
  toMemberId: string;
  toName: string;
  amount: number;
  settled: boolean;
  settledAt?: string;
  splitwiseExpenseId?: string;
}

export interface ExpenseActivity {
  id: string;
  type: "settlement" | "order" | "splitwise_push";
  description: string;
  amount: number;
  timestamp: string;
  involvedMembers: string[];
}

export interface MonthlyExpenseSummary {
  month: string;
  totalAmount: number;
  orderCount: number;
  categories: ExpenseCategory[];
  perPerson: PersonExpense[];
  settlements: Settlement[];
  activities: ExpenseActivity[];
}

// ─── Cook Messages ───

export interface CookMessage {
  id: string;
  type: "text" | "voice" | "image";
  content: string;
  originalHindi?: string;
  translation?: string;
  timestamp: string;
  actionItems: ActionItem[];
  isFromCook: boolean;
}

export interface ActionItem {
  type: "supply_request" | "meal_query" | "low_stock" | "absence" | "prep_note" | "prep_failed";
  description: string;
  resolved: boolean;
  // Structured grocery fields. `itemName`, `quantity`, `unit`, and
  // `reasoning` come from the cook-message intent extractor (or the
  // demo seed) and ARE rendered in the cart sheet — they're our data,
  // not Swiggy's, so they're safe to surface.
  //
  // `estimatedPriceInr`, `etaMinutes`, `brandHint`, and `requestedBy`
  // are RESERVED for the eventual Swiggy MCP wire-up. They are NOT
  // surfaced in the UI today: the Swiggy Builders Club rules forbid
  // "misrepresenting prices, availability, or delivery times" and
  // "misattributing where data comes from"
  // (https://mcp.swiggy.com/builders/access/), and any value we put
  // there before MCP access is invented. The data shape stays so that
  // when MCP is connected, surfacing them is a one-line render swap,
  // not a schema migration.
  itemName?: string;
  quantity?: number;
  unit?: string;
  reasoning?: string;
  requestedBy?: string;        // reserved — see comment above
  estimatedPriceInr?: number;  // reserved — see comment above
  etaMinutes?: number;         // reserved — see comment above
  brandHint?: string;          // reserved — see comment above
}

// ─── Notifications ───

export type NotificationType =
  | "order_pending"
  | "order_approved"
  | "order_auto_approved"
  | "cook_message"
  | "prep_reminder"
  | "low_stock"
  | "vote_reminder"
  | "meal_finalized"
  | "member_joined"
  | "member_left"
  | "member_removed"
  | "vote_cast"
  | "all_voted"
  | "approval_needed"
  | "partner_approved"
  | "expense_settled"
  | "you_owe"
  | "you_are_owed"
  | "cook_changed"
  | "proxy_vote_cast"
  | "voting_deadline_reminder"
  | "ingredients_missing"
  | "ingredients_ordered"
  | "morning_readiness"
  | "prep_user_needed"
  | "prep_check"
  | "prep_failed_auto_switch"
  | "instacook_confirmed"
  | "instacook_en_route"
  | "instacook_arrived"
  | "instacook_cooking"
  | "instacook_ready"
  | "instacook_cancelled"
  | "instacook_no_cook"
  | "instacook_sunday_promo"
  | "instacook_sous_suggestion"
  | "instacook_household_booked";

// ─── Splitwise ───

export interface SplitwiseConfig {
  connected: boolean;
  accessToken?: string;
  groupId?: string;
  groupName?: string;
  autoSync: boolean;
  syncTiming: "after_delivery" | "daily" | "manual";
  memberMapping: { bimiMemberId: string; splitwiseUserId: number }[];
  lastSyncedAt?: string;
}

// ─── Recipe Sources (YouTube Linking) ───

export interface RecipeSource {
  id: string;
  dishName: string;
  youtubeUrl: string;
  channelName?: string;
  videoTitle?: string;
  contributedByName?: string;
  contributedByRole: "member" | "cook";
  ingredientsExtracted?: Record<string, string>;
  avgRating: number;
  timesUsed: number;
  cookFeedback?: string;
  isCookApproved: boolean;
  isDefault: boolean;
  sourcePlatform?: "youtube" | "instagram" | "other";
  thumbnailUrl?: string;
  description?: string;
}

// ─── Leftovers ───

export interface LeftoverItem {
  id: string;
  dishName: string;
  mealDate: string;
  mealType: MealType;
  portionsRemaining: number;
  isConsumed: boolean;
  isDisposed: boolean;
  isSafe: boolean;
  notes?: string;
}

// ─── Health Outcome Tracking ───

export type HealthMetricType =
  | "a1c"
  | "fasting_glucose"
  | "bp_systolic"
  | "bp_diastolic"
  | "total_cholesterol"
  | "ldl"
  | "hdl"
  | "triglycerides"
  | "weight"
  | "bmi";

export type HealthStatus = "healthy" | "warning" | "critical" | "normal";

export interface HealthMetric {
  id: string;
  personId: string;
  personName: string;
  metricType: HealthMetricType;
  value: number;
  unit: string;
  dateRecorded: string;
  source: "manual" | "lab_report";
  notes?: string;
  status: HealthStatus;
}

export interface HealthTrend {
  personId: string;
  personName: string;
  metricType: HealthMetricType;
  label: string;
  unit: string;
  dataPoints: { date: string; value: number }[];
  currentValue?: number;
  previousValue?: number;
  change?: number;
  changeDirection?: "improved" | "worsened" | "stable";
  status: HealthStatus;
}

// ─── Guest Management ───

export interface GuestProfile {
  id: string;
  name: string;
  dietaryType?: string;
  allergies?: string[];
  healthConditions?: string[];
  notes?: string;
  visitCount: number;
  lastVisit?: string;
}

export type GuestType = "extended_family" | "friends" | "work" | "other";

export interface GuestVisit {
  id: string;
  guestName: string;
  mealDate: string;
  mealType: MealType;
  headCount: number;
  dietaryConstraints?: Record<string, string>;
  isActive: boolean;
  guestType?: GuestType;
}

// ─── Ingredient Substitutions ───

export interface IngredientSubstitution {
  original: string;
  substitute: string;
  compatibilityScore: number;
  flavorSimilarity: number;
  textureSimilarity: number;
  healthBenefits?: Record<string, boolean>;
  notes?: string;
}

// ─── Monthly Budget ───

export interface MonthlyBudget {
  month: string;
  budgetAmount: number;
  categoryBudgets?: Record<string, number>;
  spent: number;
  remaining: number;
}

// ─── Cook Absence Fallback ───

export type CookAbsenceFallback = "order_food" | "self_cook" | "replacement_cook" | "instacook" | "skip";

export interface CookAbsenceEvent {
  id: string;
  cookName: string;
  date: string;
  endDate?: string;
  reason?: string;
  fallbackChosen?: CookAbsenceFallback;
  fallbackDetails?: string;
  replacementBooked: boolean;
  /**
   * Meals the cook is off for. When omitted, treat the absence as
   * full-day (every meal). Allows partial-day absences like "Malti Didi
   * is off for Wed dinner only" to be expressed without a separate
   * absence per meal.
   */
  affectedMeals?: MealType[];
}

// 2026-05-03 audit: deleted ~200 lines of Insta Cook + multi-platform
// types — `BookingType`, `BookingStatus`, `PaymentStatus`, `PoolCook`,
// `CookMatch`, `InstacookBooking`, `BookingWithCook`, `MenuSuggestion`,
// `FamiliarCook`, `InstacookAbsenceData`, `DishEstimate`, `AddonSuggestion`,
// `PriceEstimate`, `CookAssignment`, `EstimateResponse`,
// `AssistEstimateResponse`, `DishPlan`, `PlanResponse`, `PromotionContext`,
// `TimeSlot`, `SlotsResponse`. None were imported anywhere after the
// hooks + screens that consumed them were retired (founder call: "No
// Insta Cook for now").
