/**
 * SectionEyebrow — small uppercase label above section content.
 * Replaces the ad-hoc `{ fontSize: 11, fontWeight: 700, letterSpacing: 1, textTransform: "uppercase" }`
 * pattern repeated in PlanVisualization, BookingReviewSheet, instacook.tsx.
 */

import React from "react";
import { Text, TextStyle, ViewStyle, View } from "react-native";
import { colors, fontFamily, spacing } from "@/lib/theme";

export interface SectionEyebrowProps {
  children: React.ReactNode;
  tone?: "muted" | "secondary" | "primary";
  style?: TextStyle;
  /** Adds a margin-bottom after the label. */
  spaced?: boolean;
}

export function SectionEyebrow({ children, tone = "secondary", style, spaced = true }: SectionEyebrowProps) {
  const color =
    tone === "primary" ? colors.accent.primary :
    tone === "muted" ? colors.text.muted :
    colors.text.secondary;

  const textStyle: TextStyle = {
    fontSize: 11,
    fontWeight: "700",
    fontFamily: fontFamily.bold,
    color,
    letterSpacing: 1,
    textTransform: "uppercase",
    marginBottom: spaced ? spacing.sm : 0,
    ...style,
  };

  return <Text style={textStyle}>{children}</Text>;
}
