/**
 * EmptyState — rich empty state for any list / section that has no data
 * yet. Required pattern: never render a bare "<Text>No items</Text>".
 *
 * Slots:
 *   - icon (required)
 *   - title (required)
 *   - message (required) — explains what will appear and how
 *   - hint (optional) — actionable next step ("Set up auto-rules in Settings")
 *   - action (optional) — primary button to take that next step
 */

import React from "react";
import { Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { Button, type ButtonVariant } from "../ui/Button";
import {
  colors,
  iconSize,
  radius,
  spacing,
  typography,
} from "@/lib/theme";

export interface EmptyStateProps {
  icon: keyof typeof Ionicons.glyphMap;
  title: string;
  message: string;
  hint?: string;
  action?: {
    label: string;
    onPress: () => void;
    variant?: ButtonVariant;
  };
}

export function EmptyState({
  icon,
  title,
  message,
  hint,
  action,
}: EmptyStateProps) {
  return (
    <View
      style={{
        alignItems: "center",
        paddingVertical: spacing.xxxl,
        paddingHorizontal: spacing.xl,
      }}
    >
      <View
        style={{
          width: 64,
          height: 64,
          borderRadius: 32,
          backgroundColor: colors.surface.card,
          alignItems: "center",
          justifyContent: "center",
          marginBottom: spacing.lg,
        }}
      >
        <Ionicons name={icon} size={iconSize.lg} color={colors.text.muted} />
      </View>
      <Text
        style={{
          ...typography.h3,
          textAlign: "center",
          marginBottom: spacing.xs,
        }}
      >
        {title}
      </Text>
      <Text
        style={{
          ...typography.caption,
          textAlign: "center",
          maxWidth: 320,
        }}
      >
        {message}
      </Text>
      {hint ? (
        <View
          style={{
            flexDirection: "row",
            alignItems: "center",
            gap: spacing.xs,
            backgroundColor: colors.accent.primaryDim,
            borderRadius: radius.sm,
            paddingHorizontal: spacing.md,
            paddingVertical: spacing.sm,
            marginTop: spacing.md,
          }}
        >
          <Ionicons name="bulb" size={iconSize.xs} color={colors.accent.primary} />
          <Text
            style={{
              ...typography.smallBold,
              color: colors.accent.primary,
            }}
          >
            {hint}
          </Text>
        </View>
      ) : null}
      {action ? (
        <View style={{ marginTop: spacing.lg }}>
          <Button
            variant={action.variant ?? "primary"}
            onPress={action.onPress}
          >
            {action.label}
          </Button>
        </View>
      ) : null}
    </View>
  );
}
