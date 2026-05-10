/**
 * SelfCookCta — the canonical "Self cook ideas" button. Soft Rausch
 * squircle that opens the recipe browser when the user's cook is off.
 *
 * Two surfaces share this affordance:
 *   • The home wheel's centre card, when the active day's cook is
 *     off and the absence is unresolved.
 *   • The day-meal-sheet's cook-off banner, before the user picks a
 *     fallback.
 *
 * Both surfaces previously rendered byte-identical inline copies of
 * the button (a private `CookOffCta` function in WheelOfMeals.tsx +
 * an inline RipplePressable in DayMealSheet.tsx). Two copies = drift
 * waiting to happen — the same story as the wheel's `CookOffPill` and
 * `MealDotTrio` atoms, both of which had to be extracted later for
 * the same reason. This atom lives here from day one.
 *
 * Shape: `radius.lg` squircle, NOT a full pill (`borderRadius: 999`).
 * The centre card is circular; pill ends collide with the curved wall
 * at any vertical position other than the exact mid-line. A squircle
 * with gentler corners settles inside the curve and leaves visible
 * breathing room — the geometric tangent problem goes away.
 *
 * Tone: solid Rausch fill — this is the screen's primary action when
 * the cook is off, and there's exactly one of it on each surface, so
 * it gets the canonical primary treatment.
 */

import React from "react";
import { Text, ViewStyle } from "react-native";
import { RipplePressable } from "../RipplePressable";
import { colors, radius, spacing, typography } from "@/lib/theme";

export interface SelfCookCtaProps {
  /** Defaults to "Self cook ideas" — the canonical label. Override
   *  only with intent (and update the design-system doc if you do). */
  label?: string;
  onPress: () => void;
  /** Optional outer-style override (e.g., margin tweaks). */
  style?: ViewStyle;
  testID?: string;
}

const DEFAULT_LABEL = "Self cook ideas";

export function SelfCookCta({
  label = DEFAULT_LABEL,
  onPress,
  style,
  testID,
}: SelfCookCtaProps) {
  return (
    <RipplePressable
      onPress={onPress}
      haptic="selection"
      accessibilityRole="button"
      accessibilityLabel={label}
      testID={testID}
      style={{
        backgroundColor: colors.accent.primary,
        paddingVertical: spacing.sm,
        paddingHorizontal: spacing.md,
        borderRadius: radius.lg,
        alignItems: "center",
        alignSelf: "center",
        ...style,
      }}
    >
      <Text
        style={{
          ...typography.smallBold,
          color: colors.surface.base,
          letterSpacing: 0.2,
        }}
        numberOfLines={1}
      >
        {label}
      </Text>
    </RipplePressable>
  );
}
