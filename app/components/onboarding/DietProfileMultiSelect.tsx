/**
 * DietProfileMultiSelect — household-level diet facets, replacing the
 * per-member 3-button "Veg / Eggetarian / Non-veg" cards from the
 * previous flow.
 *
 * Why per-member was wrong for India: a Bangalore Hindu household
 * almost always has the same diet rules at the table level — pure veg,
 * eggs ok, no onion-garlic, no beef. Per-member nuance comes up later
 * (the kid hates karela, dad is diabetic) but isn't a Day-1 question.
 *
 * What this captures that the old flow missed:
 *   • "Non-veg weekends only" (huge cohort — South Indian Hindu families)
 *   • "No onion / garlic" sattvik (Brahmin households especially)
 *   • "No beef" / "No pork" religious constraints
 *   • "Jain" — no roots, no allium
 *
 * Facets compose freely (you can pick "Eggs ok" + "Non-veg weekends" +
 * "No beef" simultaneously) and the host commit step folds them into
 * a per-member DietaryPreference[] for safety filtering.
 *
 * The two facet groups (`veg` and `nonveg_cadence`) are mutually
 * exclusive within group: tapping "Pure vegetarian" deselects "Eggs
 * ok"; tapping "Non-veg weekends" deselects "Non-veg any day".
 */

import React from "react";
import { View, Text } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { RipplePressable } from "../RipplePressable";
import { Pill } from "../ui";
import { colors, iconSize, radius, spacing, typography } from "@/lib/theme";
import {
  DIET_PROFILE_OPTIONS,
  COMMON_ALLERGIES,
  type DietFacetOption,
} from "@/lib/onboarding-data";
import type { DietFacet } from "@/lib/store";

export interface DietProfileMultiSelectProps {
  selectedFacets: DietFacet[];
  selectedAllergies: string[];
  onToggleFacet: (f: DietFacet) => void;
  onToggleAllergy: (a: string) => void;
  /** Commit handler used to enforce within-group mutual exclusion. */
  onReplaceFacets?: (facets: DietFacet[]) => void;
}

export function DietProfileMultiSelect({
  selectedFacets,
  selectedAllergies,
  onToggleFacet,
  onToggleAllergy,
  onReplaceFacets,
}: DietProfileMultiSelectProps) {
  const handleFacetPress = (opt: DietFacetOption) => {
    if (!opt.group || !onReplaceFacets) {
      onToggleFacet(opt.value);
      return;
    }
    // Within-group: replace any sibling facet with this one (or remove
    // if tapping an already-selected one).
    const siblings = DIET_PROFILE_OPTIONS.filter((o) => o.group === opt.group).map((o) => o.value);
    const without = selectedFacets.filter((f) => !siblings.includes(f));
    if (selectedFacets.includes(opt.value)) {
      onReplaceFacets(without);
    } else {
      onReplaceFacets([...without, opt.value]);
    }
  };

  return (
    <View style={{ gap: spacing.xl }}>
      <View style={{ gap: spacing.sm }}>
        <Text style={typography.captionBold}>How does your house eat?</Text>
        {DIET_PROFILE_OPTIONS.map((opt) => (
          <DietRow
            key={opt.value}
            opt={opt}
            isOn={selectedFacets.includes(opt.value)}
            onPress={() => handleFacetPress(opt)}
          />
        ))}
      </View>

      <View style={{ gap: spacing.sm }}>
        <Text style={typography.captionBold}>Anyone allergic? Tap what's true.</Text>
        <Text style={{ ...typography.small, marginTop: -spacing.xs }}>
          I'll never put these in any suggestion. No exceptions.
        </Text>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.xs, marginTop: spacing.xs }}>
          {COMMON_ALLERGIES.map((a) => (
            <Pill
              key={a}
              tone="primary"
              size="xs"
              active={selectedAllergies.includes(a)}
              onPress={() => onToggleAllergy(a)}
              trailingIcon={selectedAllergies.includes(a) ? "close-circle" : undefined}
            >
              {a}
            </Pill>
          ))}
        </View>
      </View>
    </View>
  );
}

function DietRow({
  opt,
  isOn,
  onPress,
}: {
  opt: DietFacetOption;
  isOn: boolean;
  onPress: () => void;
}) {
  return (
    <RipplePressable
      onPress={onPress}
      haptic="selection"
      accessibilityRole="checkbox"
      accessibilityLabel={opt.label}
      accessibilityState={{ checked: isOn }}
      style={{
        flexDirection: "row",
        alignItems: "center",
        gap: spacing.md,
        paddingHorizontal: spacing.md,
        paddingVertical: spacing.md,
        borderRadius: radius.md,
        borderWidth: 1,
        borderColor: isOn ? colors.border.active : colors.border.subtle,
        backgroundColor: isOn ? colors.surface.card : colors.surface.elevated,
      }}
    >
      <View
        style={{
          width: 22,
          height: 22,
          borderRadius: 4,
          borderWidth: 2,
          borderColor: isOn ? colors.text.primary : colors.border.subtle,
          backgroundColor: isOn ? colors.text.primary : "transparent",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {isOn && <Ionicons name="checkmark" size={iconSize.xs} color={colors.text.inverse} />}
      </View>
      <Text style={{ ...typography.body, flex: 1 }}>{opt.label}</Text>
    </RipplePressable>
  );
}
