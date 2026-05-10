/**
 * CookOffPill — the canonical "OFF" badge that marks a day on which
 * the household's cook isn't coming. Two visual states:
 *
 *   - **Unresolved** (warning amber fill + border, amber text "OFF"):
 *     the user hasn't picked a fallback (self-cook / order / skip).
 *     Reads as a soft alert that something needs a decision.
 *   - **Resolved** (white fill, subtle border, muted text — usually
 *     showing the chosen fallback verb like "SELF" or "ORDER"): the
 *     amber relaxes into a neutral chip once the user has handled it.
 *
 * Lives in components/ui/ as an atom because three surfaces all need
 * it and historically each hand-rolled its own copy that drifted out
 * of sync (WheelOfMeals' `SectorOffPill`, WheelLegend's `OffPill`,
 * meals-history's inline rendering — the last one was at fontSize 8
 * with smaller padding / radius, breaking the strict "fontSize is on
 * the type scale" rule). Centralising it kills the drift.
 *
 * Sizing: the wheel sector + calendar cell both want a tight pill;
 * the legend + larger surfaces want a roomier one. One `size` prop
 * keeps the geometry consistent within each tier.
 */

import React from "react";
import { Text, View, ViewStyle } from "react-native";
import { colors, typography } from "@/lib/theme";

export type CookOffPillSize = "sm" | "md";

export interface CookOffPillProps {
  /** When true, render the calmer "decision-made" treatment. */
  resolved?: boolean;
  /** Override the pill text. Defaults to "OFF" (case is forced upper). */
  label?: string;
  /** Default `md`. Use `sm` inside dense surfaces (wheel sector). */
  size?: CookOffPillSize;
  /** Optional container style override (e.g. marginTop). */
  style?: ViewStyle;
}

interface SizeSpec {
  paddingHorizontal: number;
  paddingVertical: number;
  borderRadius: number;
}

const SIZE_SPECS: Record<CookOffPillSize, SizeSpec> = {
  sm: { paddingHorizontal: 5, paddingVertical: 1, borderRadius: 5 },
  md: { paddingHorizontal: 6, paddingVertical: 1, borderRadius: 6 },
};

export function CookOffPill({
  resolved = false,
  label = "OFF",
  size = "md",
  style,
}: CookOffPillProps) {
  const spec = SIZE_SPECS[size];
  const bg = resolved ? colors.surface.base : colors.accent.warningDim;
  const border = resolved ? colors.border.subtle : colors.accent.warning;
  const fg = resolved ? colors.text.muted : colors.accent.warning;

  // `alignSelf` is intentionally NOT set here — the pill inherits
  // alignment from its parent's `alignItems`. See the matching note
  // in MealDotTrio.tsx for the full reasoning. Parents that need the
  // pill left-aligned (the meals-history calendar cell) set
  // `alignItems: "flex-start"` on the cell container; centred parents
  // (the wheel's centre / sector / legend) get the pill centred.
  return (
    <View
      style={[
        {
          paddingHorizontal: spec.paddingHorizontal,
          paddingVertical: spec.paddingVertical,
          borderRadius: spec.borderRadius,
          backgroundColor: bg,
          borderWidth: 1,
          borderColor: border,
        },
        style,
      ]}
      accessibilityLabel={resolved ? `Cook off, ${label.toLowerCase()}` : "Cook is off"}
    >
      <Text
        style={{
          ...typography.tinyBold,
          color: fg,
          letterSpacing: 0.4,
          textTransform: "uppercase",
        }}
        numberOfLines={1}
      >
        {label}
      </Text>
    </View>
  );
}
