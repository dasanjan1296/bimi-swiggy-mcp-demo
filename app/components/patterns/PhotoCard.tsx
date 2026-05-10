/**
 * PhotoCard — image-led content card. Modeled on Airbnb's listing cards:
 * a confident photo, optional ribbon overlay, optional badge in the top
 * corner, and a short text block beneath.
 *
 * Used by the new image-led MealCard, FeaturedDishCard, HouseholdDishCard,
 * and any "dish / member / promo" surface that should foreground imagery.
 *
 * Design rules:
 *   - Photo radius matches card radius (radius.xl by default — 20).
 *   - Aspect ratio defaults to 16/9; opt into 1/1 for grid cells.
 *   - One ribbon, one badge per card. No stacked overlays.
 *   - Title is typography.h3 (16/600). Subtitle is typography.caption.
 */

import React from "react";
import {
  Image,
  ImageSourcePropType,
  Text,
  View,
  ViewStyle,
} from "react-native";
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

export interface PhotoCardRibbon {
  label: string;
  tone?: "primary" | "success" | "warning" | "danger" | "info" | "neutral";
}

export interface PhotoCardBadge {
  /** "veg" / "non-veg" classic dot, or a custom icon name. */
  kind: "veg" | "non-veg" | "icon";
  icon?: keyof typeof Ionicons.glyphMap;
}

export interface PhotoCardProps {
  image?: ImageSourcePropType;
  /** Aspect ratio of the photo block. Defaults to 16/9. */
  aspectRatio?: number;
  title: string;
  subtitle?: string;
  /** Optional small label rendered top-left over the photo. */
  ribbon?: PhotoCardRibbon;
  /** Optional indicator rendered top-right over the photo. */
  badge?: PhotoCardBadge;
  /** Tap handler — when set, the entire card becomes pressable. */
  onPress?: () => void;
  /** Width override. Default: full container width. */
  width?: number | string;
  /** Optional content slot rendered between the photo and the title (rare). */
  beforeTitle?: React.ReactNode;
  /** Optional content slot rendered after the title block. */
  afterTitle?: React.ReactNode;
  /** Hide the text block — useful for pure-photo grid cells. */
  textless?: boolean;
  style?: ViewStyle;
  accessibilityLabel?: string;
  testID?: string;
}

function ribbonColors(tone: NonNullable<PhotoCardRibbon["tone"]>) {
  switch (tone) {
    case "success": return { bg: colors.accent.success, fg: colors.text.inverse };
    case "warning": return { bg: colors.accent.warning, fg: colors.text.contrast };
    case "danger":  return { bg: colors.accent.danger,  fg: colors.text.inverse };
    case "info":    return { bg: colors.accent.info,    fg: colors.text.inverse };
    case "neutral": return { bg: colors.text.primary,   fg: colors.text.inverse };
    case "primary":
    default:        return { bg: colors.accent.primary, fg: colors.text.inverse };
  }
}

export function PhotoCard({
  image,
  aspectRatio = 16 / 9,
  title,
  subtitle,
  ribbon,
  badge,
  onPress,
  width = "100%",
  beforeTitle,
  afterTitle,
  textless = false,
  style,
  accessibilityLabel,
  testID,
}: PhotoCardProps) {
  const containerStyle: ViewStyle = {
    width: width as ViewStyle["width"],
    borderRadius: radius.xl,
    overflow: "hidden",
    backgroundColor: colors.surface.elevated,
    ...elevation.low,
    ...style,
  };

  const Photo = (
    <View
      style={{
        width: "100%",
        aspectRatio,
        backgroundColor: colors.accent.primaryDim,
      }}
    >
      {image ? (
        <Image source={image} style={{ width: "100%", height: "100%" }} resizeMode="cover" />
      ) : (
        <View style={{ flex: 1, alignItems: "center", justifyContent: "center" }}>
          <Ionicons name="restaurant-outline" size={iconSize.xl} color={colors.text.muted} />
        </View>
      )}

      {ribbon && (
        <View
          style={{
            position: "absolute",
            top: spacing.sm,
            left: spacing.sm,
            paddingHorizontal: spacing.sm + 2,
            paddingVertical: 4,
            borderRadius: radius.sm,
            backgroundColor: ribbonColors(ribbon.tone ?? "primary").bg,
          }}
        >
          <Text
            style={{
              ...typography.tinyBold,
              color: ribbonColors(ribbon.tone ?? "primary").fg,
              letterSpacing: 0.5,
              textTransform: "uppercase",
            }}
            numberOfLines={1}
          >
            {ribbon.label}
          </Text>
        </View>
      )}

      {badge && (
        <View
          style={{
            position: "absolute",
            top: spacing.sm,
            right: spacing.sm,
            backgroundColor: colors.surface.base,
            borderRadius: 4,
            padding: 3,
            ...elevation.low,
          }}
        >
          {badge.kind === "veg" || badge.kind === "non-veg" ? (
            <View
              style={{
                width: 10,
                height: 10,
                borderRadius: 5,
                backgroundColor:
                  badge.kind === "veg" ? colors.accent.success : colors.accent.danger,
              }}
            />
          ) : badge.icon ? (
            <Ionicons name={badge.icon} size={iconSize.xs} color={colors.text.primary} />
          ) : null}
        </View>
      )}
    </View>
  );

  const TextBlock = textless ? null : (
    <View style={{ padding: spacing.md, gap: 2 }}>
      {beforeTitle}
      <Text style={typography.h3} numberOfLines={2}>{title}</Text>
      {subtitle ? (
        <Text style={{ ...typography.caption }} numberOfLines={2}>
          {subtitle}
        </Text>
      ) : null}
      {afterTitle}
    </View>
  );

  if (onPress) {
    return (
      <RipplePressable
        onPress={onPress}
        haptic="selection"
        accessibilityRole="button"
        accessibilityLabel={accessibilityLabel ?? title}
        testID={testID}
        style={containerStyle}
      >
        {Photo}
        {TextBlock}
      </RipplePressable>
    );
  }

  return (
    <View style={containerStyle} testID={testID}>
      {Photo}
      {TextBlock}
    </View>
  );
}
