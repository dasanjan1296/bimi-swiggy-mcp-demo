/**
 * MemberDietCard — one row per household member capturing the two diet
 * inputs that actually drive Bimi's safety behaviour:
 *
 *   1. Diet preset (Veg / Eggetarian / Non-veg) — three big tap targets.
 *   2. Allergies / aversions — chip multi-select from a curated list.
 *
 * No free text, no comma-separated input. The previous flow asked
 * "allergies (comma-separated)?" and shipped the typed string back as a
 * preference — that's both a typo magnet and worse than useless for the
 * MealSuggestion safety filter, which pattern-matches against
 * canonical ingredient names. Chips fix both problems.
 *
 * Used inside step 2 of the onboarding flow. The parent owns state and
 * passes it down — the card is presentational only.
 */

import React from "react";
import { View, Text } from "react-native";
import { RipplePressable } from "../RipplePressable";
import { Avatar, Pill } from "../ui";
import { colors, radius, spacing, typography } from "@/lib/theme";
import type { DietPreset } from "@/lib/store";
import { COMMON_ALLERGIES_AND_AVOIDS } from "@/lib/onboarding-data";

export interface MemberDietCardProps {
  memberId: string;
  memberName: string;
  preset: DietPreset;
  allergies: string[];
  onPresetChange: (preset: DietPreset) => void;
  onAllergiesChange: (allergies: string[]) => void;
}

const PRESETS: { value: DietPreset; label: string; sublabel: string }[] = [
  { value: "veg",         label: "Veg",         sublabel: "No meat, no egg" },
  { value: "eggetarian",  label: "+ Eggs",      sublabel: "Veg + eggs only" },
  { value: "non_veg",     label: "Non-veg",     sublabel: "Anything goes" },
];

export function MemberDietCard({
  memberId,
  memberName,
  preset,
  allergies,
  onPresetChange,
  onAllergiesChange,
}: MemberDietCardProps) {
  const toggleAllergy = (item: string) => {
    onAllergiesChange(
      allergies.includes(item) ? allergies.filter((a) => a !== item) : [...allergies, item],
    );
  };

  return (
    <View
      style={{
        backgroundColor: colors.surface.elevated,
        borderRadius: radius.lg,
        padding: spacing.lg,
        borderWidth: 1,
        borderColor: colors.border.subtle,
        gap: spacing.md,
      }}
    >
      {/* Identity row */}
      <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
        <Avatar name={memberName} id={memberId} size="md" />
        <View style={{ flex: 1 }}>
          <Text style={typography.h3} numberOfLines={1}>{memberName}</Text>
          <Text style={typography.small}>What do they eat?</Text>
        </View>
      </View>

      {/* Diet preset — 3 big tap-cards in a row */}
      <View style={{ flexDirection: "row", gap: spacing.sm }}>
        {PRESETS.map((p) => {
          const selected = preset === p.value;
          return (
            <RipplePressable
              key={p.value}
              onPress={() => onPresetChange(p.value)}
              haptic="selection"
              accessibilityRole="radio"
              accessibilityLabel={`${p.label} for ${memberName}`}
              accessibilityState={{ selected }}
              style={{
                flex: 1,
                minHeight: 60,
                paddingHorizontal: spacing.sm,
                paddingVertical: spacing.sm,
                borderRadius: radius.md,
                borderWidth: 1,
                borderColor: selected ? colors.border.active : colors.border.subtle,
                backgroundColor: selected ? colors.surface.card : colors.surface.base,
                alignItems: "center",
                justifyContent: "center",
                gap: 2,
              }}
            >
              <Text style={typography.bodyBold}>{p.label}</Text>
              <Text
                style={{ ...typography.tiny, textAlign: "center" }}
                numberOfLines={2}
              >
                {p.sublabel}
              </Text>
            </RipplePressable>
          );
        })}
      </View>

      {/* Allergies chip cloud */}
      <View style={{ gap: spacing.xs }}>
        <Text style={typography.captionBold}>Anything they can't eat?</Text>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.xs }}>
          {COMMON_ALLERGIES_AND_AVOIDS.map((item) => {
            const selected = allergies.includes(item);
            return (
              <Pill
                key={item}
                tone="primary"
                size="xs"
                active={selected}
                onPress={() => toggleAllergy(item)}
                trailingIcon={selected ? "close-circle" : undefined}
              >
                {item}
              </Pill>
            );
          })}
        </View>
      </View>
    </View>
  );
}
