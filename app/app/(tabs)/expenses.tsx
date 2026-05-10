import { View, Text, ScrollView, TouchableOpacity, Platform, LayoutAnimation, UIManager, TextInput, Linking } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import Animated, { FadeInDown, FadeInLeft } from "react-native-reanimated";
import { useMemo, useState, useRef, useEffect } from "react";
import { useExpenseStore, useHouseholdStore } from "@/lib/store";
import { useNotificationStore } from "@/lib/notifications";
import { GradientScreen } from "@/components/GradientScreen";
import { GuidanceTip } from "@/components/GuidanceTip";
import { SkeletonCard } from "@/components/Skeleton";
import { RipplePressable } from "@/components/RipplePressable";
import { colors, cardStyles, listRowStyles, spacing, radius, typography, staggerDelay, tintedBg } from "@/lib/theme";
import { haptic } from "@/lib/haptics";
import { useReducedMotion } from "@/lib/useReducedMotion";
import { useTabScrollToTop } from "@/lib/hooks/useTabScrollToTop";
import { showAlert, showConfirm } from "@/lib/dialogs";

if (Platform.OS === "android" && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

const CATEGORY_ACCENT: Record<string, string> = {
  Vegetables: colors.accent.success, Dairy: colors.accent.primary, Staples: colors.accent.warning, Pulses: colors.accent.success,
  Cleaning: colors.accent.info, Beverages: colors.text.muted, "Dry Fruits": colors.accent.primary, Spices: colors.accent.warning,
  Fruits: colors.accent.success, Other: colors.text.muted,
};

function timeAgo(timestamp: string): string {
  const diff = Date.now() - new Date(timestamp).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(timestamp).toLocaleDateString("en-IN", { month: "short", day: "numeric" });
}

export default function ExpensesScreen() {
  const summary = useExpenseStore((s) => s.summary);
  const settleDebt = useExpenseStore((s) => s.settleDebt);
  const unsettleDebt = useExpenseStore((s) => s.unsettleDebt);
  const addOrderExpense = useExpenseStore((s) => s.addOrderExpense);
  const household = useHouseholdStore((s) => s.household);
  const addNotification = useNotificationStore((s) => s.addNotification);
  const activeMembers = useMemo(() => household?.members.filter((m) => m.isActive) || [], [household]);

  const [expandedPerson, setExpandedPerson] = useState<string | null>(null);
  const [showAllActivity, setShowAllActivity] = useState(false);
  const [showCategories, setShowCategories] = useState(false);
  const [copiedSplitwise, setCopiedSplitwise] = useState(false);
  const [monthOffset, setMonthOffset] = useState(0);
  const [showAddExpense, setShowAddExpense] = useState(false);
  const [expAmount, setExpAmount] = useState("");
  const [expDesc, setExpDesc] = useState("");
  const [expPaidBy, setExpPaidBy] = useState("");
  const copyTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  useEffect(() => () => { if (copyTimerRef.current) clearTimeout(copyTimerRef.current); }, []);

  const unsettled = useMemo(() => summary.settlements.filter((s) => !s.settled), [summary]);
  const settled = useMemo(() => summary.settlements.filter((s) => s.settled), [summary]);
  const allSquare = unsettled.length === 0;
  const maxCategoryAmount = useMemo(() => Math.max(...summary.categories.map((c) => c.amount), 1), [summary]);
  const displayMonth = useMemo(() => {
    const base = new Date(summary.month + "-01");
    base.setMonth(base.getMonth() + monthOffset);
    return base;
  }, [summary.month, monthOffset]);
  const monthLabel = displayMonth.toLocaleDateString("en-IN", { month: "long", year: "numeric" });
  const isCurrentMonth = monthOffset === 0;
  const perPersonAvg = Math.round(summary.totalAmount / Math.max(activeMembers.length, 1));

  const visibleActivities = showAllActivity ? summary.activities : summary.activities.slice(0, 3);

  const handleSettle = (fromId: string, toId: string, fromName: string, toName: string, amount: number) => {
    // Confirm before marking settled — this is a money decision and a single
    // tap could let someone wipe a real debt without actual payment.
    const doSettle = () => {
      haptic("success");
      settleDebt(fromId, toId);
      addNotification({ type: "expense_settled", title: "Payment confirmed", body: `${fromName} → ${toName}: ₹${amount} marked as received.` });
    };
    showConfirm(
      "Mark as received?",
      `Confirm that ${toName} received ₹${amount} from ${fromName}. This only clears the debt in Bimi — it does not transfer money.`,
      { onConfirm: doSettle, confirmText: "Yes, received" },
    );
  };

  // P3 (PRD 4.6): Try Splitwise app deep link → fall back to clipboard +
  // share so users with the app installed jump straight to it, while
  // everyone else still gets the formatted ledger to paste manually.
  const handlePushToSplitwise = async () => {
    const lines = [
      `Groceries – ${monthLabel} | ₹${summary.totalAmount.toLocaleString()}`,
      "",
      ...summary.perPerson.map((p) => `${p.memberName} paid ₹${p.totalPaid.toLocaleString()} (share ₹${p.share.toLocaleString()})`),
    ];
    if (unsettled.length > 0) {
      lines.push("---");
      unsettled.forEach((s) => lines.push(`${s.fromName} owes ${s.toName} ₹${s.amount.toLocaleString()}`));
    }
    const text = lines.join("\n");

    // Step 1: copy to clipboard so user can paste once Splitwise opens.
    try {
      const ExpoClipboard = require("expo-clipboard");
      await ExpoClipboard.setStringAsync(text);
    } catch {
      /* clipboard not available */
    }
    setCopiedSplitwise(true);
    if (copyTimerRef.current) clearTimeout(copyTimerRef.current);
    copyTimerRef.current = setTimeout(() => setCopiedSplitwise(false), 2000);

    // Step 2: try opening the Splitwise app via its deep link, then web.
    try {
      await Linking.openURL("splitwise://");
      return;
    } catch {
      /* not installed */
    }
    try {
      await Linking.openURL("https://secure.splitwise.com/#/groups");
      return;
    } catch {
      /* no browser */
    }

    // Step 3: surface the system share sheet as a final fallback so the
    // user can drop it into any messenger.
    try {
      const { Share } = require("react-native");
      await Share.share({ message: text });
    } catch {
      /* nothing more we can do */
    }
  };

  const reducedMotion = useReducedMotion();

  const togglePerson = (id: string) => {
    if (!reducedMotion) LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    setExpandedPerson((prev) => (prev === id ? null : id));
  };

  const scrollRef = useTabScrollToTop<ScrollView>();

  return (
    <GradientScreen>
    <ScrollView
      ref={scrollRef}
      style={{ flex: 1 }}
      contentContainerStyle={{ padding: spacing.lg, paddingBottom: 120, paddingTop: 60 }}
    >
      {summary.orderCount === 0 && (
        <View style={{ marginBottom: spacing.lg }}>
          <GuidanceTip
            variant="hint"
            message="This is where you'll see grocery spending, who paid what, and settle balances. Expenses appear automatically when orders are approved."
            compact
          />
        </View>
      )}

      {/* ── Month Header ── */}
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.sm }}>
        <TouchableOpacity onPress={() => setMonthOffset((p) => p - 1)} hitSlop={12} accessibilityLabel="Previous month" accessibilityRole="button" style={{ minWidth: 44, minHeight: 44, alignItems: "center", justifyContent: "center" }}><Ionicons name="chevron-back" size={20} color={colors.text.muted} /></TouchableOpacity>
        <Text style={typography.h2}>{monthLabel}</Text>
        <TouchableOpacity onPress={() => { if (monthOffset < 0) setMonthOffset((p) => p + 1); }} hitSlop={12} accessibilityLabel="Next month" accessibilityRole="button" style={{ minWidth: 44, minHeight: 44, alignItems: "center", justifyContent: "center", opacity: monthOffset >= 0 ? 0.3 : 1 }}><Ionicons name="chevron-forward" size={20} color={colors.text.muted} /></TouchableOpacity>
      </View>
      {/* ── Add Expense ── */}
      {isCurrentMonth && !showAddExpense && (
        <TouchableOpacity
          onPress={() => { setShowAddExpense(true); setExpAmount(""); setExpDesc(""); setExpPaidBy(activeMembers[0]?.id || ""); }}
          accessibilityRole="button"
          accessibilityLabel="Add a grocery expense"
          style={{
            flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6,
            borderWidth: 1, borderColor: colors.border.subtle, borderStyle: "dashed",
            borderRadius: radius.sm, paddingVertical: 10, marginBottom: spacing.lg,
            minHeight: 44,
          }}
        >
          <Ionicons name="add-circle-outline" size={16} color={colors.accent.primary} />
          <Text style={{ ...typography.captionBold, color: colors.accent.primary }}>Add Expense</Text>
        </TouchableOpacity>
      )}
      {showAddExpense && (
        <View style={{ ...cardStyles, marginBottom: spacing.lg }}>
          <Text style={{ ...typography.bodyBold, marginBottom: spacing.md }}>New Expense</Text>
          <View style={{ gap: spacing.sm }}>
            <View>
              <Text style={{ ...typography.tiny, marginBottom: 4 }}>Amount (₹)</Text>
              <TextInput
                value={expAmount}
                onChangeText={setExpAmount}
                keyboardType="numeric"
                placeholder="0"
                placeholderTextColor={colors.text.muted}
                style={{ backgroundColor: colors.surface.input || colors.surface.elevated, borderRadius: radius.sm, padding: spacing.md, fontSize: 18, fontWeight: "700", color: colors.text.primary }}
              />
            </View>
            <View>
              <Text style={{ ...typography.tiny, marginBottom: 4 }}>Description</Text>
              <TextInput
                value={expDesc}
                onChangeText={setExpDesc}
                placeholder="e.g. Vegetables from local market"
                placeholderTextColor={colors.text.muted}
                style={{ backgroundColor: colors.surface.input || colors.surface.elevated, borderRadius: radius.sm, padding: spacing.md, fontSize: 14, color: colors.text.primary }}
              />
            </View>
            <View>
              <Text style={{ ...typography.tiny, marginBottom: 4 }}>Paid by</Text>
              <View
                style={{ flexDirection: "row", flexWrap: "wrap", gap: 6 }}
                accessibilityRole="radiogroup"
                accessibilityLabel="Who paid for this expense"
              >
                {activeMembers.map((m) => (
                  <TouchableOpacity
                    key={m.id}
                    onPress={() => setExpPaidBy(m.id)}
                    accessibilityRole="radio"
                    accessibilityState={{ selected: expPaidBy === m.id }}
                    accessibilityLabel={m.name}
                    style={{
                      paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.sm,
                      backgroundColor: expPaidBy === m.id ? colors.accent.primary : colors.surface.elevated,
                    }}
                  >
                    <Text style={{ fontSize: 13, fontWeight: "600", color: expPaidBy === m.id ? colors.text.inverse : colors.text.secondary }}>
                      {m.name}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
            <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.sm }}>
              <TouchableOpacity
                onPress={() => {
                  const amt = parseFloat(expAmount);
                  if (isNaN(amt) || amt <= 0) {
                    showAlert("Invalid", "Enter a valid amount.");
                    return;
                  }
                  const payer = activeMembers.find((m) => m.id === expPaidBy);
                  addOrderExpense({
                    amount: amt,
                    platform: expDesc.trim() || "Manual entry",
                    itemCount: 1,
                    category: "Groceries",
                    paidByMemberId: payer?.id,
                    paidByName: payer?.name,
                  });
                  haptic("success");
                  setShowAddExpense(false);
                  addNotification({ type: "order_approved", title: "Expense Added", body: `₹${amt} added by ${payer?.name || "you"}.` });
                }}
                style={{ flex: 1, backgroundColor: colors.accent.success, borderRadius: radius.sm, paddingVertical: 12, alignItems: "center" }}
              >
                <Text style={{ fontSize: 14, fontWeight: "700", color: colors.text.inverse }}>Add</Text>
              </TouchableOpacity>
              <TouchableOpacity
                onPress={() => setShowAddExpense(false)}
                style={{ flex: 1, borderWidth: 1, borderColor: colors.border.subtle, borderRadius: radius.sm, paddingVertical: 12, alignItems: "center" }}
              >
                <Text style={{ fontSize: 14, fontWeight: "600", color: colors.text.secondary }}>Cancel</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      )}

      {!isCurrentMonth ? (
        <View style={{ alignItems: "center", paddingVertical: spacing.xxxl, marginBottom: spacing.xxl }}>
          <Ionicons name="calendar-outline" size={40} color={colors.text.muted} />
          <Text style={{ ...typography.bodyBold, color: colors.text.muted, marginTop: spacing.md }}>No data for {monthLabel}</Text>
          <Text style={{ ...typography.small, color: colors.text.muted, marginTop: spacing.xs }}>Historical expense data will be available soon</Text>
        </View>
      ) : (
      <>
      <View style={{ alignItems: "center", marginBottom: spacing.xxl }}>
        <Text style={typography.display}>₹{summary.totalAmount.toLocaleString()}</Text>
        <Text style={{ ...typography.small, marginTop: 2 }}>
          {summary.orderCount} orders · ₹{perPersonAvg.toLocaleString()}/person
        </Text>
      </View>

      {/* ── Section 1: Settle Up ── */}
      <View style={{ ...cardStyles, marginBottom: spacing.lg }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, marginBottom: spacing.md }}>
          <Ionicons name="swap-horizontal" size={18} color={colors.accent.primary} />
          <Text style={typography.h3}>Settle up</Text>
        </View>

        {allSquare ? (
          <View style={{ alignItems: "center", paddingVertical: spacing.xl }}>
            <Ionicons name="checkmark-circle" size={32} color={colors.accent.success} />
            <Text style={{ ...typography.bodyBold, color: colors.accent.success, marginTop: spacing.sm }}>All square</Text>
            <Text style={{ ...typography.small, marginTop: 2 }}>No pending balances</Text>
          </View>
        ) : (
          <>
            {unsettled.map((s) => (
              <View
                key={s.fromMemberId + s.toMemberId}
                style={{
                  backgroundColor: colors.accent.dangerDim, borderRadius: radius.sm, padding: spacing.md, marginBottom: spacing.sm,
                }}
              >
                {/* Row 1: name → name · ₹ amount (full width, no buttons crowding) */}
                <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.xs, marginBottom: spacing.sm }}>
                  <Text style={{ ...typography.bodyBold, flexShrink: 1 }} numberOfLines={1}>{s.fromName}</Text>
                  <Ionicons name="arrow-forward" size={14} color={colors.accent.secondary} />
                  <Text style={{ ...typography.bodyBold, flexShrink: 1 }} numberOfLines={1}>{s.toName}</Text>
                  <Text style={{ ...typography.bodyBold, color: colors.accent.danger, marginLeft: "auto", flexShrink: 0 }}>₹{s.amount.toLocaleString()}</Text>
                </View>
                {/* Row 2: action buttons aligned right */}
                <View style={{ flexDirection: "row", gap: 8, justifyContent: "flex-end" }}>
                  <TouchableOpacity
                    onPress={() => handleSettle(s.fromMemberId, s.toMemberId, s.fromName, s.toName, s.amount)}
                    accessibilityLabel={`Mark ₹${s.amount} from ${s.fromName} to ${s.toName} as already received`}
                    style={{ borderWidth: 1, borderColor: colors.accent.success, borderRadius: radius.sm, paddingHorizontal: 12, paddingVertical: 7 }}
                  >
                    <Text style={{ fontSize: 12, fontWeight: "700", color: colors.accent.success }}>Already paid</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    onPress={() => {
                      const toMember = household?.members.find((m) => m.id === s.toMemberId);
                      const vpa = toMember?.upiId?.trim();
                      if (!vpa) {
                        // No VPA stored — most UPI apps reject `pa=` empty. Prompt the user to add it.
                        showAlert(
                          "Missing UPI ID",
                          `Bimi doesn't have a UPI ID for ${s.toName} yet. Add it under Settings → Household to enable one-tap payment.`,
                        );
                        return;
                      }
                      const upiUrl = `upi://pay?pa=${encodeURIComponent(vpa)}&pn=${encodeURIComponent(s.toName)}&am=${s.amount}&cu=INR&tn=${encodeURIComponent("Bimi settlement")}`;
                      Linking.openURL(upiUrl).catch(() => showAlert("UPI Unavailable", "No UPI app found on this device."));
                    }}
                    accessibilityLabel={`Pay ₹${s.amount} to ${s.toName} via UPI`}
                    style={{ backgroundColor: colors.accent.success, borderRadius: radius.sm, paddingHorizontal: 16, paddingVertical: 7, flexDirection: "row", alignItems: "center", gap: 6 }}
                  >
                    <Ionicons name="card" size={14} color={colors.text.inverse} />
                    <Text style={{ fontSize: 13, fontWeight: "700", color: colors.text.inverse }}>Pay via UPI</Text>
                  </TouchableOpacity>
                </View>
              </View>
            ))}
          </>
        )}

        {settled.length > 0 && (
          <>
            {settled.map((s) => (
              <View
                key={s.fromMemberId + s.toMemberId}
                style={{
                  flexDirection: "row", alignItems: "center", justifyContent: "space-between",
                  backgroundColor: colors.accent.successDim, borderRadius: radius.sm, padding: spacing.md, marginBottom: spacing.sm,
                }}
              >
                <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.xs, flex: 1, minWidth: 0 }}>
                  <Ionicons name="checkmark-circle" size={16} color={colors.accent.success} />
                  <Text style={{ ...typography.caption, color: colors.accent.success, flex: 1 }} numberOfLines={1}>{s.fromName} → {s.toName} · ₹{s.amount.toLocaleString()}</Text>
                </View>
                <TouchableOpacity
                  onPress={() => {
                    showConfirm(
                      "Undo Settlement",
                      `Mark ₹${s.amount} from ${s.fromName} → ${s.toName} as unsettled?`,
                      {
                        confirmText: "Undo",
                        destructive: true,
                        onConfirm: () => { haptic("selection"); unsettleDebt(s.fromMemberId, s.toMemberId); },
                      },
                    );
                  }}
                  hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}
                  style={{ flexDirection: "row", alignItems: "center", gap: 4, minHeight: 44, justifyContent: "center" }}
                >
                  <Ionicons name="arrow-undo" size={14} color={colors.text.muted} />
                  <Text style={{ ...typography.tiny, color: colors.text.muted }}>Undo</Text>
                </TouchableOpacity>
              </View>
            ))}
          </>
        )}

        {/* P3: Push to Splitwise — copy + open app deep link + share fallback */}
        <TouchableOpacity
          onPress={handlePushToSplitwise}
          accessibilityLabel="Push this month's ledger to Splitwise. Opens the Splitwise app or shares the summary."
          style={{
            flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm,
            borderWidth: 1, borderColor: colors.accent.success, borderRadius: radius.sm,
            paddingVertical: spacing.md, marginTop: spacing.sm,
            backgroundColor: copiedSplitwise ? colors.accent.successDim : "transparent",
          }}
        >
          <Ionicons
            name={copiedSplitwise ? "checkmark" : "share-outline"}
            size={16}
            color={colors.accent.success}
          />
          <Text style={{ ...typography.captionBold, color: colors.accent.success }}>
            {copiedSplitwise ? "Opened Splitwise · ledger copied" : "Push to Splitwise"}
          </Text>
        </TouchableOpacity>
      </View>

      {/* ── Section 2: Who Paid What ── */}
      <View style={{ ...cardStyles, marginBottom: spacing.lg }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, marginBottom: spacing.md }}>
          <Ionicons name="people" size={18} color={colors.accent.primary} />
          <Text style={typography.h3}>Who paid what</Text>
        </View>

        {summary.perPerson.length === 0 && (
          <View style={{ alignItems: "center", paddingVertical: spacing.xl }}>
            <Ionicons name="people-outline" size={32} color={colors.text.muted} />
            <Text style={{ ...typography.caption, color: colors.text.muted, marginTop: spacing.sm }}>No expense data yet</Text>
          </View>
        )}

        {summary.perPerson.map((p, index) => {
          const member = activeMembers.find((m) => m.id === p.memberId);
          const isExpanded = expandedPerson === p.memberId;
          const balanceColor = p.balance >= 0 ? colors.accent.success : colors.accent.danger;
          const balanceLabel = p.balance >= 0 ? `+₹${p.balance.toLocaleString()}` : `-₹${Math.abs(p.balance).toLocaleString()}`;
          const balanceTag = p.balance >= 0 ? "gets back" : "owes";

          return (
            <Animated.View key={p.memberId} entering={reducedMotion ? undefined : FadeInLeft.delay(index * staggerDelay).springify()}>
            <TouchableOpacity
              activeOpacity={0.7}
              onPress={() => togglePerson(p.memberId)}
              style={{
                ...listRowStyles,
                ...(isExpanded ? { backgroundColor: colors.surface.elevated, borderRadius: radius.sm, paddingHorizontal: spacing.md, borderBottomWidth: 0 } : {}),
              }}
            >
              <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
                  <Ionicons name="person-circle" size={24} color={colors.text.secondary} />
                  <Text style={typography.bodyBold}>{p.memberName}</Text>
                </View>
                <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.xs }}>
                  <Text style={{ ...typography.bodyBold, color: balanceColor }}>{balanceLabel}</Text>
                  <Text style={{ ...typography.tiny, color: balanceColor }}>{balanceTag}</Text>
                  <Ionicons name={isExpanded ? "chevron-up" : "chevron-down"} size={14} color={colors.text.muted} style={{ marginLeft: 2 }} />
                </View>
              </View>

              {isExpanded && (
                <View style={{ flexDirection: "row", gap: spacing.lg, marginTop: spacing.md, paddingTop: spacing.md, borderTopWidth: 1, borderTopColor: colors.border.subtle }}>
                  <View>
                    <Text style={typography.tiny}>Paid</Text>
                    <Text style={{ ...typography.bodyBold, marginTop: 2 }}>₹{p.totalPaid.toLocaleString()}</Text>
                  </View>
                  <View>
                    <Text style={typography.tiny}>Fair share</Text>
                    <Text style={{ ...typography.bodyBold, marginTop: 2 }}>₹{p.share.toLocaleString()}</Text>
                  </View>
                  <View>
                    <Text style={typography.tiny}>Balance</Text>
                    <Text style={{ ...typography.bodyBold, color: balanceColor, marginTop: 2 }}>{balanceLabel}</Text>
                  </View>
                </View>
              )}
            </TouchableOpacity>
            </Animated.View>
          );
        })}
      </View>

      {/* ── Section 3: Activity ── */}
      {summary.activities.length > 0 && (
        <View style={{ ...cardStyles, marginBottom: spacing.lg }}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, marginBottom: spacing.md }}>
            <Ionicons name="time" size={18} color={colors.accent.primary} />
            <Text style={typography.h3}>Activity</Text>
          </View>

          {visibleActivities.map((act) => (
            <View
              key={act.id}
              style={{ flexDirection: "row", alignItems: "center", gap: spacing.md, paddingVertical: spacing.sm }}
            >
              <View style={{
                width: 32, height: 32, borderRadius: 16, alignItems: "center", justifyContent: "center",
                backgroundColor: act.type === "settlement" ? colors.accent.successDim : colors.accent.infoDim,
              }}>
                <Ionicons
                  name={act.type === "settlement" ? "checkmark" : "cart"}
                  size={16}
                  color={act.type === "settlement" ? colors.accent.success : colors.accent.info}
                />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={typography.caption} numberOfLines={1}>
                  {act.description}
                  {act.involvedMembers.length > 0 && (
                    <Text style={typography.captionBold}> · {act.involvedMembers[0]}</Text>
                  )}
                </Text>
                <Text style={typography.tiny}>{timeAgo(act.timestamp)}</Text>
              </View>
              <Text style={{ ...typography.smallBold, color: act.type === "settlement" ? colors.accent.success : colors.text.primary }}>
                {act.type === "settlement" ? "−" : ""}₹{act.amount.toLocaleString()}
              </Text>
            </View>
          ))}

          {summary.activities.length > 3 && (
            <TouchableOpacity
              onPress={() => {
                if (!reducedMotion) LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
                setShowAllActivity((p) => !p);
              }}
              style={{ alignItems: "center", paddingTop: spacing.md }}
            >
              <Text style={{ ...typography.captionBold, color: colors.accent.primary }}>
                {showAllActivity ? "Show less" : `Show all ${summary.activities.length} entries`}
              </Text>
            </TouchableOpacity>
          )}
        </View>
      )}

      {/* ── Section 4: Spending Breakdown (Collapsed) ── */}
      <View style={{ ...cardStyles, marginBottom: spacing.lg }}>
        <TouchableOpacity
          activeOpacity={0.7}
          onPress={() => {
            if (!reducedMotion) LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
            setShowCategories((p) => !p);
          }}
          style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}
        >
          <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
            <Ionicons name="pie-chart" size={18} color={colors.accent.primary} />
            <Text style={typography.h3}>Spending</Text>
            <Text style={typography.caption}>{summary.categories.length} categories</Text>
          </View>
          <Ionicons name={showCategories ? "chevron-up" : "chevron-down"} size={18} color={colors.text.muted} />
        </TouchableOpacity>

        {showCategories && (
          <View style={{ marginTop: spacing.lg }}>
            {summary.categories.map((cat) => (
              <View key={cat.name} style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, marginBottom: spacing.md }}>
                <View style={{ width: 22, alignItems: "center" }}>
                  <Ionicons name="ellipse" size={10} color={CATEGORY_ACCENT[cat.name] || colors.text.muted} />
                </View>
                <Text style={{ ...typography.small, width: 72, color: colors.text.primary }}>{cat.name}</Text>
                <View style={{ flex: 1, height: 6, backgroundColor: colors.surface.elevated, borderRadius: 3, overflow: "hidden" }}>
                  <View style={{
                    width: `${(cat.amount / maxCategoryAmount) * 100}%`,
                    height: "100%", backgroundColor: CATEGORY_ACCENT[cat.name] || colors.text.muted, borderRadius: 3,
                  }} />
                </View>
                <Text style={{ ...typography.smallBold, width: 56, textAlign: "right", color: colors.text.primary }}>₹{cat.amount.toLocaleString()}</Text>
              </View>
            ))}
          </View>
        )}
      </View>
      </>
      )}
    </ScrollView>
    </GradientScreen>
  );
}
