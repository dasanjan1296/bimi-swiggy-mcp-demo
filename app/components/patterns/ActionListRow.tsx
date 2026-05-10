/**
 * ActionListRow — list row + inline primary action button. Used by the
 * cook actions sheet, by inline approval lists, and by anywhere the user
 * needs to confirm/dismiss a single thing per row.
 *
 * The trailing slot accepts either a `ButtonAction` (which renders a
 * compact `<Button size="sm">`) or arbitrary React. Resolved rows render
 * a green check + strikethrough title (mirrors the cook chat bubble
 * pattern from before the redesign).
 */

import React from "react";
import { Text, View, ViewStyle } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { Button, type ButtonVariant } from "../ui/Button";
import {
  colors,
  iconSize,
  spacing,
  typography,
} from "@/lib/theme";

export interface ButtonAction {
  label: string;
  onPress: () => void;
  variant?: ButtonVariant;
  loading?: boolean;
  disabled?: boolean;
}

export interface ActionListRowProps {
  /** Ionicons name for the leading icon. */
  icon: keyof typeof Ionicons.glyphMap;
  /** Tint for the icon. Default neutral. */
  iconTone?: "primary" | "success" | "warning" | "danger" | "info" | "neutral";
  title: string;
  subtitle?: string;
  /** Resolved → row goes muted + strikethrough + green check. */
  resolved?: boolean;
  /** Primary action shown on the right at rest. */
  action?: ButtonAction;
  /** Secondary action shown on a second line under the action. */
  secondaryAction?: { label: string; onPress: () => void };
  style?: ViewStyle;
}

function iconColor(tone: NonNullable<ActionListRowProps["iconTone"]>) {
  switch (tone) {
    case "primary": return colors.accent.primary;
    case "success": return colors.accent.success;
    case "warning": return colors.accent.warning;
    case "danger":  return colors.accent.danger;
    case "info":    return colors.accent.info;
    case "neutral":
    default:        return colors.text.primary;
  }
}

export function ActionListRow({
  icon,
  iconTone = "neutral",
  title,
  subtitle,
  resolved = false,
  action,
  secondaryAction,
  style,
}: ActionListRowProps) {
  return (
    <View
      style={{
        flexDirection: "row",
        alignItems: "flex-start",
        gap: spacing.md,
        paddingVertical: spacing.md,
        ...style,
      }}
    >
      <View
        style={{
          width: 32,
          height: 32,
          borderRadius: 16,
          backgroundColor: resolved ? colors.accent.successDim : colors.surface.card,
          alignItems: "center",
          justifyContent: "center",
          marginTop: 2,
        }}
      >
        <Ionicons
          name={resolved ? "checkmark" : icon}
          size={iconSize.sm}
          color={resolved ? colors.accent.success : iconColor(iconTone)}
        />
      </View>

      <View style={{ flex: 1, gap: 2 }}>
        <Text
          style={{
            ...typography.h3,
            color: resolved ? colors.text.muted : colors.text.primary,
            textDecorationLine: resolved ? "line-through" : "none",
          }}
        >
          {title}
        </Text>
        {subtitle ? (
          <Text style={typography.caption} numberOfLines={3}>
            {subtitle}
          </Text>
        ) : null}
        {secondaryAction && !resolved ? (
          <Text
            style={{ ...typography.captionBold, color: colors.accent.primary, marginTop: 4 }}
            onPress={secondaryAction.onPress}
            accessibilityRole="link"
          >
            {secondaryAction.label}
          </Text>
        ) : null}
      </View>

      {action && !resolved ? (
        <Button
          variant={action.variant ?? "primary"}
          size="sm"
          onPress={action.onPress}
          loading={action.loading}
          disabled={action.disabled}
        >
          {action.label}
        </Button>
      ) : null}
    </View>
  );
}
