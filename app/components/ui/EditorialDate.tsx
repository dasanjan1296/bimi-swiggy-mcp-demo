/**
 * EditorialDate — magazine-masthead-style date block. Renders the
 * weekday in caps as a small eyebrow, separated by a hairline rule
 * from the date numeral + month, with the year trailing in a muted
 * tone. Reads like the dateline at the top of a print edition:
 *
 *   SUNDAY  |  3 May  2026
 *   ^muted     ^dark    ^muted
 *
 * Typography only — never tints the date in Rausch. accent.primary is
 * reserved for the screen's single primary action / active state /
 * link / brand mark (see design-system.md §Color); a date eyebrow is
 * none of those, and on the home tab specifically the NextBestAction
 * hero already owns the Rausch slot. Restraint here is the point.
 *
 * Sizing:
 *   - `md` (default): bodyBold date + tinyBold eyebrow. Fits the home
 *     header below the greeting. The "calm but considered" preset.
 *   - `sm`: smallBold date + tiny eyebrow. For dense headers (sheets,
 *     section toolbars).
 *
 * Locale uses "en-IN" so we match the rest of the app (Sunday-first
 * weekday names, Indian-format date order — e.g. "3 May" not "May 3").
 */

import React, { useMemo } from "react";
import { Text, TextStyle, View, ViewStyle } from "react-native";
import { colors, spacing, typography } from "@/lib/theme";
import { useToday } from "@/lib/local-day";

export type EditorialDateSize = "sm" | "md";

export interface EditorialDateProps {
  /** Date to render. Defaults to `new Date()`. */
  date?: Date;
  /** When false, the trailing year is hidden (use in tight contexts). */
  showYear?: boolean;
  /** Default `md`. */
  size?: EditorialDateSize;
  /** Optional outer container style (margins, alignment). */
  style?: ViewStyle;
}

interface SizeSpec {
  // Each slot accepts any typography preset (`bodyBold`, `smallBold`,
  // `tinyBold`, `tiny`, etc.) — the `sm` variant intentionally swaps
  // in tighter weights, so a tighter type-of-bodyBold lock here was
  // wrong. `TextStyle` keeps the contract honest without leaking
  // unrelated style properties into the API.
  eyebrow: TextStyle;
  date: TextStyle;
  year: TextStyle;
  ruleHeight: number;
  eyebrowSpacing: number;
}

const SIZE_SPECS: Record<EditorialDateSize, SizeSpec> = {
  md: {
    eyebrow: typography.tinyBold,
    date: typography.bodyBold,
    year: typography.tiny,
    ruleHeight: 12,
    eyebrowSpacing: 1.8,
  },
  sm: {
    eyebrow: typography.tiny,
    date: typography.smallBold,
    year: typography.tiny,
    ruleHeight: 10,
    eyebrowSpacing: 1.6,
  },
};

export function EditorialDate({
  date,
  showYear = true,
  size = "md",
  style,
}: EditorialDateProps) {
  const spec = SIZE_SPECS[size];
  // When no `date` is supplied the component subscribes to `useToday()`
  // so the day-name + numeral roll over at local midnight (and on app
  // foreground after a midnight crossing). This is what fixes the
  // "shows Sunday on a Monday morning" bug — `new Date()` captured at
  // mount never re-evaluates on its own.
  const liveToday = useToday();
  const resolved = date ?? liveToday;

  const { dayName, dayMonth, year } = useMemo(() => {
    return {
      dayName: resolved.toLocaleDateString("en-IN", { weekday: "long" }).toUpperCase(),
      dayMonth: resolved.toLocaleDateString("en-IN", {
        day: "numeric",
        month: "long",
      }),
      year: String(resolved.getFullYear()),
    };
  }, [resolved]);

  return (
    <View
      style={[
        { flexDirection: "row", alignItems: "center", gap: spacing.sm },
        style,
      ]}
      accessibilityLabel={resolved.toLocaleDateString("en-IN", {
        weekday: "long",
        day: "numeric",
        month: "long",
        year: "numeric",
      })}
    >
      <Text
        style={{
          ...spec.eyebrow,
          color: colors.text.secondary,
          textTransform: "uppercase",
          letterSpacing: spec.eyebrowSpacing,
        }}
        numberOfLines={1}
      >
        {dayName}
      </Text>

      <View
        style={{
          width: 1,
          height: spec.ruleHeight,
          backgroundColor: colors.border.subtle,
        }}
      />

      <Text
        style={{
          ...spec.date,
          color: colors.text.primary,
          letterSpacing: -0.2,
        }}
        numberOfLines={1}
      >
        {dayMonth}
      </Text>

      {showYear ? (
        <Text
          style={{
            ...spec.year,
            color: colors.text.muted,
          }}
          numberOfLines={1}
        >
          {year}
        </Text>
      ) : null}
    </View>
  );
}
