/**
 * DayCardRow — one full-width day card in the home calendar agenda.
 *
 * Renders a "very big cell" with previewable details for the day:
 *   • Left rail: large day-of-month numeral + weekday short ("9 / SAT").
 *   • Top eyebrow chip: "TODAY" / "Tomorrow" / "Yesterday" or relative
 *     date — only when meaningful, never noise.
 *   • Three meal mini-rows (breakfast / lunch / dinner): icon · meal
 *     label · selected dish (or em-dash) · per-meal status chip.
 *   • Cook-off banner (single line) if absence overlaps this day.
 *   • Right edge master status chip ("All set" / "2 left" / "Cook off"
 *     / "Rated" / "—") — the one-glance state.
 *
 * Three visual densities by `state`:
 *   • "today"             — hero card, accent border, primaryDim wash.
 *   • "tomorrow"          — elevated white card, hairline border.
 *   • "near-future" / "past-with-data" — plain card, hairline border.
 *   • "past-empty" / "far-future" — collapsed line (date + dim "—" so
 *     the timeline reads continuous without claiming attention).
 *
 * The card is fully tappable end-to-end. The parent (HomeCalendar)
 * supplies onPress to open the day-detail sheet.
 */

import React, { useMemo } from "react";
import { Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { RipplePressable } from "../RipplePressable";
import { CookOffPill } from "../ui/CookOffPill";
import {
  colors,
  elevation,
  radius,
  spacing,
  typography,
} from "@/lib/theme";
import type { MealType } from "@/lib/types";
import { classifyMealState } from "@/lib/meal-state";
import type { CalendarDay, MealPreview } from "./home-calendar-types";

const MEAL_ORDER: MealType[] = ["breakfast", "lunch", "dinner"];

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

export interface DayCardRowProps {
  day: CalendarDay;
  onPress: () => void;
}

export function DayCardRow({ day, onPress }: DayCardRowProps) {
  const isToday = day.state === "today";
  const isTomorrow = day.state === "tomorrow";
  const isPast = day.state === "past";
  const isFarFuture = day.state === "far-future";

  // Past-empty + far-future render as a quiet, collapsed line so the
  // calendar reads continuous (no jarring height jumps) but doesn't
  // claim attention.
  const isCollapsed =
    (isPast && !day.hasData) || isFarFuture;

  const previews = useMemo(() => buildMealPreviews(day), [day]);

  const eyebrow = isToday
    ? "TODAY"
    : isTomorrow
    ? "TOMORROW"
    : day.state === "past" && day.relativeLabel
    ? day.relativeLabel.toUpperCase()
    : null;

  // Master status chip on the right edge — one-glance state.
  const masterStatus = computeMasterStatus(day);

  if (isCollapsed) {
    return (
      <RipplePressable
        onPress={onPress}
        haptic="selection"
        accessibilityRole="button"
        accessibilityLabel={composeA11yLabel(day, masterStatus, previews)}
        style={collapsedOuterStyle}
      >
        <View style={collapsedInnerStyle}>
          <Text style={collapsedDateStyle} numberOfLines={1}>
            {day.weekdayShort} · {day.dayOfMonth}
          </Text>
          <Text style={collapsedHintStyle} numberOfLines={1}>
            {isFarFuture ? "Bimi will plan when closer" : "—"}
          </Text>
        </View>
      </RipplePressable>
    );
  }

  // Outer chrome — splits sizing+border from inner padding so the
  // tappable surface fills the whole card without dead-zone padding
  // around the border (mirrors the meals-history cell pattern).
  const outerStyle = {
    borderRadius: radius.lg,
    backgroundColor: isToday ? colors.accent.primaryDim : colors.surface.elevated,
    borderWidth: isToday ? 1.5 : 1,
    borderColor: isToday ? colors.accent.primary : colors.border.subtle,
    overflow: "hidden" as const,
    ...(isToday || isTomorrow ? elevation.low : {}),
  };

  return (
    <RipplePressable
      onPress={onPress}
      haptic="selection"
      accessibilityRole="button"
      accessibilityLabel={composeA11yLabel(day, masterStatus, previews)}
      style={outerStyle}
    >
      <View
        style={{
          flexDirection: "row",
          padding: spacing.md,
          gap: spacing.md,
        }}
      >
        {/* Left rail — date numeral + weekday short. Anchored to the
            top so multi-line content on the right stays aligned. */}
        <View style={{ alignItems: "center", minWidth: 44, paddingTop: 2 }}>
          <Text
            style={{
              ...typography.h1,
              fontSize: 30,
              lineHeight: 32,
              color: isToday ? colors.accent.primary : colors.text.primary,
              letterSpacing: -0.5,
            }}
          >
            {day.dayOfMonth}
          </Text>
          <Text
            style={{
              ...typography.tinyBold,
              color: isToday ? colors.accent.primary : colors.text.muted,
              textTransform: "uppercase",
              letterSpacing: 0.8,
              marginTop: 2,
            }}
          >
            {day.weekdayShort}
          </Text>
        </View>

        {/* Right column — eyebrow + meal previews + cook-off line. */}
        <View style={{ flex: 1, gap: spacing.sm }}>
          {/* Eyebrow row — TODAY / TOMORROW / "yesterday" + master
              status chip on the right edge. */}
          <View
            style={{
              flexDirection: "row",
              alignItems: "center",
              justifyContent: "space-between",
              gap: spacing.sm,
            }}
          >
            <View style={{ flex: 1 }}>
              {eyebrow ? (
                <Text
                  style={{
                    ...typography.tinyBold,
                    color: isToday
                      ? colors.accent.primary
                      : colors.text.muted,
                    letterSpacing: 1.2,
                  }}
                >
                  {eyebrow}
                </Text>
              ) : null}
              <Text
                style={{
                  ...typography.bodyBold,
                  color: colors.text.primary,
                  marginTop: eyebrow ? 1 : 0,
                }}
                numberOfLines={1}
              >
                {day.dayLong}
              </Text>
            </View>
            {masterStatus ? (
              <MasterStatusBadge status={masterStatus} isToday={isToday} />
            ) : null}
          </View>

          {/* Meal preview rows — three lines, one per meal. */}
          <View style={{ gap: spacing.xs + 2 }}>
            {previews.map((p) => (
              <MealPreviewRow key={p.mealType} preview={p} />
            ))}
          </View>

          {/* Cook-off line — single sentence with the canonical OFF
              pill plus a tiny verb if a fallback was chosen. */}
          {day.cookOff ? (
            <View
              style={{
                flexDirection: "row",
                alignItems: "center",
                gap: spacing.xs,
                marginTop: 2,
              }}
            >
              <CookOffPill
                size="sm"
                resolved={!!day.cookOff.fallbackChosen}
              />
              <Text
                style={{
                  ...typography.tiny,
                  color: day.cookOff.fallbackChosen
                    ? colors.text.secondary
                    : colors.accent.warning,
                  flex: 1,
                }}
                numberOfLines={1}
              >
                {composeCookOffLine(day.cookOff)}
              </Text>
            </View>
          ) : null}
        </View>
      </View>
    </RipplePressable>
  );
}

// ── Per-meal preview row ────────────────────────────────────────────

function MealPreviewRow({ preview }: { preview: MealPreview }) {
  const { mealType, selectedMeal, status, voteTally } = preview;
  const hasMeal = !!selectedMeal;
  // In cook-off rows the dish name is historical context (what was
  // voted before the cook went off) rather than the active plan, so
  // we tone it down — same treatment the day-detail modal applies.
  const isOff = status === "off" || status === "self-cook";
  // Tentative dish is a "soft pick" — household can still switch.
  // Render in regular (non-bold) weight so it doesn't read as final.
  const isTentative = status === "tentative";

  return (
    <View
      style={{
        flexDirection: "row",
        alignItems: "center",
        gap: spacing.sm,
      }}
    >
      <Ionicons
        name={MEAL_ICON[mealType]}
        size={14}
        color={colors.text.muted}
      />
      <Text
        style={{
          ...typography.small,
          color: colors.text.muted,
          width: 56,
        }}
      >
        {MEAL_LABEL[mealType]}
      </Text>
      <Text
        style={{
          ...typography.small,
          color: isOff
            ? colors.text.secondary
            : hasMeal
            ? colors.text.primary
            : colors.text.muted,
          flex: 1,
          fontWeight:
            isOff || isTentative ? "400" : hasMeal ? "600" : "400",
          fontStyle: isOff && hasMeal ? "italic" : "normal",
        }}
        numberOfLines={1}
      >
        {selectedMeal ?? "—"}
      </Text>
      <MealStatusDot status={status} voteTally={voteTally} />
    </View>
  );
}

/**
 * Tiny status indicator at the right edge of a meal row. Renders the
 * lifecycle state computed by `classifyMealState`, mapped to the
 * household's mental model:
 *
 *   locked     → green dot + "locked"   — system has decided
 *   tentative  → amber dot + "tentative" — winner picked but mutable
 *   voting     → grey dot + "1/3"       — votes coming in, no winner
 *   open       → no chip                 — nothing happening yet
 *   rated      → amber star + "rated"
 *   off        → amber dot + "off"       (cook absent, no fallback)
 *   self-cook  → amber dot + "self-cook" (cook absent, household cooks)
 *   skipped    → muted dot + "skipped"   (past, nothing recorded)
 *
 * Replaces a previous "voted" green chip that conflated three distinct
 * states ("vote cast" / "winner picked" / "locked in") and made the
 * household ask "is this the system's choice or just one person's?".
 */
function MealStatusDot({
  status,
  voteTally,
}: {
  status: MealPreview["status"];
  voteTally?: MealPreview["voteTally"];
}) {
  if (status === "open" || status === "pending") return null;

  // ── Color ──────────────────────────────────────────────────────
  const color = (() => {
    if (status === "locked" || status === "voted") return colors.accent.success;
    if (status === "tentative") return colors.accent.warning;
    if (status === "rated") return colors.accent.warning;
    if (status === "off" || status === "self-cook") return colors.accent.warning;
    if (status === "voting") return colors.text.secondary;
    return colors.text.muted; // "skipped"
  })();

  // ── Label ──────────────────────────────────────────────────────
  const label = (() => {
    if (status === "locked" || status === "voted") return "locked";
    if (status === "tentative") return "tentative";
    if (status === "rated") return "rated";
    if (status === "self-cook") return "self-cook";
    if (status === "off") return "off";
    if (status === "voting") {
      // "1 / 3" tally; falls back to "voting" if denominator unknown.
      if (voteTally && voteTally.totalVoters > 0) {
        return `${voteTally.castVotes} / ${voteTally.totalVoters}`;
      }
      return "voting";
    }
    return "skipped";
  })();

  return (
    <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
      <View
        style={{
          width: 6,
          height: 6,
          borderRadius: 3,
          backgroundColor: color,
        }}
      />
      <Text
        style={{
          ...typography.tiny,
          color: colors.text.muted,
        }}
      >
        {label}
      </Text>
    </View>
  );
}

// ── Master status badge ─────────────────────────────────────────────

function MasterStatusBadge({
  status,
  isToday,
}: {
  status: { label: string; tone: "neutral" | "warning" | "success" | "primary" };
  isToday: boolean;
}) {
  const tones = {
    neutral: { bg: colors.surface.card, fg: colors.text.secondary, border: colors.border.subtle },
    success: { bg: colors.accent.successDim, fg: colors.accent.success, border: colors.accent.success },
    warning: { bg: colors.accent.warningDim, fg: colors.accent.warning, border: colors.accent.warning },
    primary: { bg: colors.surface.base, fg: colors.accent.primary, border: colors.accent.primary },
  } as const;

  const tone = tones[status.tone];

  return (
    <View
      style={{
        paddingHorizontal: spacing.sm,
        paddingVertical: 3,
        borderRadius: radius.pill,
        backgroundColor: isToday ? colors.surface.base : tone.bg,
        borderWidth: 1,
        borderColor: tone.border,
      }}
    >
      <Text
        style={{
          ...typography.tinyBold,
          color: tone.fg,
          letterSpacing: 0.4,
        }}
      >
        {status.label}
      </Text>
    </View>
  );
}

// ── Helpers ─────────────────────────────────────────────────────────

function buildMealPreviews(day: CalendarDay): MealPreview[] {
  // Cook-off classification is intentionally OUTSIDE the per-meal
  // status branch below: a cook-off meal supersedes "voted" / "rated"
  // because those green chips would falsely tell the user "the cook is
  // making this" when the cook isn't there. Whatever was voted stays
  // visible as historical context (the dish name renders muted, not
  // hidden), but the per-meal status flips to "off" or "self-cook" so
  // the at-a-glance signal matches reality.
  //
  // EXCEPTION: `replacement_cook` keeps the regular voted/rated status
  // because a sub cook is still making the voted plan — the original
  // cook is off but the dish is being made. The cook-off line at the
  // bottom of the cell ("Malti off — replacement booked") carries the
  // context.
  const cookOffStatusFor = (mt: MealType): "off" | "self-cook" | null => {
    if (!day.cookOff?.affectedMeals.includes(mt)) return null;
    const fb = day.cookOff.fallbackChosen;
    if (fb === "replacement_cook") return null;
    if (fb === "self_cook") return "self-cook";
    return "off";
  };

  // Future / today / tomorrow source: WeekDay.plans
  // We delegate the lifecycle classification to `classifyMealState`
  // (open/voting/tentative/locked) so the cell agrees with the day-
  // detail modal on every state. Cook-off + rated branches override
  // the lifecycle since they describe a different concern (no cook /
  // already eaten).
  if (day.weekDay) {
    // Total active voters drives the "X of N voted" denominator.
    // We approximate via the plan's vote count + skipped tally; if the
    // backend hasn't yet recorded the active member set we fall back to
    // the cast count so the label still makes sense ("1 voted" vs none).
    const activeMemberCount = day.weekDay.plans
      .map((p) =>
        new Set(p.votes.map((v) => v.memberId)).size,
      )
      .reduce((a, b) => Math.max(a, b), 0);

    return MEAL_ORDER.map((mt) => {
      const plan = day.weekDay!.plans.find((p) => p.mealType === mt);
      const offStatus = cookOffStatusFor(mt);
      if (offStatus) {
        return {
          mealType: mt,
          selectedMeal: plan?.selectedMeal ?? null,
          status: offStatus,
        };
      }
      if (plan?.rating != null) {
        return {
          mealType: mt,
          selectedMeal: plan.selectedMeal ?? null,
          status: "rated",
        };
      }
      if (!plan) {
        return { mealType: mt, selectedMeal: null, status: "open" };
      }
      const lifecycle = classifyMealState(plan);
      if (lifecycle === "voting") {
        const castVotes = plan.votes.filter((v) => !v.skipped).length;
        return {
          mealType: mt,
          selectedMeal: plan.selectedMeal ?? null,
          status: "voting",
          voteTally: {
            castVotes,
            totalVoters: Math.max(activeMemberCount, castVotes),
          },
        };
      }
      return {
        mealType: mt,
        selectedMeal: plan.selectedMeal ?? null,
        status: lifecycle, // "open" | "tentative" | "locked"
      };
    });
  }
  // Past source: history entries. Past cells are read-only — once a
  // day rolls into history, the meal is by definition "locked" (cook
  // already cooked it), so we map "entry exists, no rating" to the
  // "locked" lifecycle state so the dot legend stays consistent.
  if (day.pastEntries && day.pastEntries.length > 0) {
    return MEAL_ORDER.map((mt) => {
      const entry = day.pastEntries!.find((e) => e.mealType === mt);
      const hasRating = entry?.ratings && entry.ratings.length > 0;
      const offStatus = cookOffStatusFor(mt);
      return {
        mealType: mt,
        selectedMeal: entry?.selectedMeal ?? null,
        status: offStatus
          ? offStatus
          : hasRating
          ? "rated"
          : entry
          ? "locked"
          : "skipped",
      };
    });
  }
  // No data — empty rows.
  return MEAL_ORDER.map((mt) => ({
    mealType: mt,
    selectedMeal: null,
    status: "open",
  }));
}

function computeMasterStatus(
  day: CalendarDay,
):
  | { label: string; tone: "neutral" | "warning" | "success" | "primary" }
  | null {
  // Cook-off (almost) always wins the master chip — the previous
  // version returned "All set" when all 3 meals were voted even on a
  // cook-off day, which read as a false ✓ while the household was
  // actually self-cooking. EXCEPTION: replacement_cook lets the
  // normal voted/all-set logic win below, because the sub cook is
  // still making the voted plan.
  if (day.cookOff && day.cookOff.fallbackChosen !== "replacement_cook") {
    const fb = day.cookOff.fallbackChosen;
    if (!fb) return { label: "Cook off", tone: "warning" };
    if (fb === "self_cook") return { label: "Self-cook", tone: "warning" };
    if (fb === "order_food") return { label: "Ordering", tone: "warning" };
    if (fb === "instacook") return { label: "Insta Cook", tone: "warning" };
    if (fb === "skip") return { label: "Skipping", tone: "neutral" };
    return { label: "Cook off", tone: "warning" };
  }
  if (day.weekDay) {
    const plans = day.weekDay.plans;
    const total = day.weekDay.total;

    // Classify each meal so the master chip reflects the LIFECYCLE
    // (locked / tentative / voting / open) — not just "did anyone vote".
    // A previous version called every meal with a `selectedMeal`
    // "voted" and showed "All set" green even when meals were still
    // soft-locked, which read as final when it wasn't.
    const states = plans.map((p) => classifyMealState(p));
    const lockedCount = states.filter((s) => s === "locked").length;
    const tentativeCount = states.filter((s) => s === "tentative").length;
    const votingCount = states.filter((s) => s === "voting").length;
    const openCount = states.filter((s) => s === "open").length;

    if (lockedCount === total) {
      return {
        label: "All set",
        tone: day.state === "today" ? "primary" : "success",
      };
    }
    if (tentativeCount > 0) {
      // Tentative wins over voting/open since it's the most "this is
      // about to be decided" state. Singular reads as "Tentative",
      // plural surfaces the count.
      return {
        label: tentativeCount === 1 ? "Tentative" : `${tentativeCount} tentative`,
        tone: "warning",
      };
    }
    if (votingCount > 0 && openCount === 0) {
      return { label: "Voting open", tone: "warning" };
    }
    if (openCount === total) {
      return { label: `${total} to plan`, tone: "neutral" };
    }
    // Mix: some locked + some open/voting.
    const remaining = total - lockedCount;
    return { label: `${remaining} left`, tone: "warning" };
  }
  if (day.pastEntries && day.pastEntries.length > 0) {
    const ratedCount = day.pastEntries.filter(
      (e) => e.ratings.length > 0,
    ).length;
    if (ratedCount === day.pastEntries.length && ratedCount > 0)
      return { label: "Rated", tone: "success" };
    if (ratedCount > 0) return { label: `${ratedCount}★`, tone: "neutral" };
    return null;
  }
  return null;
}

function composeCookOffLine(cookOff: NonNullable<CalendarDay["cookOff"]>): string {
  const cookFirst = cookOff.absence.cookName.split(" ")[0] || cookOff.absence.cookName;
  const verb = cookOff.fallbackChosen;
  if (verb === "self_cook") return `${cookFirst} off — self-cooking`;
  if (verb === "order_food") return `${cookFirst} off — ordering in`;
  if (verb === "instacook") return `${cookFirst} off — Insta Cook arranged`;
  if (verb === "replacement_cook") return `${cookFirst} off — replacement booked`;
  if (verb === "skip") return `${cookFirst} off — skipping`;
  return cookOff.isFullDay
    ? `${cookFirst} off all day`
    : `${cookFirst} off — needs a plan`;
}

function composeA11yLabel(
  day: CalendarDay,
  masterStatus: ReturnType<typeof computeMasterStatus>,
  previews: MealPreview[],
): string {
  const parts: string[] = [];
  parts.push(day.dayLong);
  if (day.state === "today") parts.push("today");
  else if (day.state === "tomorrow") parts.push("tomorrow");
  if (masterStatus) parts.push(masterStatus.label);
  const voted = previews.filter((p) => p.status === "voted" || p.status === "rated").length;
  if (voted > 0 && day.state !== "past") {
    parts.push(`${voted} of ${previews.length} meals voted`);
  }
  if (day.cookOff) parts.push("cook is off");
  parts.push("opens day details");
  return parts.join(", ");
}

// ── Style presets ───────────────────────────────────────────────────

const collapsedOuterStyle = {
  borderRadius: radius.md,
  backgroundColor: "transparent" as const,
};
const collapsedInnerStyle = {
  paddingHorizontal: spacing.md,
  paddingVertical: spacing.sm + 2,
  flexDirection: "row" as const,
  alignItems: "center" as const,
  justifyContent: "space-between" as const,
  gap: spacing.md,
};
const collapsedDateStyle = {
  ...typography.smallBold,
  color: colors.text.muted,
  letterSpacing: 0.4,
};
const collapsedHintStyle = {
  ...typography.tiny,
  color: colors.text.muted,
  fontStyle: "italic" as const,
};
