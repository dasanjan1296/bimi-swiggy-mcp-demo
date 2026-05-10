/**
 * HeroCard — single-CTA above-the-fold action card. The home screen's
 * "Next Best Action" lives in this shape. Strict rule: ONE primary CTA
 * per card, no secondary actions, no dismiss buttons. The user either
 * engages or scrolls past.
 *
 * Tones reuse the standard accent palette. The CTA style matches the
 * primary `<Button>` so the user reads the same visual cue across the
 * app — no per-screen flair.
 *
 * The CTA is OPTIONAL: omit both `ctaLabel` and `onPress` to render a
 * calm narration card with no chevron and no press handler. Used by
 * `<TodayMealStatusHero>` when the day is sorted and Bimi is just
 * announcing the plan ("Poha for breakfast — I'll ping you if anything's
 * off."). A chevron pointing at a CTA the user can't act on is a UX
 * lie — quietly omit it instead.
 */

import React from "react";
import { Text, View, ViewStyle } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { RipplePressable } from "../RipplePressable";
import {
  colors,
  elevation,
  iconSize,
  radius,
  spacing,
  typography,
} from "@/lib/theme";

export type HeroTone = "primary" | "success" | "warning" | "info" | "danger";

export interface HeroCardProps {
  tone?: HeroTone;
  icon: keyof typeof Ionicons.glyphMap;
  title: string;
  subtitle?: string;
  /** When omitted (alongside `onPress`), the card renders as a calm
   *  narration block — no CTA row, no chevron, no press affordance. */
  ctaLabel?: string;
  /** Required IFF `ctaLabel` is provided. */
  onPress?: () => void;
  /** Slot rendered to the right of the title (rare). */
  trailing?: React.ReactNode;
  /** Slot pinned to the card's top-right corner (e.g. "Powered by"
   *  attribution pill). Sits above the title row, doesn't affect
   *  the title/CTA layout. */
  topRight?: React.ReactNode;
  testID?: string;
  style?: ViewStyle;
}

function toneColors(tone: HeroTone) {
  switch (tone) {
    case "success":
      return { bg: colors.accent.successDim, accent: colors.accent.success };
    case "warning":
      return { bg: colors.accent.warningDim, accent: colors.accent.warning };
    case "info":
      return { bg: colors.accent.infoDim, accent: colors.accent.info };
    case "danger":
      // Light red — reserved for action-required heroes (e.g. cook
      // chat actions waiting for the user to approve). Distinct from
      // `warning` (amber) which we use for "off"/cook-absence states
      // that don't need an immediate ack.
      return { bg: colors.accent.dangerDim, accent: colors.accent.danger };
    case "primary":
    default:
      return { bg: colors.accent.primaryDim, accent: colors.accent.primary };
  }
}

export function HeroCard({
  tone = "primary",
  icon,
  title,
  subtitle,
  ctaLabel,
  onPress,
  trailing,
  topRight,
  testID,
  style,
}: HeroCardProps) {
  const t = toneColors(tone);
  const hasCta = !!ctaLabel && !!onPress;

  const cardStyle: ViewStyle = {
    backgroundColor: t.bg,
    borderRadius: radius.lg,
    padding: spacing.md,
    ...elevation.low,
    ...style,
  };

  const inner = (
    <View>
      {topRight ? (
        <View style={{ position: "absolute", top: 0, right: 0, zIndex: 1 }}>
          {topRight}
        </View>
      ) : null}
      <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
      <View
        style={{
          width: 40,
          height: 40,
          borderRadius: 20,
          backgroundColor: t.accent,
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <Ionicons name={icon} size={iconSize.sm} color={colors.text.inverse} />
      </View>

      <View style={{ flex: 1, gap: 2 }}>
        <Text style={typography.bodyBold} numberOfLines={1}>
          {title}
        </Text>
        {subtitle ? (
          <Text style={typography.caption} numberOfLines={2}>
            {subtitle}
          </Text>
        ) : null}
        {hasCta ? (
          <View
            style={{
              flexDirection: "row",
              alignItems: "center",
              gap: 4,
              marginTop: spacing.xs,
            }}
          >
            <Text
              style={{
                ...typography.tinyBold,
                color: t.accent,
                letterSpacing: 0.4,
                textTransform: "uppercase",
              }}
            >
              {ctaLabel}
            </Text>
            <Ionicons name="chevron-forward" size={iconSize.xs} color={t.accent} />
          </View>
        ) : null}
      </View>

      {trailing}
      </View>
    </View>
  );

  // No-CTA variant: render a static View with no press handler. Tapping
  // an obvious "card" surface that does nothing is worse than a card
  // that's clearly read-only by virtue of not being interactive.
  if (!hasCta) {
    return (
      <View
        style={cardStyle}
        testID={testID}
        accessibilityRole="text"
        accessibilityLabel={subtitle ? `${title}. ${subtitle}` : title}
      >
        {inner}
      </View>
    );
  }

  return (
    <RipplePressable
      onPress={onPress}
      haptic="selection"
      testID={testID}
      accessibilityRole="button"
      accessibilityLabel={`${title}. ${ctaLabel}`}
      style={cardStyle}
    >
      {inner}
    </RipplePressable>
  );
}
