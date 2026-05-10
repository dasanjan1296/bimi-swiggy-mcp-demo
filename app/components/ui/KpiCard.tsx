/**
 * KpiCard — single primary number per card with optional trend + sparkline.
 * Modeled on the metric card in `health-dashboard.tsx` (the canonical version).
 *
 * Replaces `StatBox` (insights), per-person row (expenses), inline KPI rows
 * in BookingReviewSheet and PlanVisualization.
 */

import React from "react";
import { View, Text, ViewStyle } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, cardStyles, radius, spacing, typography, fontFamily, iconSize } from "@/lib/theme";
import type { PillTone } from "./Pill";

export interface KpiCardProps {
  label: string;
  value: string | number;
  unit?: string;
  /** Small uppercase eyebrow above the value (e.g., "this month"). */
  eyebrow?: string;
  icon?: keyof typeof Ionicons.glyphMap;
  /** Tone applied to the value text + accent strip on the left. */
  tone?: PillTone;
  /** Optional trend delta (positive = up, negative = down). */
  trend?: { delta: number; suffix?: string; positiveIsGood?: boolean };
  /** Footer line — e.g., "Last recorded: Apr 18". */
  footer?: string;
  /** Optional sparkline data series — last point is highlighted. */
  sparkline?: number[];
  style?: ViewStyle;
}

function toneColor(tone: PillTone): string {
  switch (tone) {
    case "primary":  return colors.accent.primary;
    case "success":  return colors.accent.success;
    case "warning":  return colors.accent.warning;
    case "danger":   return colors.accent.danger;
    case "info":     return colors.accent.info;
    case "ai":       return colors.accent.ai;
    case "neutral":
    default:         return colors.text.primary;
  }
}

export function KpiCard({ label, value, unit, eyebrow, icon, tone = "primary", trend, footer, sparkline, style }: KpiCardProps) {
  const valueColor = toneColor(tone);

  let trendColor: string = colors.text.muted;
  let trendIcon: keyof typeof Ionicons.glyphMap = "remove-outline";
  if (trend && trend.delta !== 0) {
    const isUp = trend.delta > 0;
    const positiveIsGood = trend.positiveIsGood ?? true;
    const isGood = isUp === positiveIsGood;
    trendColor = isGood ? colors.accent.success : colors.accent.danger;
    trendIcon = isUp ? "trending-up" : "trending-down";
  }

  return (
    <View
      style={{
        ...cardStyles,
        borderLeftWidth: 4,
        borderLeftColor: valueColor,
        ...style,
      }}
    >
      <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, marginBottom: spacing.xs }}>
        {icon && <Ionicons name={icon} size={iconSize.sm} color={colors.text.secondary} />}
        <Text style={{ ...typography.caption, flex: 1 }} numberOfLines={1}>{label}</Text>
      </View>

      {eyebrow && (
        <Text style={{ ...typography.tiny, marginBottom: 2, textTransform: "uppercase", letterSpacing: 1 }}>
          {eyebrow}
        </Text>
      )}

      <View style={{ flexDirection: "row", alignItems: "baseline", gap: spacing.xs }}>
        <Text style={{ fontSize: 28, fontWeight: "800", fontFamily: fontFamily.extrabold, color: valueColor }}>
          {value}
        </Text>
        {unit && <Text style={{ ...typography.captionBold, color: colors.text.secondary }}>{unit}</Text>}
        {trend && trend.delta !== 0 && (
          <View style={{ flexDirection: "row", alignItems: "center", gap: 2, marginLeft: spacing.sm }}>
            <Ionicons name={trendIcon} size={iconSize.xs} color={trendColor} />
            <Text style={{ ...typography.tiny, color: trendColor }}>
              {Math.abs(trend.delta)}{trend.suffix ?? ""}
            </Text>
          </View>
        )}
      </View>

      {sparkline && sparkline.length > 1 && (
        <View style={{ flexDirection: "row", alignItems: "flex-end", gap: 3, height: 28, marginTop: spacing.sm }}>
          {sparkline.map((v, idx) => {
            const max = Math.max(...sparkline, 1);
            const h = Math.max(3, (v / max) * 24);
            const isLast = idx === sparkline.length - 1;
            return (
              <View
                key={idx}
                style={{
                  width: 6,
                  height: h,
                  borderRadius: 2,
                  backgroundColor: isLast ? valueColor : colors.surface.elevated,
                }}
              />
            );
          })}
        </View>
      )}

      {footer && (
        <Text style={{ ...typography.tiny, marginTop: spacing.sm }}>{footer}</Text>
      )}
    </View>
  );
}
