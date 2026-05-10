/**
 * IconBadge — small rounded-square (or circle) icon container.
 *
 * The "icon-in-tinted-square" pattern duplicated in:
 *   AutoRuleCard, EmptyStateGuide, HowItWorks, BookingReviewSheet, MealCalendar.
 */

import React from "react";
import { View, ViewStyle } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, radius, iconSize as iconSizes } from "@/lib/theme";
import type { PillTone } from "./Pill";

export type IconBadgeSize = "xs" | "sm" | "md" | "lg";

export interface IconBadgeProps {
  icon: keyof typeof Ionicons.glyphMap;
  tone?: PillTone;
  size?: IconBadgeSize;
  /** When true, renders a circle instead of a rounded square. */
  circle?: boolean;
  style?: ViewStyle;
}

function dimsFor(size: IconBadgeSize) {
  switch (size) {
    case "xs": return { d: 24, icon: iconSizes.xs };
    case "sm": return { d: 32, icon: iconSizes.sm };
    case "lg": return { d: 56, icon: iconSizes.lg };
    case "md":
    default:   return { d: 40, icon: iconSizes.md };
  }
}

function colorsFor(tone: PillTone): { bg: string; fg: string } {
  switch (tone) {
    case "primary":  return { bg: colors.accent.primaryDim, fg: colors.accent.primary };
    case "success":  return { bg: colors.accent.successDim, fg: colors.accent.success };
    case "warning":  return { bg: colors.accent.warningDim, fg: colors.accent.warning };
    case "danger":   return { bg: colors.accent.dangerDim,  fg: colors.accent.danger };
    case "info":     return { bg: colors.accent.infoDim,    fg: colors.accent.info };
    case "ai":       return { bg: colors.accent.aiDim,      fg: colors.accent.ai };
    case "neutral":
    default:         return { bg: colors.surface.elevated,  fg: colors.text.secondary };
  }
}

export function IconBadge({ icon, tone = "primary", size = "md", circle = false, style }: IconBadgeProps) {
  const d = dimsFor(size);
  const c = colorsFor(tone);
  return (
    <View
      style={{
        width: d.d,
        height: d.d,
        borderRadius: circle ? d.d / 2 : radius.md,
        backgroundColor: c.bg,
        alignItems: "center",
        justifyContent: "center",
        ...style,
      }}
    >
      <Ionicons name={icon} size={d.icon} color={c.fg} />
    </View>
  );
}
