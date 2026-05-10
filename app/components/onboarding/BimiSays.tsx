/**
 * BimiSays — the conversational chat bubble that opens every step in
 * the redesigned onboarding flow. This is the single component that
 * carries the "smart system learning" feel; without it the screens are
 * just a wizard with extra steps.
 *
 * Anatomy:
 *
 *   ┌───────────────────────────────────────────────────────┐
 *   │ ⬤ b   Got it — Bangalore couple. I'll lean toward     │
 *   │       South Indian on weekdays.                        │
 *   │                                                        │
 *   │       ✨ What I learned                                │
 *   │       • You eat 17 meals at home a week                │
 *   │       • Geeta arrives at 7 PM                          │
 *   └───────────────────────────────────────────────────────┘
 *
 * The "What I learned" sub-block is optional and renders as a quiet
 * `accent.aiDim` panel. We use the AI accent (not Rausch) deliberately
 * — these are Bimi's inferences, not the user's actions.
 *
 * Avatar: a simple Rausch "b" mark. We don't ship the full brand mark
 * here because the conversation has many bubbles and the ornament
 * would overpower the content.
 */

import React from "react";
import { View, Text } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import {
  colors,
  fontFamily,
  iconSize,
  radius,
  spacing,
  typography,
} from "@/lib/theme";

export interface LearnedFact {
  /** Short, present-tense — "You eat 17 meals at home a week". */
  text: string;
  /** Optional Ionicons glyph rendered at the start of the row. */
  icon?: keyof typeof Ionicons.glyphMap;
}

export interface BimiSaysProps {
  /** The main message — Bimi's voice. Keep to 1–2 sentences. */
  message: string;
  /**
   * Optional inferred-facts panel rendered under the message. Use for
   * "here's what I learned from your last answer" or "here's what I'm
   * about to do" — never for instructions or warnings.
   */
  learned?: LearnedFact[];
  /** Custom heading for the learned panel. Default: "What I learned". */
  learnedHeading?: string;
  /** When true, render with a dimmer background (use mid-conversation). */
  quiet?: boolean;
}

export function BimiSays({
  message,
  learned,
  learnedHeading = "What I learned",
  quiet = false,
}: BimiSaysProps) {
  return (
    <View
      style={{
        flexDirection: "row",
        gap: spacing.md,
        padding: spacing.lg,
        borderRadius: radius.lg,
        backgroundColor: quiet ? colors.surface.card : colors.surface.elevated,
        borderWidth: 1,
        borderColor: colors.border.subtle,
      }}
    >
      <BimiAvatar />
      <View style={{ flex: 1, gap: spacing.md }}>
        <Text style={{ ...typography.body, color: colors.text.primary }}>
          {message}
        </Text>

        {learned && learned.length > 0 && (
          <View
            style={{
              padding: spacing.md,
              borderRadius: radius.md,
              backgroundColor: colors.accent.aiDim,
              gap: spacing.sm,
            }}
          >
            <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.xs }}>
              <Ionicons name="sparkles" size={iconSize.xs} color={colors.accent.ai} />
              <Text style={{ ...typography.smallBold, color: colors.accent.ai, textTransform: "uppercase", letterSpacing: 1 }}>
                {learnedHeading}
              </Text>
            </View>
            {learned.map((fact, i) => (
              <View key={i} style={{ flexDirection: "row", alignItems: "flex-start", gap: spacing.xs }}>
                <Ionicons
                  name={fact.icon ?? "checkmark-circle"}
                  size={iconSize.xs}
                  color={colors.accent.ai}
                  style={{ marginTop: 3 }}
                />
                <Text style={{ ...typography.caption, color: colors.text.primary, flex: 1 }}>
                  {fact.text}
                </Text>
              </View>
            ))}
          </View>
        )}
      </View>
    </View>
  );
}

function BimiAvatar() {
  return (
    <View
      style={{
        width: 36,
        height: 36,
        borderRadius: 18,
        backgroundColor: colors.surface.card,
        alignItems: "center",
        justifyContent: "center",
      }}
      accessibilityElementsHidden
    >
      <Text
        style={{
          fontSize: 20,
          fontWeight: "700",
          fontFamily: fontFamily.bold,
          color: colors.accent.primary,
        }}
      >
        b
      </Text>
    </View>
  );
}
