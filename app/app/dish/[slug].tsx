/**
 * Dish (recipe) detail — read-only view.
 *
 * 2026-05-03 audit (FRONTEND-BACKEND-COORDINATION.md):
 * The previous detail screen was a "buy this dish" flow with portion
 * stepper, price breakdown, Bimi Gold upsell, savings badge, and
 * add-to-cart CTA. Per founder decisions:
 *   - "No Insta Cook for now" → no in-app dish ordering
 *   - "Delete UI" for Bimi Gold → no membership / pricing
 *   - "Dish Catalog and Recipe Archive are sort of the same"
 *     → this screen is now a read-only recipe browse target
 *
 * The Bimi Recipes catalog (formerly dish-catalog.tsx) deep-links here
 * via `/dish/{slug}` to show what the dish is. Queueing it for the
 * cook lives on the Your Kitchen tab via /your-kitchen/queue (existing
 * backend endpoint).
 */

import React from "react";
import {
  ActivityIndicator,
  Image,
  Pressable,
  ScrollView,
  Text,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { fetchDish, type Dish } from "@/lib/dish-api";
import { API_HOST } from "@/lib/api";
import { getDishImage } from "@/lib/dish-images";
import { safeBack } from "@/lib/safe-back";
import {
  cardStyles,
  colors,
  iconSize,
  radius,
  spacing,
  typography,
} from "@/lib/theme";

export default function DishDetailScreen() {
  const params = useLocalSearchParams<{ slug: string }>();
  const slug = params.slug ?? "";

  const dishQuery = useQuery<Dish>({
    queryKey: ["dish", slug],
    queryFn: () => fetchDish(slug),
    enabled: !!slug,
  });

  if (dishQuery.isLoading) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.surface.base, alignItems: "center", justifyContent: "center" }}>
        <ActivityIndicator color={colors.accent.primary} />
      </View>
    );
  }

  if (!dishQuery.data) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.surface.base, padding: spacing.xl, paddingTop: 80 }}>
        <Text style={typography.h2}>Recipe not found</Text>
        <Pressable onPress={() => safeBack()} style={{ marginTop: spacing.lg }}>
          <Text style={{ color: colors.accent.primary }}>Go back</Text>
        </Pressable>
      </View>
    );
  }

  const dish = dishQuery.data;
  const imageSrc = dish.image_url
    ? dish.image_url.startsWith("http")
      ? dish.image_url
      : `${API_HOST}${dish.image_url}`
    : getDishImage(dish.slug);

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface.base }}>
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ paddingTop: 60, paddingBottom: 60 }}
      >
        <View style={{ paddingHorizontal: spacing.lg, marginBottom: spacing.md }}>
          <Pressable
            onPress={() => safeBack()}
            accessibilityRole="button"
            accessibilityLabel="Back"
            style={{ flexDirection: "row", alignItems: "center", gap: 4 }}
          >
            <Ionicons name="chevron-back" size={iconSize.md} color={colors.text.primary} />
            <Text style={{ ...typography.caption, color: colors.text.primary }}>Recipes</Text>
          </Pressable>
        </View>

        {imageSrc ? (
          <Image
            source={typeof imageSrc === "string" ? { uri: imageSrc } : imageSrc}
            style={{
              width: "100%",
              height: 240,
              backgroundColor: colors.surface.card,
            }}
            resizeMode="cover"
          />
        ) : (
          <View
            style={{
              width: "100%",
              height: 240,
              backgroundColor: colors.surface.card,
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <Text style={{ fontSize: 64 }}>🍽️</Text>
          </View>
        )}

        <View style={{ padding: spacing.lg, gap: spacing.lg }}>
          <View>
            <Text style={typography.h1}>{dish.name}</Text>
            {dish.description ? (
              <Text style={{ ...typography.body, color: colors.text.secondary, marginTop: spacing.xs }}>
                {dish.description}
              </Text>
            ) : null}
          </View>

          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.md }}>
            <MetaChip icon="time" text={`~${dish.base_time_minutes ?? 30} min`} />
            <MetaChip icon="restaurant" text={(dish.cuisine ?? "indian").replace(/_/g, " ")} />
            {dish.is_veg ? (
              <MetaChip icon="leaf" text="Veg" />
            ) : (
              <MetaChip icon="nutrition" text="Non-veg" />
            )}
          </View>

          {/* Read-only ingredients section if the recipe has them. */}
          {Array.isArray((dish as any).ingredients) && (dish as any).ingredients.length > 0 ? (
            <View style={cardStyles}>
              <Text style={{ ...typography.bodyBold, marginBottom: spacing.sm }}>
                Ingredients
              </Text>
              {((dish as any).ingredients as Array<{ name: string; quantity?: string }>).map(
                (ing, i) => (
                  <Text
                    key={i}
                    style={{
                      ...typography.body,
                      color: colors.text.secondary,
                      marginBottom: 2,
                    }}
                  >
                    • {ing.name}
                    {ing.quantity ? ` — ${ing.quantity}` : ""}
                  </Text>
                ),
              )}
            </View>
          ) : null}
        </View>
      </ScrollView>
    </View>
  );
}

function MetaChip({ icon, text }: { icon: keyof typeof Ionicons.glyphMap; text: string }) {
  return (
    <View
      style={{
        flexDirection: "row",
        alignItems: "center",
        gap: 6,
        paddingHorizontal: 10,
        paddingVertical: 6,
        borderRadius: radius.pill,
        backgroundColor: colors.surface.card,
      }}
    >
      <Ionicons name={icon} size={iconSize.xs} color={colors.text.secondary} />
      <Text style={{ ...typography.small, color: colors.text.secondary }}>{text}</Text>
    </View>
  );
}
