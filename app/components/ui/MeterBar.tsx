/**
 * MeterBar — single-fill horizontal progress/meter bar.
 *
 * Replaces three meter-bar implementations:
 *   MealCard mini-fairness, FairnessBar per-member, PlanVisualization.ManHoursBar.
 */

import React from "react";
import { View, Text, ViewStyle } from "react-native";
import { colors, fontFamily, spacing } from "@/lib/theme";
import type { PillTone } from "./Pill";

export type MeterSize = "sm" | "md" | "lg";

export interface MeterBarProps {
  /** Value as a fraction 0..1 OR an absolute number (then `max` is required). */
  value: number;
  max?: number;
  tone?: PillTone | string;
  size?: MeterSize;
  /** Optional left label (e.g., a member name). */
  label?: string;
  /** Optional right value (e.g., "62%" or "5 meals"). */
  trailingLabel?: string;
  style?: ViewStyle;
}

function heightFor(size: MeterSize) {
  switch (size) {
    case "sm": return 4;
    case "lg": return 10;
    case "md":
    default:   return 6;
  }
}

function toneColor(tone: PillTone | string): string {
  switch (tone) {
    case "primary":  return colors.accent.primary;
    case "success":  return colors.accent.success;
    case "warning":  return colors.accent.warning;
    case "danger":   return colors.accent.danger;
    case "info":     return colors.accent.info;
    case "ai":       return colors.accent.ai;
    case "neutral":  return colors.text.secondary;
    default:         return tone; // raw color allowed
  }
}

export function MeterBar({
  value,
  max,
  tone = "primary",
  size = "md",
  label,
  trailingLabel,
  style,
}: MeterBarProps) {
  const fraction = max && max > 0 ? value / max : value;
  const pct = Math.max(0, Math.min(1, fraction)) * 100;
  const h = heightFor(size);
  const fill = toneColor(tone);

  const bar = (
    <View
      style={{
        height: h,
        borderRadius: h / 2,
        backgroundColor: colors.surface.elevated,
        overflow: "hidden",
        flex: 1,
      }}
      accessibilityRole="progressbar"
      accessibilityValue={{ now: Math.round(pct), min: 0, max: 100 }}
    >
      <View style={{ width: `${pct}%`, height: "100%", backgroundColor: fill, borderRadius: h / 2 }} />
    </View>
  );

  if (!label && !trailingLabel) {
    return <View style={style}>{bar}</View>;
  }

  return (
    <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, ...style }}>
      {label && (
        <Text style={{ fontSize: 12, fontFamily: fontFamily.regular, color: colors.text.secondary, flex: 1 }} numberOfLines={1}>
          {label}
        </Text>
      )}
      {bar}
      {trailingLabel && (
        <Text style={{ fontSize: 12, fontWeight: "600", fontFamily: fontFamily.semibold, color: colors.text.primary, minWidth: 36, textAlign: "right" }}>
          {trailingLabel}
        </Text>
      )}
    </View>
  );
}
