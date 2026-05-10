import React from "react";
import { View, Text } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { RipplePressable } from "./RipplePressable";
import { colors, circleButtonStyles, spacing } from "@/lib/theme";

interface CircleButtonProps {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  onPress?: () => void;
  iconColor?: string;
  badge?: number;
  badgeColor?: string;
}

export function CircleButton({
  icon,
  label,
  onPress,
  iconColor = colors.accent.primary,
  badge,
  badgeColor = colors.accent.secondary,
}: CircleButtonProps) {
  return (
    <View style={{ alignItems: "center" }}>
      <RipplePressable
        onPress={onPress}
        haptic="light"
        style={{ borderRadius: 28, overflow: "hidden" }}
        accessibilityRole="button"
        accessibilityLabel={badge != null && badge > 0 ? `${label}, ${badge} unread` : label}
      >
        <View style={circleButtonStyles.container}>
          <Ionicons name={icon} size={22} color={iconColor} />
          {badge != null && badge > 0 && (
            <View
              style={{
                position: "absolute",
                top: 2,
                right: 2,
                width: 16,
                height: 16,
                borderRadius: 8,
                backgroundColor: badgeColor,
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <Text style={{ fontSize: 9, fontWeight: "700", color: colors.text.primary }}>
                {badge > 9 ? "9+" : badge}
              </Text>
            </View>
          )}
        </View>
      </RipplePressable>
      <Text style={{ ...circleButtonStyles.label, marginTop: spacing.xs }}>{label}</Text>
    </View>
  );
}
