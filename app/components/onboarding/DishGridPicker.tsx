/**
 * DishGridPicker — multi-select photo grid used in step 5 (cook
 * repertoire) and reusable for any "pick from a grid of bundled dish
 * photos" need.
 *
 * Key visual decisions:
 *
 *   • Photo cards are fixed 2-column. With our `radius.xl` photo
 *     radius and the 30 bundled JPEGs (compressed to 1200 px max), the
 *     grid feels like a Spotify playlist of dishes — recognisable at a
 *     glance, no copy needed.
 *
 *   • Selected state is a dark `border.active` ring + a Rausch
 *     check-circle in the corner. We do NOT tint the photo (no overlay,
 *     no opacity drop) — selected photos must remain identifiable.
 *
 *   • The selected count is rendered above the grid as a quiet running
 *     total ("4 picked"). No "min N" gate — the parent decides whether
 *     to enable Next based on count.
 */

import React from "react";
import { View, Text, Image } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { RipplePressable } from "../RipplePressable";
import { colors, radius, spacing, typography, iconSize } from "@/lib/theme";
import { getDishImage } from "@/lib/dish-images";
import type { OnboardingDish } from "@/lib/onboarding-data";

export interface DishGridPickerProps {
  dishes: OnboardingDish[];
  selectedSlugs: string[];
  onToggle: (slug: string) => void;
  /** Optional caption above the grid ("Pick what cook makes well"). */
  caption?: string;
}

export function DishGridPicker({ dishes, selectedSlugs, onToggle, caption }: DishGridPickerProps) {
  return (
    <View style={{ gap: spacing.md }}>
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "baseline" }}>
        {caption ? <Text style={typography.captionBold}>{caption}</Text> : <View />}
        <Text style={typography.small} accessibilityLiveRegion="polite">
          {selectedSlugs.length} picked
        </Text>
      </View>

      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
        {dishes.map((dish) => (
          <DishTile
            key={dish.slug}
            dish={dish}
            selected={selectedSlugs.includes(dish.slug)}
            onPress={() => onToggle(dish.slug)}
          />
        ))}
      </View>
    </View>
  );
}

function DishTile({
  dish,
  selected,
  onPress,
}: {
  dish: OnboardingDish;
  selected: boolean;
  onPress: () => void;
}) {
  const img = getDishImage(dish.slug);

  return (
    <RipplePressable
      onPress={onPress}
      haptic="selection"
      accessibilityRole="checkbox"
      accessibilityLabel={dish.name}
      accessibilityState={{ checked: selected }}
      style={{
        flexBasis: "48%",
        flexGrow: 1,
        borderRadius: radius.xl,
        overflow: "hidden",
        borderWidth: 2,
        borderColor: selected ? colors.border.active : colors.border.subtle,
        backgroundColor: colors.surface.card,
      }}
    >
      <View style={{ aspectRatio: 1, backgroundColor: colors.surface.card }}>
        {img ? (
          <Image
            source={img}
            resizeMode="cover"
            accessible={false}
            accessibilityIgnoresInvertColors
            style={{ width: "100%", height: "100%" }}
          />
        ) : (
          <View style={{ flex: 1, alignItems: "center", justifyContent: "center" }}>
            <Ionicons name="restaurant" size={iconSize.xl} color={colors.text.muted} />
          </View>
        )}

        {selected && (
          <View
            style={{
              position: "absolute",
              top: spacing.sm,
              right: spacing.sm,
              width: 28,
              height: 28,
              borderRadius: 14,
              backgroundColor: colors.accent.primary,
              alignItems: "center",
              justifyContent: "center",
            }}
            accessibilityElementsHidden
          >
            <Ionicons name="checkmark" size={iconSize.sm} color={colors.text.inverse} />
          </View>
        )}
      </View>

      <View style={{ padding: spacing.sm, gap: 2 }}>
        <Text style={typography.bodyBold} numberOfLines={1}>{dish.name}</Text>
        {dish.isVeg ? (
          <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
            <View
              style={{
                width: 10,
                height: 10,
                borderWidth: 1,
                borderColor: colors.accent.success,
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <View
                style={{
                  width: 5,
                  height: 5,
                  borderRadius: 3,
                  backgroundColor: colors.accent.success,
                }}
              />
            </View>
            <Text style={typography.tiny}>Veg</Text>
          </View>
        ) : (
          <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
            <View
              style={{
                width: 10,
                height: 10,
                borderWidth: 1,
                borderColor: colors.accent.danger,
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <View
                style={{
                  width: 5,
                  height: 5,
                  borderRadius: 3,
                  backgroundColor: colors.accent.danger,
                }}
              />
            </View>
            <Text style={typography.tiny}>Non-veg</Text>
          </View>
        )}
      </View>
    </RipplePressable>
  );
}
