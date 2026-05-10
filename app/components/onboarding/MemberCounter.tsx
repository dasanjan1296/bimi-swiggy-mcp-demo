/**
 * MemberCounter — visual + / – stepper for "how many people eat here?",
 * with the active count rendered as a row of monogram avatars. The
 * parent owns the underlying members list; this component just nudges
 * count up and down via two callbacks. Naming each member is captured
 * inline in the parent (one input per row, autofocus on add).
 *
 * Why a stepper instead of a "tap to add" button: most households are
 * 2–4 people. Letting the user land on the right number in two taps
 * (rather than four "Add member" taps) cuts the perceived effort of
 * step 1 in half.
 */

import React from "react";
import { View, Text } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { RipplePressable } from "../RipplePressable";
import { Avatar } from "../ui";
import { colors, radius, spacing, typography, iconSize } from "@/lib/theme";

export interface MemberCounterProps {
  count: number;
  /** Inclusive bounds. Default 1..8. */
  min?: number;
  max?: number;
  /** Names rendered inside the avatars. Length must match `count`. */
  names: string[];
  onIncrement: () => void;
  onDecrement: () => void;
}

export function MemberCounter({
  count,
  min = 1,
  max = 8,
  names,
  onIncrement,
  onDecrement,
}: MemberCounterProps) {
  const canDec = count > min;
  const canInc = count < max;

  return (
    <View style={{ gap: spacing.lg }}>
      {/* Stepper */}
      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.lg }}>
        <StepButton icon="remove" onPress={onDecrement} disabled={!canDec} label="Remove a member" />

        <View style={{ alignItems: "center", minWidth: 80 }}>
          <Text style={{ ...typography.hero, fontSize: 56, lineHeight: 60 }}>{count}</Text>
          <Text style={typography.small}>{count === 1 ? "person" : "people"}</Text>
        </View>

        <StepButton icon="add" onPress={onIncrement} disabled={!canInc} label="Add a member" />
      </View>

      {/* Avatar preview row */}
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, justifyContent: "center" }}>
        {Array.from({ length: count }).map((_, i) => (
          <Avatar key={i} name={names[i] || `M${i + 1}`} id={`onb-${i}`} size="md" />
        ))}
      </View>
    </View>
  );
}

function StepButton({
  icon,
  onPress,
  disabled,
  label,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  onPress: () => void;
  disabled: boolean;
  label: string;
}) {
  return (
    <RipplePressable
      onPress={disabled ? undefined : onPress}
      haptic="light"
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled }}
      style={{
        width: 56,
        height: 56,
        borderRadius: radius.pill,
        borderWidth: 1,
        borderColor: disabled ? colors.border.subtle : colors.border.active,
        backgroundColor: disabled ? colors.surface.disabled : colors.surface.elevated,
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <Ionicons
        name={icon}
        size={iconSize.lg}
        color={disabled ? colors.text.muted : colors.text.primary}
      />
    </RipplePressable>
  );
}
