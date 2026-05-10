/**
 * CalloutCard — semantic info/warning/success/danger box used for inline notes
 * and short banners that aren't long enough to warrant a full screen takeover.
 *
 * Replaces ~10 inline bordered/tinted card patterns across PlanVisualization,
 * BookingReviewSheet, MealCard, InlineBookingCard.PairingSuggestionCard, etc.
 */

import React from "react";
import { View, Text, ViewStyle } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, cardStyles, radius, spacing, typography, iconSize } from "@/lib/theme";
import type { PillTone } from "./Pill";

export interface CalloutCardProps {
  tone?: PillTone;
  leadingIcon?: keyof typeof Ionicons.glyphMap;
  /** Small uppercase eyebrow above the title. */
  eyebrow?: string;
  title?: string;
  children?: React.ReactNode;
  /** When set, renders a colored left strip instead of a full border. */
  accentLeft?: boolean;
  style?: ViewStyle;
}

function colorsFor(tone: PillTone) {
  switch (tone) {
    case "success":  return { bg: colors.accent.successDim, fg: colors.accent.success, border: colors.accent.success };
    case "warning":  return { bg: colors.accent.warningDim, fg: colors.accent.warning, border: colors.accent.warning };
    case "danger":   return { bg: colors.accent.dangerDim,  fg: colors.accent.danger,  border: colors.accent.danger };
    case "info":     return { bg: colors.accent.infoDim,    fg: colors.accent.info,    border: colors.accent.info };
    case "ai":       return { bg: colors.accent.aiDim,      fg: colors.accent.ai,      border: colors.accent.ai };
    case "primary":  return { bg: colors.accent.primaryDim, fg: colors.accent.primary, border: colors.accent.primary };
    case "neutral":
    default:         return { bg: colors.surface.card,      fg: colors.text.secondary, border: colors.border.subtle };
  }
}

export function CalloutCard({
  tone = "info",
  leadingIcon,
  eyebrow,
  title,
  children,
  accentLeft = false,
  style,
}: CalloutCardProps) {
  const c = colorsFor(tone);

  const containerStyle: ViewStyle = accentLeft
    ? {
        ...cardStyles,
        borderLeftWidth: 4,
        borderLeftColor: c.border,
        ...style,
      }
    : {
        ...cardStyles,
        backgroundColor: c.bg,
        borderColor: c.border,
        borderWidth: 1,
        borderRadius: radius.lg,
        ...style,
      };

  return (
    <View style={containerStyle}>
      {(eyebrow || leadingIcon || title) && (
        <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, marginBottom: children ? spacing.xs : 0 }}>
          {leadingIcon && <Ionicons name={leadingIcon} size={iconSize.md} color={c.fg} />}
          <View style={{ flex: 1 }}>
            {eyebrow && (
              <Text style={{ ...typography.smallBold, color: c.fg, textTransform: "uppercase", letterSpacing: 1 }}>
                {eyebrow}
              </Text>
            )}
            {title && <Text style={{ ...typography.bodyBold }}>{title}</Text>}
          </View>
        </View>
      )}
      {typeof children === "string" ? (
        <Text style={{ ...typography.caption, color: colors.text.secondary }}>{children}</Text>
      ) : (
        children
      )}
    </View>
  );
}
