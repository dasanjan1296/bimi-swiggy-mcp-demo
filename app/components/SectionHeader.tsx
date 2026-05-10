/**
 * SectionHeader — uniform header for grouped dish sections on the catalog.
 *
 * Matches Swiggy's information architecture: a title, an optional subtitle,
 * and an optional trailing action ("See all" / "View filters").
 */

import React from "react";
import { Pressable, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";

import {
  colors,
  iconSize,
  spacing,
  typography,
} from "@/lib/theme";

export function SectionHeader({
  title,
  subtitle,
  actionLabel,
  onAction,
  icon,
}: {
  title: string;
  subtitle?: string;
  actionLabel?: string;
  onAction?: () => void;
  icon?: keyof typeof Ionicons.glyphMap;
}) {
  return (
    <View
      style={{
        flexDirection: "row",
        alignItems: "flex-end",
        justifyContent: "space-between",
        marginBottom: spacing.md,
        marginTop: spacing.lg,
      }}
    >
      <View style={{ flex: 1, flexDirection: "row", alignItems: "center", gap: 8 }}>
        {icon ? (
          <Ionicons name={icon} size={iconSize.md} color={colors.accent.primary} />
        ) : null}
        <View style={{ flex: 1 }}>
          <Text style={{ ...typography.h2, color: colors.text.primary }}>{title}</Text>
          {subtitle ? (
            <Text style={{ ...typography.small, color: colors.text.secondary }}>
              {subtitle}
            </Text>
          ) : null}
        </View>
      </View>
      {actionLabel && onAction ? (
        <Pressable
          onPress={onAction}
          accessibilityRole="button"
          accessibilityLabel={actionLabel}
          hitSlop={8}
          style={{
            flexDirection: "row",
            alignItems: "center",
            gap: 2,
            paddingVertical: 4,
            paddingHorizontal: 8,
          }}
        >
          <Text
            style={{
              ...typography.small,
              fontWeight: "600",
              color: colors.accent.primary,
            }}
          >
            {actionLabel}
          </Text>
          <Ionicons
            name="chevron-forward"
            size={iconSize.xs}
            color={colors.accent.primary}
          />
        </Pressable>
      ) : null}
    </View>
  );
}
