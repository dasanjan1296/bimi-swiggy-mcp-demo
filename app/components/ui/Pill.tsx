/**
 * Pill / chip primitive — covers tab-pills (active/inactive), filter chips,
 * tag chips, and the "selected"/"selectable" pattern.
 *
 * Replaces ~18 inline pill chips with hand-rolled radius/padding/fontSize.
 */

import React from "react";
import { Text, View, ViewStyle } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { RipplePressable } from "../RipplePressable";
import { colors, radius, fontFamily, iconSize as iconSizes } from "@/lib/theme";

export type PillTone = "primary" | "neutral" | "success" | "warning" | "danger" | "info" | "ai";
export type PillSize = "xs" | "sm" | "md";

export interface PillProps {
  children: React.ReactNode;
  tone?: PillTone;
  size?: PillSize;
  active?: boolean;
  leadingIcon?: keyof typeof Ionicons.glyphMap;
  trailingIcon?: keyof typeof Ionicons.glyphMap;
  onPress?: () => void;
  /** When true, render with `borderRadius: pill` even at xs size. */
  rounded?: boolean;
  style?: ViewStyle;
  accessibilityLabel?: string;
}

function colorsFor(tone: PillTone, active: boolean) {
  if (!active) {
    // Airbnb-style inactive filter chip: white fill, subtle border.
    return { bg: colors.surface.base, fg: colors.text.primary, border: colors.border.subtle };
  }
  switch (tone) {
    case "primary":
      // Filter-chip "selected" pattern: filled dark (NOT Rausch). Rausch
      // is reserved for the screen's primary CTA, not pills.
      return { bg: colors.text.primary, fg: colors.text.inverse, border: colors.text.primary };
    case "success":
      return { bg: colors.accent.successDim, fg: colors.accent.success, border: colors.accent.successDim };
    case "warning":
      return { bg: colors.accent.warningDim, fg: colors.accent.warning, border: colors.accent.warningDim };
    case "danger":
      return { bg: colors.accent.dangerDim, fg: colors.accent.danger, border: colors.accent.dangerDim };
    case "info":
      return { bg: colors.accent.infoDim, fg: colors.accent.info, border: colors.accent.infoDim };
    case "ai":
      return { bg: colors.accent.aiDim, fg: colors.accent.ai, border: colors.accent.aiDim };
    case "neutral":
    default:
      return { bg: colors.surface.card, fg: colors.text.primary, border: colors.surface.card };
  }
}

function dimsFor(size: PillSize) {
  switch (size) {
    case "xs":
      return { padH: 8, padV: 3, fontSize: 11, iconSize: iconSizes.xs, gap: 4 };
    case "md":
      return { padH: 14, padV: 8, fontSize: 13, iconSize: iconSizes.sm, gap: 6 };
    case "sm":
    default:
      return { padH: 10, padV: 5, fontSize: 12, iconSize: iconSizes.xs, gap: 5 };
  }
}

function PillImpl({
  children,
  tone = "primary",
  size = "sm",
  active = true,
  leadingIcon,
  trailingIcon,
  onPress,
  rounded = true,
  style,
  accessibilityLabel,
}: PillProps) {
  const c = colorsFor(tone, active);
  const d = dimsFor(size);

  const containerStyle: ViewStyle = {
    backgroundColor: c.bg,
    borderRadius: rounded ? radius.pill : radius.sm,
    borderWidth: 1,
    borderColor: c.border,
    paddingHorizontal: d.padH,
    paddingVertical: d.padV,
    flexDirection: "row",
    alignItems: "center",
    gap: d.gap,
    alignSelf: "flex-start",
    ...style,
  };

  const inner = (
    <>
      {leadingIcon && <Ionicons name={leadingIcon} size={d.iconSize} color={c.fg} />}
      {typeof children === "string" ? (
        <Text style={{ fontSize: d.fontSize, fontWeight: "600", fontFamily: fontFamily.semibold, color: c.fg }} numberOfLines={1}>
          {children}
        </Text>
      ) : (
        children
      )}
      {trailingIcon && <Ionicons name={trailingIcon} size={d.iconSize} color={c.fg} />}
    </>
  );

  if (!onPress) {
    return (
      <View style={containerStyle} accessibilityLabel={accessibilityLabel}>
        {inner}
      </View>
    );
  }

  return (
    <RipplePressable
      onPress={onPress}
      style={containerStyle}
      haptic="selection"
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel}
      accessibilityState={{ selected: active }}
    >
      {inner}
    </RipplePressable>
  );
}

/** Memoised — Pills get rendered in long chip rows (cuisine filters,
 *  feedback areas, popular dishes, voting modes). Prevents re-render
 *  cascade when the parent's unrelated state changes. */
export const Pill = React.memo(PillImpl);
