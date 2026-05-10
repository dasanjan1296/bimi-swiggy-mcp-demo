/**
 * DishGridCard — compact two-column grid cell used inside category sections
 * on the catalog. Shows a square photo (ribbon badge optional), dish name,
 * inspired-by byline, price, and savings pill in a tight vertical stack.
 *
 * Width is computed by the parent so the grid gutters stay consistent.
 */

import React from "react";
import { Image, Pressable, Text, View } from "react-native";

import {
  colors,
  radius,
  spacing,
  typography,
} from "@/lib/theme";
import { API_HOST } from "@/lib/api";
import { getDishImage } from "@/lib/dish-images";
// 2026-05-03 audit: SavingsBadge removed alongside the Bimi Gold UI.
// The "saved ₹X vs Swiggy" mechanic depended on the deleted savings/
// membership backend.
import { RibbonBadge, type RibbonVariant } from "@/components/RibbonBadge";
import type { Dish } from "@/lib/dish-api";

// 2026-05-03 audit: portion_tiers + swiggy savings + isGold pricing
// were Bimi Gold concepts. The recipe-archive backend doesn't carry
// per-tier prices. Cards now show the cook-time line only.
function DishGridCardImpl({
  dish,
  width,
  onPress,
  ribbon,
}: {
  dish: Dish;
  width: number;
  /** Receives the dish slug so the handler can be a stable ref at the
   *  call site (no per-cell arrow lambda needed — preserves memo). */
  onPress: (slug: string) => void;
  ribbon?: RibbonVariant;
  /** Legacy prop accepted for backwards-compat with existing callers
   *  (dish-catalog.tsx still threads `isGold` through). Always ignored. */
  isGold?: boolean;
}) {
  const local = getDishImage(dish.slug);
  const remoteUri =
    dish.image_url && !dish.image_url.startsWith("http")
      ? `${API_HOST}${dish.image_url}`
      : dish.image_url;
  const source = local !== undefined ? local : remoteUri ? { uri: remoteUri } : null;

  // Bind the dish slug to the parent's stable handler. The wrapper is
  // recreated each render but it lives inside the memoised cell, so
  // upstream refs stay stable and React.memo skips the re-render.
  const handlePress = () => onPress(dish.slug);

  return (
    <Pressable
      onPress={handlePress}
      accessibilityRole="button"
      accessibilityLabel={`Open ${dish.name}`}
      testID={`grid-dish-${dish.slug}`}
      style={{
        width,
        borderRadius: radius.md,
        overflow: "hidden",
        backgroundColor: colors.surface.card,
        borderWidth: 1,
        borderColor: colors.border.subtle,
      }}
    >
      <View
        style={{
          width: "100%",
          aspectRatio: 1,
          backgroundColor: colors.accent.primaryDim,
        }}
      >
        {source ? (
          <Image
            source={source as never}
            style={{ width: "100%", height: "100%" }}
            resizeMode="cover"
            // Parent Pressable already announces "Open {dish name}", so
            // VoiceOver should treat the image as decorative and not
            // double-focus it as an unlabelled element.
            accessible={false}
            accessibilityIgnoresInvertColors
          />
        ) : (
          <View style={{ flex: 1, alignItems: "center", justifyContent: "center" }}>
            <Text style={{ fontSize: 48 }}>🍽️</Text>
          </View>
        )}
        {ribbon ? <RibbonBadge variant={ribbon} /> : null}
        <VegDotAbsolute isVeg={dish.is_veg} />
      </View>

      <View style={{ padding: spacing.sm, gap: 2 }}>
        <Text
          style={{ ...typography.small, fontWeight: "700", color: colors.text.primary }}
          numberOfLines={1}
        >
          {dish.name}
        </Text>
        <Text
          style={{ ...typography.tiny, color: colors.text.secondary }}
          numberOfLines={1}
        >
          ~{dish.base_time_minutes} min
        </Text>
      </View>
    </Pressable>
  );
}

/**
 * Memoised so the catalog grid doesn't re-render every cell when the
 * parent's search/filter state changes (only the visible cells should
 * change). Dish ref + width + ribbon are stable enough that React.memo's
 * shallow comparison is the right default.
 */
export const DishGridCard = React.memo(DishGridCardImpl);

function VegDotAbsolute({ isVeg }: { isVeg: boolean }) {
  const color = isVeg ? colors.accent.success : colors.accent.danger;
  return (
    <View
      style={{
        position: "absolute",
        right: 8,
        bottom: 8,
        width: 16,
        height: 16,
        backgroundColor: colors.text.contrast,
        borderRadius: 3,
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <View
        style={{
          width: 12,
          height: 12,
          borderWidth: 1.5,
          borderColor: color,
          borderRadius: 2,
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <View
          style={{
            width: 5,
            height: 5,
            borderRadius: 2.5,
            backgroundColor: color,
          }}
        />
      </View>
    </View>
  );
}
