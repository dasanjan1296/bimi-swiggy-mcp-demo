/**
 * TextLink — tertiary text-only pressable. For "Edit menu", "Change time",
 * "Skip verification", "Have an invite code? Join a house".
 */

import React from "react";
import { Text, TextStyle, ViewStyle } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { RipplePressable } from "../RipplePressable";
import { colors, fontFamily, iconSize as iconSizes, spacing } from "@/lib/theme";

export type TextLinkSize = "sm" | "md";
export type TextLinkTone = "primary" | "secondary" | "muted" | "danger" | "success";

export interface TextLinkProps {
  children: React.ReactNode;
  onPress?: () => void;
  size?: TextLinkSize;
  tone?: TextLinkTone;
  leadingIcon?: keyof typeof Ionicons.glyphMap;
  trailingIcon?: keyof typeof Ionicons.glyphMap;
  underline?: boolean;
  style?: ViewStyle;
  accessibilityLabel?: string;
}

function colorFor(tone: TextLinkTone): string {
  switch (tone) {
    case "primary":   return colors.accent.primary;
    case "secondary": return colors.text.secondary;
    case "muted":     return colors.text.muted;
    case "danger":    return colors.accent.danger;
    case "success":   return colors.accent.success;
  }
}

function dimsFor(size: TextLinkSize) {
  switch (size) {
    case "sm": return { fontSize: 12, iconSize: iconSizes.xs };
    case "md":
    default:   return { fontSize: 14, iconSize: iconSizes.sm };
  }
}

export function TextLink({
  children,
  onPress,
  size = "md",
  tone = "primary",
  leadingIcon,
  trailingIcon,
  underline = false,
  style,
  accessibilityLabel,
}: TextLinkProps) {
  const c = colorFor(tone);
  const d = dimsFor(size);

  const textStyle: TextStyle = {
    fontSize: d.fontSize,
    fontWeight: "600",
    fontFamily: fontFamily.semibold,
    color: c,
    textDecorationLine: underline ? "underline" : "none",
  };

  return (
    <RipplePressable
      onPress={onPress}
      haptic="selection"
      accessibilityRole="link"
      accessibilityLabel={accessibilityLabel ?? (typeof children === "string" ? children : undefined)}
      hitSlop={{ top: 8, left: 8, right: 8, bottom: 8 }}
      style={{
        flexDirection: "row",
        alignItems: "center",
        gap: spacing.xs,
        alignSelf: "flex-start",
        ...style,
      }}
    >
      {leadingIcon && <Ionicons name={leadingIcon} size={d.iconSize} color={c} />}
      <Text style={textStyle}>{children}</Text>
      {trailingIcon && <Ionicons name={trailingIcon} size={d.iconSize} color={c} />}
    </RipplePressable>
  );
}
