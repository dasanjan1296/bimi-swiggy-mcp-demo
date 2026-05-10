/**
 * Card — the canonical visually-grouped container in Bimi.
 *
 * Variants:
 *   • flat        — gray surface, no shadow. Default for grouped content.
 *   • interactive — flat + RipplePressable. Pressable cards (tap to open).
 *   • elevated    — white surface + soft shadow. Hero cards.
 *   • photo       — full-bleed image header + content body. Use <PhotoCard>
 *                   directly when you need the photo treatment.
 *
 * Design rules enforced (see design-system.md §7):
 *   - Border-less by default (Airbnb pattern). The previous "glass card +
 *     hairline border" died with the dark theme.
 *   - Padding is always spacing.lg (16). Override only for nested cards.
 *   - Radius is always radius.lg (16) for flat / interactive / elevated.
 */

import React from "react";
import { View, ViewStyle } from "react-native";
import { RipplePressable } from "../RipplePressable";
import {
  cardStyles,
  colors,
  elevatedCardStyles,
  radius,
  spacing,
} from "@/lib/theme";

export type CardVariant = "flat" | "interactive" | "elevated";

export interface CardProps {
  variant?: CardVariant;
  /** Slot for content. */
  children: React.ReactNode;
  /** Tap handler — required when variant is "interactive". */
  onPress?: () => void;
  /** Override the default radius.lg (e.g., for nested-in-card-card cases). */
  borderRadius?: number;
  /** Override the default padding (rare). */
  padding?: number;
  style?: ViewStyle;
  /** Accessibility label, required when interactive. */
  accessibilityLabel?: string;
  testID?: string;
}

export function Card({
  variant = "flat",
  children,
  onPress,
  borderRadius,
  padding,
  style,
  accessibilityLabel,
  testID,
}: CardProps) {
  const base: ViewStyle =
    variant === "elevated"
      ? { ...elevatedCardStyles }
      : { ...cardStyles };

  const merged: ViewStyle = {
    ...base,
    ...(borderRadius !== undefined ? { borderRadius } : null),
    ...(padding !== undefined ? { padding } : null),
    ...style,
  };

  if (variant === "interactive" && onPress) {
    return (
      <RipplePressable
        onPress={onPress}
        haptic="selection"
        accessibilityRole="button"
        accessibilityLabel={accessibilityLabel}
        testID={testID}
        style={merged}
      >
        {children}
      </RipplePressable>
    );
  }

  return (
    <View style={merged} testID={testID}>
      {children}
    </View>
  );
}
