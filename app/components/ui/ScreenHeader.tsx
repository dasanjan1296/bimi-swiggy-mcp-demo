/**
 * ScreenHeader — single source of truth for in-content screen headers.
 *
 * Replaces the six different header patterns currently in use across the app.
 * Use ONLY when the screen has `headerShown: false` on its Stack.Screen entry;
 * otherwise let the native stack header handle it.
 */

import React from "react";
import { View, Text, ViewStyle } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { RipplePressable } from "../RipplePressable";
import { colors, spacing, typography, iconSize } from "@/lib/theme";
import { safeBack } from "@/lib/safe-back";

export interface ScreenHeaderProps {
  title: string;
  subtitle?: string;
  /** When true, render a back-arrow on the left that calls `safeBack()`
   *  (pops the stack if possible, otherwise replaces with `/(tabs)`). */
  back?: boolean;
  /** Override the back action (defaults to `safeBack()`). */
  onBack?: () => void;
  /** Optional custom right-side element (icon button, link, etc). */
  right?: React.ReactNode;
  /** Centered layout (used by onboarding). */
  centered?: boolean;
  style?: ViewStyle;
}

export function ScreenHeader({
  title,
  subtitle,
  back = false,
  onBack,
  right,
  centered = false,
  style,
}: ScreenHeaderProps) {
  const handleBack = () => {
    if (onBack) onBack();
    else safeBack();
  };

  return (
    <View
      style={{
        flexDirection: "row",
        alignItems: "center",
        gap: spacing.sm,
        marginBottom: spacing.xl,
        ...style,
      }}
    >
      {back && (
        <RipplePressable
          onPress={handleBack}
          hitSlop={{ top: 12, left: 12, right: 12, bottom: 12 }}
          accessibilityRole="button"
          accessibilityLabel="Go back"
          haptic="selection"
          style={{
            width: 40,
            height: 40,
            marginLeft: -spacing.sm,
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Ionicons name="chevron-back" size={iconSize.lg} color={colors.text.primary} />
        </RipplePressable>
      )}
      <View style={{ flex: 1, alignItems: centered ? "center" : "flex-start" }}>
        <Text style={typography.h1} numberOfLines={1}>{title}</Text>
        {subtitle && (
          <Text style={{ ...typography.caption, marginTop: 2 }} numberOfLines={2}>
            {subtitle}
          </Text>
        )}
      </View>
      {right}
    </View>
  );
}
