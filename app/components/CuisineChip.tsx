/**
 * CuisineChip — Swiggy-style cuisine filter pill with a colored icon bubble.
 *
 * Three modes:
 *   - Active (the current cuisine filter) — filled amber background, inverse text.
 *   - Inactive — glass surface, secondary text, colored icon bubble.
 *   - "All" variant — special first chip with a "compass" icon and no cuisine tint.
 *
 * The tiny count to the right helps users see where the density is
 * without tapping through every cuisine.
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

export type CuisineId =
  | "all"
  | "north_indian"
  | "bengali"
  | "south_indian"
  | "hyderabadi";

type CuisineMeta = {
  label: string;
  emoji: string;
  tintKey: keyof typeof colors.cuisine;
};

export const CUISINE_META: Record<CuisineId, CuisineMeta> = {
  all: { label: "All", emoji: "🍽️", tintKey: "all" },
  north_indian: { label: "North Indian", emoji: "🫓", tintKey: "north_indian" },
  bengali: { label: "Bengali", emoji: "🐟", tintKey: "bengali" },
  south_indian: { label: "South Indian", emoji: "🥥", tintKey: "south_indian" },
  hyderabadi: { label: "Hyderabadi", emoji: "🍚", tintKey: "hyderabadi" },
};

export function CuisineChip({
  cuisine,
  active,
  count,
  onPress,
}: {
  cuisine: CuisineId;
  active: boolean;
  count?: number;
  onPress: () => void;
}) {
  const meta = CUISINE_META[cuisine];
  const bubbleColor = colors.cuisine[meta.tintKey];

  return (
    <Pressable
      onPress={onPress}
      accessibilityState={{ selected: active }}
      accessibilityLabel={`${meta.label}${count !== undefined ? `, ${count} dishes` : ""}`}
      style={{
        flexDirection: "row",
        alignItems: "center",
        gap: 8,
        paddingLeft: 6,
        paddingRight: 14,
        paddingVertical: 6,
        borderRadius: radius.pill,
        borderWidth: 1,
        borderColor: active ? colors.accent.primary : colors.border.subtle,
        backgroundColor: active ? colors.accent.primary : colors.surface.card,
      }}
    >
      <View
        style={{
          width: 28,
          height: 28,
          borderRadius: 14,
          backgroundColor: active ? "rgba(255,255,255,0.22)" : bubbleColor,
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {cuisine === "all" ? (
          <Ionicons
            name="compass"
            size={iconSize.sm}
            color={active ? colors.text.inverse : colors.accent.primary}
          />
        ) : (
          <Text style={{ fontSize: 14 }}>{meta.emoji}</Text>
        )}
      </View>
      <Text
        style={{
          ...typography.small,
          fontWeight: "600",
          color: active ? colors.text.inverse : colors.text.primary,
        }}
      >
        {meta.label}
      </Text>
      {count !== undefined && count > 0 ? (
        <Text
          style={{
            ...typography.tiny,
            color: active ? colors.text.inverse : colors.text.muted,
            marginLeft: -2,
          }}
        >
          {count}
        </Text>
      ) : null}
    </Pressable>
  );
}
