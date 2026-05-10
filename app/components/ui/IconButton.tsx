/**
 * IconButton — tap target for an icon-only action with optional label below
 * and badge overlay. Replaces hand-rolled circle/tile icon-buttons across
 * Home, InstaCookHeroCard quick actions, header circle buttons, etc.
 */

import React from "react";
import { View, Text, ViewStyle } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { RipplePressable } from "../RipplePressable";
import { colors, radius, spacing, fontFamily, iconSize as iconSizes } from "@/lib/theme";

export type IconButtonSize = "sm" | "md" | "lg";
export type IconButtonShape = "circle" | "tile";

export interface IconButtonProps {
  icon: keyof typeof Ionicons.glyphMap;
  onPress?: () => void;
  label?: string;
  size?: IconButtonSize;
  shape?: IconButtonShape;
  badge?: number;
  badgeColor?: string;
  iconColor?: string;
  active?: boolean;
  disabled?: boolean;
  style?: ViewStyle;
  accessibilityLabel?: string;
}

function dimsFor(size: IconButtonSize) {
  switch (size) {
    case "sm": return { d: 36, icon: iconSizes.sm };
    case "lg": return { d: 48, icon: iconSizes.lg };
    case "md":
    default:   return { d: 40, icon: iconSizes.md };
  }
}

export function IconButton({
  icon,
  onPress,
  label,
  size = "md",
  shape = "circle",
  badge,
  badgeColor,
  iconColor,
  active = false,
  disabled = false,
  style,
  accessibilityLabel,
}: IconButtonProps) {
  const d = dimsFor(size);
  // Airbnb-style ghost circle: white fill, hairline border, dark icon by
  // default. Active state uses primaryDim + Rausch icon — used sparingly
  // (e.g. notification button when there's an unread).
  const fg = iconColor ?? (active ? colors.accent.primary : colors.text.primary);
  const bg = active ? colors.accent.primaryDim : colors.surface.base;
  const borderColor = active ? colors.accent.primary : colors.border.subtle;

  const containerStyle: ViewStyle = {
    width: d.d,
    height: d.d,
    borderRadius: shape === "circle" ? d.d / 2 : radius.lg,
    backgroundColor: bg,
    borderWidth: 1,
    borderColor,
    alignItems: "center",
    justifyContent: "center",
    opacity: disabled ? 0.5 : 1,
    ...style,
  };

  const button = (
    <View>
      <RipplePressable
        onPress={disabled ? undefined : onPress}
        disabled={disabled}
        haptic="light"
        accessibilityRole="button"
        accessibilityLabel={accessibilityLabel ?? label}
        accessibilityState={{ disabled, selected: active }}
        style={containerStyle}
      >
        <Ionicons name={icon} size={d.icon} color={fg} />
      </RipplePressable>
      {typeof badge === "number" && badge > 0 && (
        <View
          pointerEvents="none"
          style={{
            position: "absolute",
            top: -4,
            right: -4,
            minWidth: 18,
            height: 18,
            paddingHorizontal: 4,
            borderRadius: 9,
            backgroundColor: badgeColor ?? colors.accent.danger,
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Text style={{ fontSize: 10, fontWeight: "700", fontFamily: fontFamily.bold, color: colors.text.inverse }}>
            {badge > 99 ? "99+" : badge}
          </Text>
        </View>
      )}
    </View>
  );

  if (!label) return button;

  return (
    <View style={{ alignItems: "center" }}>
      {button}
      <Text
        style={{
          fontSize: 11,
          fontWeight: "500",
          fontFamily: fontFamily.medium,
          color: colors.text.muted,
          marginTop: spacing.xs,
          textAlign: "center",
        }}
        numberOfLines={1}
      >
        {label}
      </Text>
    </View>
  );
}
