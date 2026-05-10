/**
 * YourKitchenEntryCard — always-visible row entry on Home that opens the
 * personal-canon view (PRD §4.13).
 *
 * The Your Kitchen screen is the primary browsing surface per PRD §4.13, but
 * `OrderDinnerHero` (the no-cook variant of NextBestAction) was previously
 * the only home entry into it — invisible to households with a cook. This
 * card sits below the hero on every household so the canon is discoverable
 * regardless of ICP, without crowding the single-CTA hero rule.
 *
 * Renders one of three states:
 *   1. Has canon       — "12 loved dishes · 3 saved" with a heart icon
 *   2. Day-zero        — "Build your household's dish canon"
 *   3. Loading         — skeleton-style placeholder with no count
 *
 * Tap routes to /your-kitchen. The screen handles its own day-zero band so
 * we don't need to special-case the empty state in the route — just always
 * show this entry.
 */

import React, { useMemo } from "react";
import { Pressable, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { router } from "expo-router";

import {
  cardStyles,
  colors,
  iconSize,
  radius,
  spacing,
  typography,
} from "@/lib/theme";
import { useYourKitchen } from "@/lib/your-kitchen-api";

export function YourKitchenEntryCard() {
  const canon = useYourKitchen();

  const summary = useMemo(() => {
    if (canon.isLoading) return "Loading your canon…";
    if (canon.isError) return "The dishes your household actually loves";

    const data = canon.data;
    if (!data) return "The dishes your household actually loves";

    if (!data.has_canon) {
      return "Build your household's dish canon";
    }

    const totalLoved = data.sections
      .filter((s) => s.id === "loved_by_everyone")
      .reduce((acc, s) => acc + s.dishes.length, 0);
    const saved = data.sections
      .filter((s) => s.id === "saved")
      .reduce((acc, s) => acc + s.dishes.length, 0);
    const total = data.total_dishes;

    const parts: string[] = [];
    // Prefer the most concrete signal first: how big is the canon overall?
    parts.push(`${total} ${total === 1 ? "dish" : "dishes"}`);
    if (totalLoved > 0) parts.push(`${totalLoved} loved`);
    if (saved > 0) parts.push(`${saved} saved`);
    return parts.join(" · ");
  }, [canon.isLoading, canon.isError, canon.data]);

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel="Open Your Kitchen — your household's dish canon"
      testID="your-kitchen-entry"
      onPress={() => router.push("/your-kitchen" as never)}
      style={{
        ...cardStyles,
        backgroundColor: colors.surface.card,
        borderColor: colors.border.subtle,
        paddingVertical: spacing.md,
        paddingHorizontal: spacing.md,
        flexDirection: "row",
        alignItems: "center",
        gap: spacing.md,
        marginTop: spacing.md,
      }}
    >
      <View
        style={{
          width: 40,
          height: 40,
          borderRadius: radius.pill,
          backgroundColor: colors.accent.primaryDim,
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <Ionicons name="bookmark" size={iconSize.sm} color={colors.accent.primary} />
      </View>

      <View style={{ flex: 1 }}>
        <Text style={{ ...typography.bodyBold, color: colors.text.primary }} numberOfLines={1}>
          Your Kitchen
        </Text>
        <Text
          style={{ ...typography.small, color: colors.text.secondary, marginTop: 2 }}
          numberOfLines={1}
        >
          {summary}
        </Text>
      </View>

      <Ionicons name="chevron-forward" size={iconSize.sm} color={colors.text.secondary} />
    </Pressable>
  );
}
