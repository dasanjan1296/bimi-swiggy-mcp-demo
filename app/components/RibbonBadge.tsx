/**
 * RibbonBadge — tiny corner ribbon drawn over a dish card hero image.
 *
 * Four semantic variants: bestseller (coral), chef's pick (violet),
 * quick (mint, for sub-30-min dishes), and new (gold). All use the
 * same geometry so a card's layout never shifts as the variant changes.
 *
 * The variant decision lives in [app/app/dish-catalog.tsx] where we can
 * see the whole catalog at once; this component is dumb-by-design.
 */

import React from "react";
import { Text, View } from "react-native";

import { colors, fontFamily, radius } from "@/lib/theme";

export type RibbonVariant = "bestseller" | "chef_pick" | "quick" | "new";

const LABELS: Record<RibbonVariant, string> = {
  bestseller: "BESTSELLER",
  chef_pick: "CHEF'S PICK",
  quick: "QUICK",
  new: "NEW",
};

const COLORS: Record<RibbonVariant, { bg: string; fg: string }> = {
  bestseller: { bg: colors.ribbon.bestsellerBg, fg: colors.ribbon.bestsellerFg },
  chef_pick: { bg: colors.ribbon.chefPickBg, fg: colors.ribbon.chefPickFg },
  quick: { bg: colors.ribbon.quickBg, fg: colors.ribbon.quickFg },
  new: { bg: colors.ribbon.newBg, fg: colors.ribbon.newFg },
};

export function RibbonBadge({
  variant,
  style,
}: {
  variant: RibbonVariant;
  style?: object;
}) {
  const palette = COLORS[variant];
  return (
    <View
      style={[
        {
          position: "absolute",
          top: 8,
          left: 8,
          paddingHorizontal: 8,
          paddingVertical: 3,
          borderRadius: radius.pill,
          backgroundColor: palette.bg,
          // subtle shadow so the ribbon reads on bright parts of the hero photo
          shadowColor: colors.shadow.default,
          shadowOffset: { width: 0, height: 1 },
          shadowOpacity: 0.25,
          shadowRadius: 2,
          elevation: 2,
        },
        style ?? {},
      ]}
      accessibilityLabel={LABELS[variant]}
    >
      <Text
        style={{
          fontSize: 9,
          fontFamily: fontFamily.extrabold,
          fontWeight: "800",
          letterSpacing: 0.6,
          color: palette.fg,
        }}
      >
        {LABELS[variant]}
      </Text>
    </View>
  );
}
