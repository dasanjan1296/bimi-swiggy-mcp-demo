/**
 * BurnerStove — visual stove illustration with 1, 2, 3, or 4 burners.
 * Tap a burner-count card; the rendered stove updates to match. The
 * onboarding flow uses this in place of asking "how many burners?" as
 * a numeric question — recognition beats recall, and Indian users with
 * limited app-form fluency parse a stove drawing instantly.
 *
 * The "stove" is rendered with primitives only (View + Ionicons flame
 * glyph) so we don't ship an SVG dependency. The active burner ring
 * color is `border.active` (#222) — same selected-state grammar as the
 * Pill atom; we never use Rausch for selection (see design-system.md
 * §Color hard rules).
 */

import React from "react";
import { View, Text } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { RipplePressable } from "../RipplePressable";
import { colors, radius, spacing, typography, iconSize } from "@/lib/theme";

export type BurnerCount = 1 | 2 | 3 | 4;

export interface BurnerStoveProps {
  value: BurnerCount;
  onChange: (n: BurnerCount) => void;
}

const OPTIONS: { value: BurnerCount; label: string; sublabel: string }[] = [
  { value: 1, label: "1 burner", sublabel: "Studio · PG" },
  { value: 2, label: "2 burners", sublabel: "Most flats" },
  { value: 3, label: "3 burners", sublabel: "Larger kitchen" },
  { value: 4, label: "4 burners", sublabel: "Family kitchen" },
];

export function BurnerStove({ value, onChange }: BurnerStoveProps) {
  return (
    <View style={{ gap: spacing.lg }}>
      {/* Stove preview — the visual anchor. Updates as the user taps. */}
      <View
        style={{
          backgroundColor: colors.surface.card,
          borderRadius: radius.xl,
          padding: spacing.xl,
          alignItems: "center",
        }}
        accessibilityElementsHidden
        importantForAccessibility="no-hide-descendants"
      >
        <StovePreview burners={value} />
      </View>

      {/* Picker — 2x2 grid */}
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
        {OPTIONS.map((opt) => {
          const selected = value === opt.value;
          return (
            <RipplePressable
              key={opt.value}
              onPress={() => onChange(opt.value)}
              haptic="selection"
              accessibilityRole="radio"
              accessibilityLabel={`${opt.label}, ${opt.sublabel}`}
              accessibilityState={{ selected }}
              style={{
                flexBasis: "48%",
                flexGrow: 1,
                minHeight: 64,
                paddingHorizontal: spacing.md,
                paddingVertical: spacing.md,
                borderRadius: radius.md,
                borderWidth: 1,
                borderColor: selected ? colors.border.active : colors.border.subtle,
                backgroundColor: selected ? colors.surface.card : colors.surface.base,
                alignItems: "flex-start",
                justifyContent: "center",
                gap: 2,
              }}
            >
              <Text style={typography.bodyBold}>{opt.label}</Text>
              <Text style={typography.small}>{opt.sublabel}</Text>
            </RipplePressable>
          );
        })}
      </View>
    </View>
  );
}

/**
 * Renders the burner grid. We use the cooking-flame icon in
 * `accent.warning` for "lit" and a subtle gray ring for unlit, so the
 * stove looks alive even at the 1-burner end. Burners always render
 * in a 2x2 grid with the unused ones grayed out — this matters because
 * a 1-burner kitchen is still recognisably a stove, not a single dot.
 */
function StovePreview({ burners }: { burners: BurnerCount }) {
  const cells: { idx: number; lit: boolean }[] = [
    { idx: 0, lit: burners >= 1 },
    { idx: 1, lit: burners >= 2 },
    { idx: 2, lit: burners >= 3 },
    { idx: 3, lit: burners >= 4 },
  ];
  const STOVE_W = 220;
  const STOVE_H = 140;

  return (
    <View
      style={{
        width: STOVE_W,
        height: STOVE_H,
        borderRadius: radius.lg,
        backgroundColor: colors.surface.elevated,
        borderWidth: 1,
        borderColor: colors.border.subtle,
        padding: spacing.md,
      }}
    >
      <View
        style={{
          flex: 1,
          flexDirection: "row",
          flexWrap: "wrap",
          justifyContent: "space-between",
          alignContent: "space-between",
        }}
      >
        {cells.map((c) => (
          <BurnerCell key={c.idx} lit={c.lit} />
        ))}
      </View>
    </View>
  );
}

function BurnerCell({ lit }: { lit: boolean }) {
  const D = 48;
  return (
    <View
      style={{
        width: D,
        height: D,
        borderRadius: D / 2,
        borderWidth: 2,
        borderColor: lit ? colors.text.primary : colors.border.subtle,
        backgroundColor: lit ? colors.surface.card : colors.surface.elevated,
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <Ionicons
        name="flame"
        size={iconSize.md}
        color={lit ? colors.accent.warning : colors.text.muted}
      />
    </View>
  );
}
