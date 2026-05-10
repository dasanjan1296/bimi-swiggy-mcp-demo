/**
 * TopBanner — sticky / inline top banner with semantic tone, optional action,
 * optional accessibility live region.
 *
 * Backs OfflineBanner; reusable for "Sync in progress", "Update available",
 * "Vote closing in 2 hours", etc.
 */

import React from "react";
import { View, Text, AccessibilityInfo, ViewStyle } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, spacing, typography, iconSize as iconSizes } from "@/lib/theme";
import { TextLink } from "./TextLink";
import type { PillTone } from "./Pill";

export interface TopBannerProps {
  tone?: PillTone;
  leadingIcon?: keyof typeof Ionicons.glyphMap;
  message: string;
  /** Optional inline action (e.g., "Retry"). */
  actionLabel?: string;
  onAction?: () => void;
  /** When true, also announce the message via VoiceOver/TalkBack. */
  announce?: boolean;
  style?: ViewStyle;
}

function colorsFor(tone: PillTone) {
  switch (tone) {
    case "success":  return { bg: colors.accent.successDim, fg: colors.accent.success };
    case "warning":  return { bg: colors.accent.warningDim, fg: colors.accent.warning };
    case "danger":   return { bg: colors.accent.dangerDim,  fg: colors.accent.danger };
    case "info":     return { bg: colors.accent.infoDim,    fg: colors.accent.info };
    case "ai":       return { bg: colors.accent.aiDim,      fg: colors.accent.ai };
    case "primary":  return { bg: colors.accent.primaryDim, fg: colors.accent.primary };
    case "neutral":
    default:         return { bg: colors.surface.elevated,  fg: colors.text.secondary };
  }
}

export function TopBanner({
  tone = "info",
  leadingIcon,
  message,
  actionLabel,
  onAction,
  announce = false,
  style,
}: TopBannerProps) {
  const c = colorsFor(tone);

  React.useEffect(() => {
    if (announce) AccessibilityInfo.announceForAccessibility?.(message);
  }, [announce, message]);

  return (
    <View
      accessibilityRole={"alert" as any}
      accessibilityLiveRegion={announce ? "polite" : "none"}
      accessibilityLabel={message}
      style={{
        backgroundColor: c.bg,
        flexDirection: "row",
        alignItems: "center",
        justifyContent: "center",
        gap: spacing.sm,
        paddingVertical: 6,
        paddingHorizontal: spacing.md,
        ...style,
      }}
    >
      {leadingIcon && <Ionicons name={leadingIcon} size={iconSizes.xs} color={c.fg} />}
      <Text style={{ ...typography.tiny, color: c.fg, fontWeight: "600", flexShrink: 1 }} numberOfLines={2}>
        {message}
      </Text>
      {actionLabel && onAction && <TextLink onPress={onAction} size="sm" tone="secondary">{actionLabel}</TextLink>}
    </View>
  );
}
