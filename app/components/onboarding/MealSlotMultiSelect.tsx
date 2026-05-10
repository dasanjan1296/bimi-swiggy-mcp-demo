/**
 * MealSlotMultiSelect — three big toggle cards (Breakfast / Lunch /
 * Dinner) for "which meals do you actually want Bimi to orchestrate?".
 *
 * Why three cards instead of three pills: the answer to this question
 * defines half of what Bimi does for the household. A 1-burner PG
 * student who only wants dinner suggestions should never see a "vote
 * for breakfast" prompt. Burying that decision inside a chip row on the
 * cook step would understate it; promoting it to its own grouped UI
 * with a one-line "what this means" preview makes the impact obvious.
 *
 * The component refuses to leave the user with zero selected slots —
 * tapping the last selected slot is a no-op (handled by the store). The
 * UI just visually doesn't toggle, no error toast.
 */

import React from "react";
import { View, Text } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { RipplePressable } from "../RipplePressable";
import { colors, radius, spacing, typography, iconSize } from "@/lib/theme";

export type SlotKey = "breakfast" | "lunch" | "dinner";

interface SlotMeta {
  key: SlotKey;
  label: string;
  icon: keyof typeof import("@expo/vector-icons").Ionicons.glyphMap;
  defaultTime: string;
  preview: string;
}

const SLOTS: SlotMeta[] = [
  { key: "breakfast", label: "Breakfast", icon: "sunny-outline",  defaultTime: "8:30 AM",  preview: "Quick · everyday" },
  { key: "lunch",     label: "Lunch",     icon: "restaurant-outline", defaultTime: "1:30 PM", preview: "Tiffins · home-cooked" },
  { key: "dinner",    label: "Dinner",    icon: "moon-outline",   defaultTime: "8:00 PM",  preview: "The main event" },
];

export interface MealSlotMultiSelectProps {
  selected: SlotKey[];
  onToggle: (key: SlotKey) => void;
}

export function MealSlotMultiSelect({ selected, onToggle }: MealSlotMultiSelectProps) {
  return (
    <View style={{ gap: spacing.sm }}>
      {SLOTS.map((slot) => {
        const isOn = selected.includes(slot.key);
        const isLastOn = isOn && selected.length === 1;
        return (
          <RipplePressable
            key={slot.key}
            onPress={() => onToggle(slot.key)}
            haptic="selection"
            accessibilityRole="checkbox"
            accessibilityLabel={`${slot.label}, ${slot.defaultTime}`}
            accessibilityState={{ checked: isOn, disabled: isLastOn }}
            accessibilityHint={isLastOn ? "Cannot deselect the last meal" : undefined}
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
            <View
              style={{
                width: 40,
                height: 40,
                borderRadius: 20,
                backgroundColor: isOn ? colors.text.primary : colors.surface.card,
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <Ionicons
                name={slot.icon}
                size={iconSize.md}
                color={isOn ? colors.text.inverse : colors.text.secondary}
              />
            </View>

            <View style={{ flex: 1 }}>
              <Text style={typography.bodyBold}>{slot.label}</Text>
              <Text style={typography.small}>
                {slot.defaultTime} · {slot.preview}
              </Text>
            </View>

            <Ionicons
              name={isOn ? "checkmark-circle" : "ellipse-outline"}
              size={iconSize.lg}
              color={isOn ? colors.accent.success : colors.text.muted}
            />
          </RipplePressable>
        );
      })}
    </View>
  );
}
