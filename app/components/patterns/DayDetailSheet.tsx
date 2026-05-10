/**
 * DayDetailSheet — the unified bottom sheet opened from any day card
 * in the home calendar. ONE BottomSheet shell, branched body based on
 * the day's state:
 *
 *   • past         → `<PastDayBody>` (read-only votes + ratings + notes)
 *   • today        → `<DayVotingBody>` for change-vote affordances,
 *                    plus a "Rate today's meals" CTA when any meal is
 *                    in its post-eat window. Tapping the CTA closes
 *                    this sheet and asks the parent (HomeCalendar) to
 *                    open `<RateMealSheet>` (avoids nested sheets).
 *   • tomorrow /
 *     near-future  → `<DayVotingBody>` (full vote-on-anything flow)
 *   • far-future   → empty-state copy: "Bimi will plan when closer"
 *
 * Cook-off context renders inside the appropriate body (DayVotingBody
 * already has the canonical CookOffBanner — we don't duplicate it on
 * past or far-future days).
 */

import React from "react";
import { Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { Button } from "../ui/Button";
import { BottomSheet } from "../ui/BottomSheet";
import {
  colors,
  iconSize,
  radius,
  spacing,
  typography,
} from "@/lib/theme";
import type { MealType } from "@/lib/types";
import type { DayCookOff } from "@/lib/use-week-meal-plans";
import {
  DayVotingBody,
  CookOffBanner,
} from "./DayMealSheet";
import { PastDayBody, formatDateLong, composeCookSummary } from "./PastDayDetailSheet";
import type { CalendarDay } from "./home-calendar-types";

export interface DayDetailSheetProps {
  visible: boolean;
  onClose: () => void;
  /** Day to render. Pass null when closed. */
  day: CalendarDay | null;
  /**
   * Open the rating sheet for this day's past-time-window meals. The
   * parent (HomeCalendar) should close THIS sheet first, then mount
   * `<RateMealSheet>` — bottom sheets do not nest cleanly.
   */
  onOpenRate?: (date: string) => void;
  /**
   * Open the recipe browser for a cook-off day. Same flow constraint:
   * close this sheet, then open `<SelfCookSheet>`. The CookOffBanner
   * inside DayVotingBody also commits the `self_cook` fallback before
   * calling this, so the absence is resolved on intent.
   */
  onOpenSelfCookIdeas?: (cookOff: DayCookOff) => void;
}

export function DayDetailSheet({
  visible,
  onClose,
  day,
  onOpenRate,
  onOpenSelfCookIdeas,
}: DayDetailSheetProps) {
  if (!day) return null;

  const title = formatDateLong(day.date);
  const subtitle = composeSubtitle(day);

  return (
    <BottomSheet
      visible={visible}
      onClose={onClose}
      title={title}
      subtitle={subtitle}
      maxHeightFraction={0.9}
      scrollable
    >
      {renderBody(day, { onClose, onOpenRate, onOpenSelfCookIdeas })}
    </BottomSheet>
  );
}

// ── Branching body renderer ─────────────────────────────────────────

function renderBody(
  day: CalendarDay,
  ctx: {
    onClose: () => void;
    onOpenRate?: (date: string) => void;
    onOpenSelfCookIdeas?: (cookOff: DayCookOff) => void;
  },
) {
  // Past day → read-only history. Cook-off banner (read-only, no
  // resolve action — the day is already over) sits at the top so the
  // user knows the cook situation before reading the meal sections.
  if (day.state === "past") {
    return (
      <View style={{ gap: spacing.md }}>
        {day.cookOff ? (
          <PastCookOffBanner cookOff={day.cookOff} />
        ) : null}
        <PastDayBody date={day.date} entries={day.pastEntries ?? []} />
      </View>
    );
  }

  // Far future → no plans yet. Quiet empty state with one calm CTA so
  // the user understands the absence isn't a bug.
  if (day.state === "far-future") {
    return <FarFutureBody />;
  }

  // Today / tomorrow / near-future → vote rows. The CookOffBanner is
  // rendered by DayVotingBody itself (with its actionable Self-cook
  // CTA), so we don't pre-pend one here.
  if (!day.weekDay) {
    // Defensive — shouldn't happen given the build pipeline always
    // attaches a WeekDay for today/tomorrow/near-future.
    return <FarFutureBody />;
  }

  const showRateButton =
    day.state === "today" && hasPastTimeMeal(day.weekDay);

  return (
    <View style={{ gap: spacing.lg }}>
      <DayVotingBody
        day={day.weekDay}
        onOpenSelfCookIdeas={(cookOff) => {
          // Close this sheet, then bubble up — the parent opens
          // `<SelfCookSheet>` from the now-empty sheet slot.
          ctx.onClose();
          ctx.onOpenSelfCookIdeas?.(cookOff);
        }}
      />

      {showRateButton ? (
        <Button
          variant="secondary"
          size="md"
          onPress={() => {
            ctx.onClose();
            ctx.onOpenRate?.(day.date);
          }}
          fullWidth
          leadingIcon="star-outline"
        >
          Rate today's meals
        </Button>
      ) : null}
    </View>
  );
}

// ── Past-day cook-off banner ────────────────────────────────────────
// Read-only — the absence is in the past, so there's no fallback to
// resolve. We just show what happened (calmer green if a fallback was
// chosen at the time, neutral grey otherwise).

function PastCookOffBanner({ cookOff }: { cookOff: NonNullable<CalendarDay["cookOff"]> }) {
  const isResolved = !!cookOff.fallbackChosen;
  return (
    <View
      style={{
        backgroundColor: isResolved
          ? colors.accent.successDim
          : colors.surface.card,
        borderRadius: radius.md,
        borderWidth: 1,
        borderColor: isResolved
          ? colors.accent.success
          : colors.border.subtle,
        padding: spacing.md,
        flexDirection: "row",
        alignItems: "center",
        gap: spacing.sm,
      }}
    >
      <Ionicons
        name={isResolved ? "checkmark-circle" : "information-circle-outline"}
        size={iconSize.sm}
        color={isResolved ? colors.accent.success : colors.text.secondary}
      />
      <Text
        style={{
          ...typography.caption,
          color: isResolved ? colors.accent.success : colors.text.secondary,
          flex: 1,
        }}
      >
        {composeCookSummary(cookOff.absence)}
      </Text>
    </View>
  );
}

// ── Far-future body ────────────────────────────────────────────────

function FarFutureBody() {
  return (
    <View
      style={{
        alignItems: "center",
        paddingVertical: spacing.xxl,
        gap: spacing.sm,
      }}
    >
      <Ionicons
        name="time-outline"
        size={iconSize.xl}
        color={colors.text.muted}
      />
      <Text
        style={{
          ...typography.bodyBold,
          color: colors.text.primary,
          textAlign: "center",
        }}
      >
        Bimi will plan this closer to the day
      </Text>
      <Text
        style={{
          ...typography.caption,
          color: colors.text.secondary,
          textAlign: "center",
          maxWidth: 260,
        }}
      >
        Suggestions and voting open about a week ahead, when fresh
        preferences are most useful to the cook.
      </Text>
    </View>
  );
}

// ── Helpers ─────────────────────────────────────────────────────────

function composeSubtitle(day: CalendarDay): string | undefined {
  if (day.state === "today") {
    if (day.cookOff) return composeCookSummaryShort(day.cookOff);
    if (day.weekDay) {
      if (day.weekDay.voted === day.weekDay.total)
        return "All meals set. Tap any to change.";
      return `${day.weekDay.voted} of ${day.weekDay.total} sorted`;
    }
    return undefined;
  }
  if (day.state === "tomorrow") {
    if (day.cookOff) return composeCookSummaryShort(day.cookOff);
    if (day.weekDay)
      return `Tomorrow · ${day.weekDay.voted} of ${day.weekDay.total} sorted`;
    return "Tomorrow";
  }
  if (day.state === "near-future") {
    if (day.cookOff) return composeCookSummaryShort(day.cookOff);
    return day.relativeLabel
      ? `${day.relativeLabel} · tap a meal to vote`
      : "Vote ahead";
  }
  if (day.state === "past") {
    return composeCookSummary(day.cookOff?.absence ?? null);
  }
  if (day.state === "far-future") {
    return day.relativeLabel ?? "Coming up";
  }
  return undefined;
}

function composeCookSummaryShort(cookOff: NonNullable<CalendarDay["cookOff"]>): string {
  const cookFirst =
    cookOff.absence.cookName.split(" ")[0] || cookOff.absence.cookName;
  if (cookOff.fallbackChosen === "self_cook")
    return `${cookFirst} off — self-cooking`;
  if (cookOff.fallbackChosen === "order_food")
    return `${cookFirst} off — ordering in`;
  if (cookOff.fallbackChosen)
    return `${cookFirst} off — plan in place`;
  return cookOff.isFullDay
    ? `${cookFirst} off all day`
    : `${cookFirst} off — needs a plan`;
}

const MEAL_BOUNDARIES: Record<MealType, [number, number]> = {
  breakfast: [5, 11],
  lunch: [10, 16],
  dinner: [15, 23],
  snack: [0, 24],
};

function hasPastTimeMeal(weekDay: NonNullable<CalendarDay["weekDay"]>): boolean {
  const hour = new Date().getHours();
  return weekDay.plans.some((p) => {
    const [, end] = MEAL_BOUNDARIES[p.mealType];
    // A meal is "past-time" if its eat window has ended AND we have a
    // selected dish (something to rate).
    return hour >= end && !!p.selectedMeal;
  });
}
