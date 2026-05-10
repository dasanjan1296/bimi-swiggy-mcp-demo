/**
 * LearnedSummary — a quiet horizontal pill row that travels with the
 * user across steps, showing the answers Bimi has captured so far.
 *
 * The point: every screen reminds the user "you're not starting from
 * zero — here's what I've already filed away". Reduces the "am I done
 * yet?" anxiety that drives drop-off in step-by-step flows.
 *
 * Layout:
 *
 *   ──────────────────────────────────────────────────────
 *    Couple · Bangalore · South+North · 17 meals/wk
 *   ──────────────────────────────────────────────────────
 *
 * The pills are non-interactive in the onboarding flow (the user goes
 * back to edit by tapping the wizard back-arrow); making them tappable
 * here would create two competing back-navigation models.
 */

import React from "react";
import { View, Text } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, iconSize, radius, spacing, typography } from "@/lib/theme";

export interface LearnedItem {
  /** Short label — "Couple", "Bangalore", "Veg+eggs". Keep ≤ 16 chars. */
  label: string;
  icon?: keyof typeof Ionicons.glyphMap;
}

export interface LearnedSummaryProps {
  items: LearnedItem[];
}

export function LearnedSummary({ items }: LearnedSummaryProps) {
  if (items.length === 0) return null;
  return (
    <View
      style={{
        flexDirection: "row",
        flexWrap: "wrap",
        gap: spacing.xs,
        paddingVertical: spacing.sm,
      }}
      accessibilityLabel={`So far I know: ${items.map((i) => i.label).join(", ")}`}
    >
      {items.map((item, idx) => (
        <View
          key={idx}
          style={{
            flexDirection: "row",
            alignItems: "center",
            gap: 4,
            backgroundColor: colors.surface.card,
            borderRadius: radius.pill,
            paddingHorizontal: spacing.sm,
            paddingVertical: 4,
          }}
        >
          {item.icon && (
            <Ionicons name={item.icon} size={iconSize.xs} color={colors.text.secondary} />
          )}
          <Text style={{ ...typography.tinyBold, color: colors.text.secondary }}>
            {item.label}
          </Text>
        </View>
      ))}
    </View>
  );
}
