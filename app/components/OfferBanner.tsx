/**
 * OfferBanner — dismissible hero banner for promos (first-dinner credit,
 * Gold upsell, festival offers). Swiggy-style: a small colored card with
 * bold copy, a rupee/value callout, and an optional CTA.
 *
 * Keep the copy short — this is a glance-and-tap surface, not a pitch.
 */

import React from "react";
import { Pressable, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";

import {
  colors,
  iconSize,
  radius,
  spacing,
  typography,
} from "@/lib/theme";

export type OfferBannerVariant = "credit" | "gold" | "festival";

const VARIANT_STYLES: Record<
  OfferBannerVariant,
  { bg: string; accent: string; icon: keyof typeof Ionicons.glyphMap }
> = {
  credit: {
    bg: "rgba(52,211,153,0.12)",
    accent: colors.accent.success,
    icon: "gift",
  },
  gold: {
    bg: "rgba(251,191,36,0.14)",
    accent: colors.accent.warning,
    icon: "star",
  },
  festival: {
    bg: "rgba(224,122,95,0.14)",
    accent: colors.accent.secondary,
    icon: "sparkles",
  },
};

export function OfferBanner({
  variant,
  title,
  subtitle,
  highlight,
  onPress,
  onDismiss,
}: {
  variant: OfferBannerVariant;
  title: string;
  subtitle: string;
  highlight?: string;
  onPress?: () => void;
  onDismiss?: () => void;
}) {
  const style = VARIANT_STYLES[variant];
  const Container = onPress ? Pressable : View;

  return (
    <Container
      onPress={onPress}
      accessibilityRole={onPress ? "button" : undefined}
      accessibilityLabel={`${title}. ${subtitle}`}
      style={{
        backgroundColor: style.bg,
        borderWidth: 1,
        borderColor: `${style.accent}33`,
        borderRadius: radius.md,
        padding: spacing.md,
        flexDirection: "row",
        alignItems: "center",
        gap: spacing.md,
        marginBottom: spacing.md,
      }}
    >
      <View
        style={{
          width: 40,
          height: 40,
          borderRadius: 20,
          backgroundColor: `${style.accent}22`,
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <Ionicons name={style.icon} size={iconSize.md} color={style.accent} />
      </View>

      <View style={{ flex: 1 }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
          <Text
            style={{ ...typography.bodyBold, color: style.accent }}
            numberOfLines={1}
          >
            {title}
          </Text>
          {highlight ? (
            <Text
              style={{
                ...typography.tiny,
                color: colors.text.inverse,
                backgroundColor: style.accent,
                paddingHorizontal: 6,
                paddingVertical: 2,
                borderRadius: radius.sm,
                overflow: "hidden",
                fontWeight: "700",
              }}
            >
              {highlight}
            </Text>
          ) : null}
        </View>
        <Text
          style={{ ...typography.small, color: colors.text.secondary, marginTop: 2 }}
          numberOfLines={2}
        >
          {subtitle}
        </Text>
      </View>

      {onPress ? (
        <Ionicons
          name="chevron-forward"
          size={iconSize.sm}
          color={style.accent}
        />
      ) : null}
      {onDismiss ? (
        <Pressable
          onPress={onDismiss}
          hitSlop={8}
          accessibilityLabel="Dismiss offer"
          style={{ padding: 4 }}
        >
          <Ionicons name="close" size={iconSize.sm} color={colors.text.muted} />
        </Pressable>
      ) : null}
    </Container>
  );
}
