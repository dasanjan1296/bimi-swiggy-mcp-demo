/**
 * TodaysPlanDrawer — quiet expandable list of today + tomorrow meal
 * plans. Each row narrates the slot's status (Eaten / Cooking / Voted
 * / Pick a meal).
 *
 * STATUS: not currently rendered on the home tab. The home centerpiece
 * is `<HomeCalendar>` (a vertical agenda of days). This drawer is
 * preserved as a pattern for any future surface that wants a
 * compressed today + tomorrow expression (e.g., a focused weekday
 * detail screen, a settings preview, etc).
 *
 * Honors the design principles when used:
 *   #1 (one question per session)  — collapsed by default; the hero is
 *      still the only decision moment.
 *   #4 (today before tomorrow)     — Today section renders first, with
 *      the "now" meal highlighted; Tomorrow section follows.
 *   #5 (Bimi acts; Bimi narrates)  — past meals show their final
 *      status; current meals show "Cooking now"; future meals show
 *      their voted-or-pending state. No ambiguity.
 *   #7 (density emerges from absence) — a single tap target by default;
 *      generous whitespace when expanded.
 *
 * Reads from the meal store and deep-links into voting (for unfinished
 * tomorrow slots) and into the meal-calendar route (for the broader
 * weekly view).
 */

import React, { useCallback, useMemo, useState } from "react";
import {
  LayoutAnimation,
  Platform,
  Text,
  UIManager,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { router } from "expo-router";
import { useMealStore } from "@/lib/store";
import { useIsCookOffTomorrow } from "@/lib/context-hooks";
import { RipplePressable } from "../RipplePressable";
import { Pill, StatusChip } from "../ui";
import {
  colors,
  iconSize,
  radius,
  spacing,
  typography,
} from "@/lib/theme";
import type { MealPlan, MealType } from "@/lib/types";

if (Platform.OS === "android" && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

const MEAL_ORDER: Record<MealType, number> = {
  breakfast: 0,
  lunch: 1,
  dinner: 2,
  snack: 3,
};

const MEAL_LABEL: Record<MealType, string> = {
  breakfast: "Breakfast",
  lunch: "Lunch",
  dinner: "Dinner",
  snack: "Snack",
};

const MEAL_ICON: Record<MealType, keyof typeof Ionicons.glyphMap> = {
  breakfast: "sunny-outline",
  lunch: "restaurant-outline",
  dinner: "moon-outline",
  snack: "cafe-outline",
};

// Map MealPlan.status → tone for the "now" / "past" indicator.
function statusBadge(plan: MealPlan, when: "past" | "now" | "future") {
  if (when === "now" && plan.status === "cooking") {
    return <StatusChip status="cooking" size="xs" />;
  }
  if (when === "past" && plan.status === "cooked") {
    return <StatusChip status="delivered" size="xs" label="Eaten" />;
  }
  if (when === "future" && plan.selectedMeal) {
    return <StatusChip status="approved" size="xs" label="Voted" />;
  }
  return null;
}

function getMealWhen(mealType: MealType): "past" | "now" | "future" {
  const hour = new Date().getHours();
  // Boundaries match getMealTimeState in the legacy home screen so a
  // user transitioning between drawer and hero sees consistent state.
  const boundaries: Record<string, [number, number]> = {
    breakfast: [5, 11],
    lunch: [10, 16],
    dinner: [15, 23],
  };
  const [start, end] = boundaries[mealType] ?? [0, 24];
  if (hour >= end) return "past";
  if (hour >= start) return "now";
  return "future";
}

function sortByMeal(plans: MealPlan[]): MealPlan[] {
  return [...plans].sort(
    (a, b) => (MEAL_ORDER[a.mealType] ?? 4) - (MEAL_ORDER[b.mealType] ?? 4),
  );
}

export interface TodaysPlanDrawerProps {
  /** Optional override for whether the drawer is forced open. Useful
   *  for tests / first-run onboarding that wants to expand by default. */
  defaultExpanded?: boolean;
}

export function TodaysPlanDrawer({ defaultExpanded = false }: TodaysPlanDrawerProps) {
  const todaysPlans = useMealStore((s) => s.todaysPlans);
  const tomorrowsPlans = useMealStore((s) => s.tomorrowsPlans);
  const setActiveMealType = useMealStore((s) => s.setActiveMealType);
  const isTomorrowCookOff = useIsCookOffTomorrow();

  const [expanded, setExpanded] = useState(defaultExpanded);

  const todaysSorted = useMemo(() => sortByMeal(todaysPlans), [todaysPlans]);
  const tomorrowsSorted = useMemo(() => sortByMeal(tomorrowsPlans), [tomorrowsPlans]);

  // The compact summary that always shows in the collapsed state. Picks
  // the most relevant meal per "today" + "tomorrow" so the user knows
  // at a glance whether to expand. Format: "Lunch · Rajma chawal".
  const compactToday = useMemo(() => {
    const now = todaysSorted.find((p) => getMealWhen(p.mealType) === "now");
    if (now?.selectedMeal) return `${MEAL_LABEL[now.mealType]} · ${now.selectedMeal}`;
    const next = todaysSorted.find((p) => getMealWhen(p.mealType) === "future" && p.selectedMeal);
    if (next?.selectedMeal) return `Next · ${next.selectedMeal}`;
    return null;
  }, [todaysSorted]);

  const tomorrowVotedCount = useMemo(
    () => tomorrowsSorted.filter((p) => !!p.selectedMeal).length,
    [tomorrowsSorted],
  );

  const toggle = useCallback(() => {
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    setExpanded((e) => !e);
  }, []);

  // 2026-05-03 audit: the voting tab is gone — folded into Today per
  // redesign §7. Tomorrow rows used to be tappable to jump into the
  // voting picker for that meal type. Until the inline picker is built,
  // the rows render in informational-only mode (no onPress).
  void setActiveMealType;
  const goToVoting = undefined;

  // Hide the drawer entirely if there's nothing to show — keeps day-1
  // households' home as quiet as possible.
  if (todaysPlans.length === 0 && tomorrowsPlans.length === 0) {
    return null;
  }

  return (
    <View
      style={{
        marginTop: spacing.lg,
        borderRadius: radius.lg,
        backgroundColor: colors.surface.card,
        overflow: "hidden",
      }}
    >
      <RipplePressable
        onPress={toggle}
        haptic="selection"
        accessibilityRole="button"
        accessibilityLabel={expanded ? "Hide today's plan" : "Show today's plan"}
        accessibilityState={{ expanded }}
        style={{
          flexDirection: "row",
          alignItems: "center",
          paddingVertical: spacing.md,
          paddingHorizontal: spacing.lg,
          gap: spacing.sm,
        }}
      >
        <Ionicons
          name="calendar-outline"
          size={iconSize.sm}
          color={colors.text.secondary}
        />
        <View style={{ flex: 1 }}>
          <Text style={typography.bodyBold}>
            {expanded ? "Today's plan" : compactToday ?? "Today's plan"}
          </Text>
          {!expanded && (
            <Text style={typography.tiny}>
              {tomorrowVotedCount > 0
                ? `Tomorrow: ${tomorrowVotedCount} of ${tomorrowsSorted.length} sorted`
                : "Tap to plan tomorrow"}
            </Text>
          )}
        </View>
        <Ionicons
          name={expanded ? "chevron-up" : "chevron-down"}
          size={iconSize.sm}
          color={colors.text.muted}
        />
      </RipplePressable>

      {expanded && (
        <View style={{ paddingHorizontal: spacing.lg, paddingBottom: spacing.lg, gap: spacing.lg }}>
          <PlanSection
            label="Today"
            plans={todaysSorted}
            kind="today"
          />
          {/* Tomorrow section — hide when the cook is off; the absence
              flow surfaces tomorrow's coordination separately. */}
          {!isTomorrowCookOff && (
            <PlanSection
              label="Tomorrow"
              plans={tomorrowsSorted}
              kind="tomorrow"
              onPickMeal={goToVoting}
            />
          )}
        </View>
      )}
    </View>
  );
}

function PlanSection({
  label,
  plans,
  kind,
  onPickMeal,
}: {
  label: string;
  plans: MealPlan[];
  kind: "today" | "tomorrow";
  onPickMeal?: (mealType: MealType) => void;
}) {
  return (
    <View style={{ gap: spacing.sm }}>
      <Text
        style={{
          ...typography.smallBold,
          color: colors.text.muted,
          textTransform: "uppercase",
          letterSpacing: 0.8,
        }}
      >
        {label}
      </Text>
      <View
        style={{
          backgroundColor: colors.surface.base,
          borderRadius: radius.md,
          overflow: "hidden",
        }}
      >
        {plans.map((plan, idx) => {
          const when = kind === "today" ? getMealWhen(plan.mealType) : "future";
          const isLast = idx === plans.length - 1;
          const finalised = !!plan.selectedMeal;
          const isPast = kind === "today" && when === "past";

          // Pressable behaviour:
          //   - Today's past/now meals: not pressable (informational).
          //   - Today's future meals (not yet started): inert too.
          //   - Tomorrow with no selectedMeal: tap to vote.
          //   - Tomorrow with selectedMeal: tap to re-vote / change.
          const onPress = kind === "tomorrow"
            ? () => onPickMeal?.(plan.mealType)
            : undefined;

          const Wrapper = onPress ? RipplePressable : View;

          return (
            <Wrapper
              key={plan.id}
              {...(onPress ? { onPress, haptic: "selection" as const, accessibilityRole: "button" as const, accessibilityLabel: `${MEAL_LABEL[plan.mealType]}: ${plan.selectedMeal ?? "Pick a meal"}` } : {})}
              style={{
                flexDirection: "row",
                alignItems: "center",
                paddingVertical: spacing.md,
                paddingHorizontal: spacing.md,
                gap: spacing.md,
                borderBottomWidth: isLast ? 0 : 1,
                borderBottomColor: colors.divider.default,
                opacity: isPast && !finalised ? 0.5 : 1,
              }}
            >
              <Ionicons
                name={MEAL_ICON[plan.mealType]}
                size={iconSize.md}
                color={colors.text.secondary}
              />
              <View style={{ flex: 1 }}>
                <Text
                  style={{
                    ...typography.smallBold,
                    color: colors.text.muted,
                    textTransform: "uppercase",
                    letterSpacing: 0.5,
                  }}
                >
                  {MEAL_LABEL[plan.mealType]}
                </Text>
                <Text
                  style={{
                    ...typography.bodyBold,
                    color: finalised ? colors.text.primary : colors.text.secondary,
                    marginTop: 1,
                  }}
                  numberOfLines={1}
                >
                  {plan.selectedMeal ?? (kind === "tomorrow" ? "Pick a meal" : "—")}
                </Text>
              </View>
              {kind === "today" ? (
                statusBadge(plan, when)
              ) : finalised ? (
                <StatusChip status="approved" size="xs" label="Voted" />
              ) : (
                <Pill tone="primary" size="xs">
                  Pick
                </Pill>
              )}
              {kind === "tomorrow" && (
                <Ionicons
                  name="chevron-forward"
                  size={iconSize.xs}
                  color={colors.text.muted}
                />
              )}
            </Wrapper>
          );
        })}
      </View>
    </View>
  );
}
