/**
 * CuisineTraditionPicker — multi-select tap cards for the household's
 * cooking tradition(s). Picked up during onboarding step 2.
 *
 * Why this matters: a Tamil–Punjabi couple in Bangalore (a wildly
 * common cohort) needs Bimi to alternate suggestions; otherwise one
 * partner gets shafted constantly. The previous flow had no way to
 * capture this and ranked all suggestions identically for everyone.
 *
 * UI choice: card-shaped pills (not chip pills) because each option
 * carries a sub-line — "Punjabi, Awadhi, Mughlai" etc. The sub-line is
 * load-bearing; without it "North Indian" is meaningless to a
 * non-foodie.
 */

import React from "react";
import { View, Text } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { RipplePressable } from "../RipplePressable";
import { colors, iconSize, radius, spacing, typography } from "@/lib/theme";
import { CUISINE_TRADITIONS, type CuisineOption } from "@/lib/onboarding-data";
import type { CuisineTradition } from "@/lib/store";

export interface CuisineTraditionPickerProps {
  selected: CuisineTradition[];
  onToggle: (t: CuisineTradition) => void;
}

export function CuisineTraditionPicker({ selected, onToggle }: CuisineTraditionPickerProps) {
  return (
    <View style={{ gap: spacing.sm }}>
      {CUISINE_TRADITIONS.map((opt) => (
        <CuisineRow
          key={opt.value}
          opt={opt}
          isOn={selected.includes(opt.value)}
          onPress={() => onToggle(opt.value)}
        />
      ))}
    </View>
  );
}

function CuisineRow({
  opt,
  isOn,
  onPress,
}: {
  opt: CuisineOption;
  isOn: boolean;
  onPress: () => void;
}) {
  return (
    <RipplePressable
      onPress={onPress}
      haptic="selection"
      accessibilityRole="checkbox"
      accessibilityLabel={`${opt.label}, ${opt.blurb}`}
      accessibilityState={{ checked: isOn }}
      style={{
        flexDirection: "row",
        alignItems: "center",
        gap: spacing.md,
        padding: spacing.lg,
        borderRadius: radius.lg,
        borderWidth: 1,
        borderColor: isOn ? colors.border.active : colors.border.subtle,
        backgroundColor: isOn ? colors.surface.card : colors.surface.elevated,
      }}
    >
      <Text style={{ fontSize: 24, lineHeight: 28 }} accessibilityElementsHidden>
        {opt.emoji}
      </Text>
      <View style={{ flex: 1, gap: 2 }}>
        <Text style={typography.bodyBold}>{opt.label}</Text>
        <Text style={typography.small} numberOfLines={1}>{opt.blurb}</Text>
      </View>
      <Ionicons
        name={isOn ? "checkmark-circle" : "ellipse-outline"}
        size={iconSize.lg}
        color={isOn ? colors.accent.success : colors.text.muted}
      />
    </RipplePressable>
  );
}
