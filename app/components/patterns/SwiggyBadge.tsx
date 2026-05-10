/**
 * SwiggyBadge — three-mode visual attribution for the Swiggy MCP
 * integration surface (home hero pill, sheet header, footer CTA glyph).
 *
 *   <SwiggyBadge size="pill"   />  → "■ Powered by Swiggy" — hero pill
 *   <SwiggyBadge size="inline" />  → mark + "swiggy" wordmark — sheet header
 *   <SwiggyBadge size="cta"    />  → mark on a white pad — footer CTA
 *
 * Brand asset: `app/assets/brand/swiggy-mark.png` (the orange rounded
 * "S" pin mark). The wordmark is rendered in text since no separate
 * wordmark asset is on disk yet.
 *
 * Brand colour `#FC8019` (Swiggy orange) is the reference for the
 * footer CTA background — keep them in sync.
 */

import React from "react";
import { Image, Text, View } from "react-native";
import { colors, spacing, typography } from "@/lib/theme";

export const SWIGGY_ORANGE = "#FC8019";

const SWIGGY_MARK = require("@/assets/brand/swiggy-mark.png");

type SwiggyBadgeSize = "pill" | "inline" | "cta";

interface SwiggyBadgeProps {
  size: SwiggyBadgeSize;
}

export function SwiggyBadge({ size }: SwiggyBadgeProps) {
  if (size === "pill") {
    // Tasteful corner attribution for the home hero card.
    return (
      <View
        style={{
          flexDirection: "row",
          alignItems: "center",
          gap: 4,
          paddingHorizontal: 6,
          paddingVertical: 2,
          borderRadius: 999,
          backgroundColor: colors.surface.base,
        }}
      >
        <Image
          source={SWIGGY_MARK}
          resizeMode="contain"
          style={{ width: 12, height: 12 }}
        />
        <Text
          style={{
            ...typography.tiny,
            color: colors.text.secondary,
            letterSpacing: 0.2,
          }}
        >
          Powered by{" "}
          <Text style={{ color: SWIGGY_ORANGE, fontWeight: "700" }}>swiggy</Text>
        </Text>
      </View>
    );
  }

  if (size === "cta") {
    // White circular pad keeps the orange-on-orange mark legible
    // against the SWIGGY_ORANGE footer-button background.
    return (
      <View
        style={{
          width: 22,
          height: 22,
          borderRadius: 11,
          backgroundColor: colors.surface.base,
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <Image
          source={SWIGGY_MARK}
          resizeMode="contain"
          style={{ width: 18, height: 18 }}
        />
      </View>
    );
  }

  // inline (default): mark + wordmark side-by-side for the sheet header.
  return (
    <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.xs }}>
      <Image
        source={SWIGGY_MARK}
        resizeMode="contain"
        style={{ width: 18, height: 18 }}
      />
      <Text
        style={{
          ...typography.bodyBold,
          color: SWIGGY_ORANGE,
          letterSpacing: -0.3,
        }}
      >
        swiggy
      </Text>
    </View>
  );
}
