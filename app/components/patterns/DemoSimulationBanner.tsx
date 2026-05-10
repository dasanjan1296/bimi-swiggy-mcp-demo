/**
 * DemoSimulationBanner — persistent disclaimer shown on every Swiggy
 * lifecycle surface (cart sheet, active delivery hero, tracking sheet,
 * delivered hero) so the viewer always knows the values they're
 * looking at are illustrative, not live Swiggy data.
 *
 * Why: Swiggy MCP Builders Club rules forbid "misrepresenting prices,
 * availability, or delivery times" and "dark patterns / deceptive UX
 * / misattributing where data comes from"
 * (https://mcp.swiggy.com/builders/access/). Until MCP access is
 * granted, every numeric claim we make about Swiggy is invented; the
 * banner makes that fact unmissable.
 *
 * Two layouts:
 *   - "inline": small italic line for body content (cart sheet between
 *     attribution + first card; below a HeroCard).
 *   - "header": thin full-width band sitting under a BottomSheet header.
 */

import React from "react";
import { Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, radius, spacing, typography } from "@/lib/theme";

const COPY = "Demo simulation — live values when Swiggy MCP is connected";

interface DemoSimulationBannerProps {
  variant?: "inline" | "header";
}

export function DemoSimulationBanner({
  variant = "inline",
}: DemoSimulationBannerProps) {
  if (variant === "header") {
    return (
      <View
        style={{
          backgroundColor: colors.surface.elevated,
          paddingVertical: spacing.sm,
          paddingHorizontal: spacing.lg,
          flexDirection: "row",
          alignItems: "center",
          gap: spacing.xs,
        }}
      >
        <Ionicons
          name="information-circle-outline"
          size={14}
          color={colors.text.secondary}
        />
        <Text
          style={{
            ...typography.caption,
            color: colors.text.secondary,
            flex: 1,
          }}
          numberOfLines={2}
        >
          {COPY}
        </Text>
      </View>
    );
  }

  return (
    <View
      style={{
        flexDirection: "row",
        alignItems: "center",
        gap: spacing.xs,
        paddingVertical: spacing.xs,
        paddingHorizontal: spacing.sm,
        borderRadius: radius.sm,
        backgroundColor: colors.surface.elevated,
      }}
    >
      <Ionicons
        name="information-circle-outline"
        size={12}
        color={colors.text.muted}
      />
      <Text
        style={{
          ...typography.tiny,
          color: colors.text.muted,
          fontStyle: "italic",
          flex: 1,
        }}
        numberOfLines={2}
      >
        {COPY}
      </Text>
    </View>
  );
}
