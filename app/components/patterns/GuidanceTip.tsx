/**
 * GuidanceTip — one-line contextual hint or warning. Use for inline
 * explanations, safety notes, or feature descriptions on a screen.
 *
 * Tones drive both the icon color and the tinted background. Default is
 * "info"; use "warning" for blocking-ish concerns (allergies, dietary
 * conflicts), "success" for confirmations, "hint" for soft "did you
 * know" tips.
 */

import React from "react";
import { Text, View, ViewStyle } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { RipplePressable } from "../RipplePressable";
import {
  colors,
  iconSize,
  radius,
  spacing,
  typography,
} from "@/lib/theme";

export type GuidanceTone = "info" | "hint" | "success" | "warning";

const TONES: Record<
  GuidanceTone,
  {
    iconName: keyof typeof Ionicons.glyphMap;
    fg: string;
    bg: string;
  }
> = {
  info:    { iconName: "information-circle", fg: colors.accent.info,    bg: colors.accent.infoDim },
  hint:    { iconName: "bulb",               fg: colors.accent.primary, bg: colors.accent.primaryDim },
  success: { iconName: "checkmark-circle",   fg: colors.accent.success, bg: colors.accent.successDim },
  warning: { iconName: "warning",            fg: colors.accent.warning, bg: colors.accent.warningDim },
};

export interface GuidanceTipProps {
  message: string;
  title?: string;
  variant?: GuidanceTone;
  icon?: keyof typeof Ionicons.glyphMap;
  onDismiss?: () => void;
  compact?: boolean;
  style?: ViewStyle;
}

export function GuidanceTip({
  message,
  title,
  variant = "info",
  icon,
  onDismiss,
  compact = false,
  style,
}: GuidanceTipProps) {
  const tone = TONES[variant];

  return (
    <View
      style={[
        {
          backgroundColor: tone.bg,
          borderRadius: radius.md,
          padding: compact ? spacing.sm : spacing.md,
          flexDirection: "row",
          alignItems: "flex-start",
          gap: spacing.sm,
        },
        style,
      ]}
    >
      <Ionicons
        name={icon ?? tone.iconName}
        size={iconSize.md}
        color={tone.fg}
        style={{ marginTop: 1 }}
      />
      <View style={{ flex: 1 }}>
        {title ? (
          <Text style={{ ...typography.bodyBold, marginBottom: 2 }}>{title}</Text>
        ) : null}
        <Text style={{ ...typography.caption, color: colors.text.primary }}>
          {message}
        </Text>
      </View>
      {onDismiss ? (
        <RipplePressable
          onPress={onDismiss}
          haptic="selection"
          accessibilityRole="button"
          accessibilityLabel="Dismiss"
          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          style={{ width: 24, height: 24, alignItems: "center", justifyContent: "center" }}
        >
          <Ionicons name="close" size={iconSize.sm} color={colors.text.muted} />
        </RipplePressable>
      ) : null}
    </View>
  );
}
