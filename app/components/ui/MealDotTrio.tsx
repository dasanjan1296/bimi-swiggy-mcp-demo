/**
 * MealDotTrio — three small dots that summarise the breakfast / lunch
 * / dinner decisions for a single day at a glance. A filled dot means
 * "decided"; a hollow dot means "not yet". The vocabulary is shared
 * across:
 *
 *   - The wheel-of-meals sectors (compact, one tone per day's label).
 *   - The wheel-of-meals centre card (larger, Rausch fill).
 *   - The wheel-of-meals legend ("Meals planned" row).
 *   - The meals-history calendar cells.
 *
 * Historically each surface re-implemented the trio inline, and the
 * four copies drifted on width / radius / gap / fill colour — the
 * meals-history copy was 5×5 with a `text.secondary` fill, which was
 * neither the wheel's `accent.primary` nor its `success` per-sector
 * tone. This atom is the single source of truth.
 *
 * Sizing tiers:
 *   - `sm` (6×6, gap 4): wheel sectors + dense cells like calendar.
 *   - `md` (8×8, gap 6): centre card + legend swatch — the canonical
 *     "you can see this from across the room" rendering.
 */

import React from "react";
import { View, ViewStyle } from "react-native";
import { colors } from "@/lib/theme";

export type MealDotTrioSize = "sm" | "md";

export interface MealDotTrioProps {
  /** Length-3 array, one per meal in MEAL_DOT_ORDER (breakfast/lunch/
   *  dinner). `true` = decided (filled), `false` = undecided (hollow). */
  filled: [boolean, boolean, boolean];
  /** Default `md`. Use `sm` for dense surfaces. */
  size?: MealDotTrioSize;
  /** Override the filled-dot colour. Defaults to `colors.accent.primary`.
   *  The wheel uses the per-sector label colour for visual cohesion. */
  filledColor?: string;
  /** Override container style (margin tweaks for nested layouts). */
  style?: ViewStyle;
}

interface SizeSpec {
  diameter: number;
  gap: number;
  borderWidth: number;
}

const SIZE_SPECS: Record<MealDotTrioSize, SizeSpec> = {
  sm: { diameter: 6, gap: 4, borderWidth: 1.2 },
  md: { diameter: 8, gap: 6, borderWidth: 1.5 },
};

export function MealDotTrio({
  filled,
  size = "md",
  filledColor,
  style,
}: MealDotTrioProps) {
  const spec = SIZE_SPECS[size];
  const fill = filledColor ?? colors.accent.primary;
  // `alignSelf` is intentionally NOT set here — the trio inherits
  // alignment from its parent's `alignItems`. Centred parents (the
  // wheel's centre card, the legend swatch slot, the wheel sector
  // label area) get the trio centred; left-aligned parents (the
  // meals-history calendar cell, where `alignItems: "flex-start"` is
  // set on the cell container) get it left-aligned. An earlier
  // version baked `alignSelf: "flex-start"` into the default to
  // prevent the trio from stretching in column-flex parents — that
  // backfired on the centre card (the dots appeared shifted left of
  // "WED") because the override beat the parent's centring rule.
  return (
    <View
      style={[
        {
          flexDirection: "row",
          gap: spec.gap,
        },
        style,
      ]}
    >
      {filled.map((isFilled, idx) => (
        <View
          key={idx}
          style={{
            width: spec.diameter,
            height: spec.diameter,
            borderRadius: spec.diameter / 2,
            backgroundColor: isFilled ? fill : "transparent",
            borderWidth: isFilled ? 0 : spec.borderWidth,
            borderColor: colors.border.subtle,
          }}
        />
      ))}
    </View>
  );
}
