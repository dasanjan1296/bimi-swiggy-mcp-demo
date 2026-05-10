/**
 * BandHeader — the "TODAY" / "TOMORROW" / "THIS WEEK" section divider used
 * on home and several other screens. Small accent strip on the left, an
 * uppercase eyebrow label, and a hairline rule that fills the remaining
 * width.
 *
 * If you just need a small uppercase label without the rule, use
 * `<SectionEyebrow>` from `components/ui` instead.
 */

import React from "react";
import { Text, View, ViewStyle } from "react-native";
import { colors, radius, spacing, typography } from "@/lib/theme";

export interface BandHeaderProps {
  label: string;
  /** Optional pill rendered at the right end (e.g., COOK OFF). */
  trailing?: React.ReactNode;
  /** Tone of the leading accent strip. Defaults to primary (Rausch). */
  tone?: "primary" | "neutral";
  style?: ViewStyle;
}

export function BandHeader({
  label,
  trailing,
  tone = "primary",
  style,
}: BandHeaderProps) {
  const stripColor =
    tone === "primary" ? colors.accent.primary : colors.text.muted;

  return (
    <View
      style={[
        {
          flexDirection: "row",
          alignItems: "center",
          gap: spacing.sm,
        },
        style,
      ]}
    >
      <View
        style={{
          width: 4,
          height: 14,
          borderRadius: 2,
          backgroundColor: stripColor,
        }}
      />
      <Text
        style={{
          ...typography.smallBold,
          color: colors.text.muted,
          textTransform: "uppercase",
          letterSpacing: 1.2,
          fontSize: 11,
        }}
      >
        {label}
      </Text>
      <View
        style={{
          flex: 1,
          height: 1,
          backgroundColor: colors.divider.default,
          marginLeft: spacing.sm,
        }}
      />
      {trailing}
    </View>
  );
}
