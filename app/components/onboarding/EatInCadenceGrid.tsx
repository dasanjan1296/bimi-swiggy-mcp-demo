/**
 * EatInCadenceGrid — 7-day x 3-meal grid that captures the household's
 * actual weekly eat-in pattern. Replaces the simpler "which meals do
 * you orchestrate?" multi-select.
 *
 * Why a grid: Bangalore working couples don't eat at home in a uniform
 * pattern. A typical answer is:
 *   • Mon-Thu: breakfast + dinner (skip lunch — office tiffin or
 *     ordered)
 *   • Fri: nothing (Friday eat-out night)
 *   • Sat: breakfast + lunch + dinner (recovery)
 *   • Sun: all three meals
 *
 * That's 14 home-cooked meals, scattered across 17 day-meal cells.
 * Encoding it as `["breakfast", "lunch", "dinner"]` collapses too much
 * and pushes Bimi into spamming "vote for Friday dinner!" prompts that
 * the household actively wants silenced.
 *
 * Tap-to-toggle. The grid uses a 7-column narrow layout (each day a
 * column, each meal a row) — fits one screen, doesn't scroll
 * horizontally on phones ≥ 360 px wide.
 *
 * Sticky default highlighted on first render: weekday dinners + all
 * weekend meals. Most users tap-tweak from there rather than start
 * from blank.
 */

import React from "react";
import { View, Text } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { RipplePressable } from "../RipplePressable";
import { colors, iconSize, radius, spacing, typography } from "@/lib/theme";
import {
  DAYS_OF_WEEK,
  DAY_LABELS_SHORT,
  MEAL_SLOTS_VERTICAL,
  MEAL_SLOT_LABELS,
  MEAL_SLOT_ICONS,
} from "@/lib/onboarding-data";

export interface EatInCadenceGridProps {
  cells: Record<string, boolean>;
  onToggle: (key: string) => void;
}

export function EatInCadenceGrid({ cells, onToggle }: EatInCadenceGridProps) {
  const total = Object.values(cells).filter(Boolean).length;

  return (
    <View style={{ gap: spacing.lg }}>
      {/* Day-of-week header row */}
      <View style={{ flexDirection: "row", paddingLeft: 88, gap: 4 }}>
        {DAY_LABELS_SHORT.map((d, i) => (
          <View key={i} style={{ flex: 1, alignItems: "center" }}>
            <Text style={{ ...typography.smallBold, color: colors.text.secondary }}>{d}</Text>
          </View>
        ))}
      </View>

      {/* 3 meal rows */}
      {MEAL_SLOTS_VERTICAL.map((slot) => (
        <View key={slot} style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
          {/* Meal label */}
          <View style={{ width: 84, flexDirection: "row", alignItems: "center", gap: spacing.xs }}>
            <Ionicons
              name={MEAL_SLOT_ICONS[slot] as keyof typeof Ionicons.glyphMap}
              size={iconSize.sm}
              color={colors.text.secondary}
            />
            <Text style={typography.captionBold}>{MEAL_SLOT_LABELS[slot]}</Text>
          </View>

          {/* 7 day cells */}
          {DAYS_OF_WEEK.map((day) => {
            const key = `${day}-${slot}`;
            const isOn = !!cells[key];
            return (
              <RipplePressable
                key={key}
                onPress={() => onToggle(key)}
                haptic="selection"
                accessibilityRole="checkbox"
                accessibilityLabel={`${MEAL_SLOT_LABELS[slot]} on ${day}`}
                accessibilityState={{ checked: isOn }}
                style={{
                  flex: 1,
                  aspectRatio: 1,
                  borderRadius: radius.sm,
                  borderWidth: 1,
                  borderColor: isOn ? colors.border.active : colors.border.subtle,
                  backgroundColor: isOn ? colors.text.primary : colors.surface.elevated,
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                {isOn && (
                  <Ionicons name="checkmark" size={iconSize.sm} color={colors.text.inverse} />
                )}
              </RipplePressable>
            );
          })}
        </View>
      ))}

      <Text style={{ ...typography.small, textAlign: "center" }}>
        {total} meals at home this week
      </Text>
    </View>
  );
}
