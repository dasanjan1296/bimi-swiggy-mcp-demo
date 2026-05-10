/**
 * CookContactCard — replaces the previous "name + phone + slot pills +
 * working days + arrival + departure" cook step with a much smarter
 * Bangalore-aware capture.
 *
 * Critical Bangalore-household friction points this fixes:
 *
 *   1. Many users don't know the cook's first name. We pre-fill four
 *      relational names (Akka / Didi / Aunty / Bai) as taps so the
 *      user can move on immediately. The first name field is opt-in.
 *
 *   2. Many cooks don't have WhatsApp — they share a husband's number,
 *      use a feature phone, or have a Jio number they don't know. The
 *      "She doesn't use WhatsApp" toggle pivots Bimi to SMS-style
 *      updates instead of blocking the flow.
 *
 *   3. Asking for arrival + departure as text inputs ("19:00") is
 *      hostile. We collapse to "Morning / Evening / Both" with sane
 *      defaults; precise times are editable later in settings.
 *
 *   4. The 7-day working-days toggle gets a sane default (Mon-Sat)
 *      with one tap to flip Sunday.
 *
 *   5. We DON'T ask the user what the cook can cook — instead we
 *      preview the WhatsApp message Bimi will send to the cook and
 *      offer one-tap "Send now". This replaces a guess-and-tap
 *      step with an actual data-collection action.
 */

import React from "react";
import { View, Text, TextInput } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { RipplePressable } from "../RipplePressable";
import { Pill, IconBadge } from "../ui";
import {
  colors,
  iconSize,
  inputStyles,
  radius,
  spacing,
  typography,
} from "@/lib/theme";
import { COOK_NAME_OPTIONS } from "@/lib/onboarding-data";
import type { OnboardingCookProfile } from "@/lib/store";

const SLOT_OPTIONS: { value: "morning" | "evening" | "both"; label: string; sub: string }[] = [
  { value: "morning", label: "Morning",      sub: "~7–9 AM" },
  { value: "evening", label: "Evening",      sub: "~6–8 PM" },
  { value: "both",    label: "Both",         sub: "Twice a day" },
];

const ALL_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const DAY_LETTERS = ["M", "T", "W", "T", "F", "S", "S"];

export interface CookContactCardProps {
  profile: OnboardingCookProfile;
  onChange: (patch: Partial<OnboardingCookProfile>) => void;
  /** WhatsApp message Bimi will send to the cook. Caller pre-builds it. */
  introMessagePreview: string;
  onSendNow: () => void;
  onSkipBrief: () => void;
}

export function CookContactCard({
  profile,
  onChange,
  introMessagePreview,
  onSendNow,
  onSkipBrief,
}: CookContactCardProps) {
  const toggleDay = (d: string) => {
    onChange({
      workingDays: profile.workingDays.includes(d)
        ? profile.workingDays.filter((x) => x !== d)
        : [...profile.workingDays, d],
    });
  };

  return (
    <View style={{ gap: spacing.xl }}>
      {/* ── What you call her ────────────────────────────────────── */}
      <View style={{ gap: spacing.sm }}>
        <Text style={typography.captionBold}>What do you call her at home?</Text>

        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.xs }}>
          {COOK_NAME_OPTIONS.map((name) => (
            <Pill
              key={name}
              tone="primary"
              size="md"
              active={profile.displayName === name}
              onPress={() => onChange({ displayName: name })}
            >
              {name}
            </Pill>
          ))}
        </View>

        <TextInput
          value={profile.displayName && !COOK_NAME_OPTIONS.includes(profile.displayName) ? profile.displayName : ""}
          onChangeText={(v) => onChange({ displayName: v })}
          placeholder="Or her actual name (Geeta, Lakshmi…)"
          placeholderTextColor={colors.text.muted}
          accessibilityLabel="Cook's name"
          autoCapitalize="words"
          returnKeyType="next"
          style={{ ...inputStyles, borderWidth: 1, borderColor: colors.border.subtle, marginTop: spacing.xs }}
        />
      </View>

      {/* ── WhatsApp number + has-WhatsApp toggle ───────────────── */}
      <View style={{ gap: spacing.sm }}>
        <Text style={typography.captionBold}>Phone number</Text>
        <TextInput
          value={profile.whatsappNumber}
          onChangeText={(v) => onChange({ whatsappNumber: v })}
          placeholder="+91 98765 43210"
          placeholderTextColor={colors.text.muted}
          keyboardType="phone-pad"
          accessibilityLabel="Cook's phone number"
          autoComplete="tel"
          textContentType="telephoneNumber"
          returnKeyType="done"
          style={{ ...inputStyles, borderWidth: 1, borderColor: colors.border.subtle }}
        />

        <RipplePressable
          onPress={() => onChange({ hasWhatsapp: !profile.hasWhatsapp })}
          haptic="selection"
          accessibilityRole="checkbox"
          accessibilityLabel="She does not use WhatsApp"
          accessibilityState={{ checked: !profile.hasWhatsapp }}
          style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: spacing.xs }}
        >
          <Ionicons
            name={!profile.hasWhatsapp ? "checkbox" : "square-outline"}
            size={iconSize.md}
            color={!profile.hasWhatsapp ? colors.text.primary : colors.text.muted}
          />
          <Text style={typography.body}>She doesn't use WhatsApp — send SMS instead</Text>
        </RipplePressable>
      </View>

      {/* ── Slot ─────────────────────────────────────────────────── */}
      <View style={{ gap: spacing.sm }}>
        <Text style={typography.captionBold}>When does she usually come?</Text>
        <View style={{ flexDirection: "row", gap: spacing.sm }}>
          {SLOT_OPTIONS.map((s) => {
            const isOn = profile.slot === s.value;
            return (
              <RipplePressable
                key={s.value}
                onPress={() => onChange({ slot: s.value })}
                haptic="selection"
                accessibilityRole="radio"
                accessibilityLabel={`${s.label}, ${s.sub}`}
                accessibilityState={{ selected: isOn }}
                style={{
                  flex: 1,
                  paddingVertical: spacing.md,
                  paddingHorizontal: spacing.sm,
                  borderRadius: radius.md,
                  borderWidth: 1,
                  borderColor: isOn ? colors.border.active : colors.border.subtle,
                  backgroundColor: isOn ? colors.surface.card : colors.surface.elevated,
                  alignItems: "center",
                  gap: 2,
                }}
              >
                <Text style={typography.bodyBold}>{s.label}</Text>
                <Text style={typography.tiny}>{s.sub}</Text>
              </RipplePressable>
            );
          })}
        </View>
      </View>

      {/* ── Working days ─────────────────────────────────────────── */}
      <View style={{ gap: spacing.sm }}>
        <Text style={typography.captionBold}>Working days</Text>
        <Text style={{ ...typography.small, marginTop: -spacing.xs }}>
          Default Mon–Sat. Tap to flip.
        </Text>
        <View style={{ flexDirection: "row", justifyContent: "space-between", marginTop: spacing.xs }}>
          {ALL_DAYS.map((d, i) => {
            const on = profile.workingDays.includes(d);
            return (
              <RipplePressable
                key={d}
                onPress={() => toggleDay(d)}
                haptic="selection"
                accessibilityRole="checkbox"
                accessibilityState={{ checked: on }}
                accessibilityLabel={`Working day ${d}`}
                style={{
                  width: 40,
                  height: 40,
                  borderRadius: 20,
                  alignItems: "center",
                  justifyContent: "center",
                  backgroundColor: on ? colors.text.primary : colors.surface.card,
                  borderWidth: 1,
                  borderColor: on ? colors.text.primary : colors.border.subtle,
                }}
              >
                <Text
                  style={{
                    ...typography.smallBold,
                    color: on ? colors.text.inverse : colors.text.secondary,
                  }}
                >
                  {DAY_LETTERS[i]}
                </Text>
              </RipplePressable>
            );
          })}
        </View>
      </View>

      {/* ── WhatsApp brief preview ──────────────────────────────── */}
      {profile.hasWhatsapp && profile.displayName && profile.whatsappNumber.length >= 10 && (
        <View
          style={{
            backgroundColor: colors.surface.card,
            borderRadius: radius.lg,
            padding: spacing.lg,
            gap: spacing.md,
          }}
        >
          <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
            <IconBadge icon="logo-whatsapp" tone="success" size="sm" circle />
            <View style={{ flex: 1 }}>
              <Text style={typography.bodyBold}>I'll text {profile.displayName}</Text>
              <Text style={typography.small}>
                One message — to learn what she cooks well.
              </Text>
            </View>
          </View>

          {/* The message itself, in a quoted-reply style block */}
          <View
            style={{
              borderLeftWidth: 3,
              borderLeftColor: colors.accent.whatsapp,
              paddingLeft: spacing.md,
              paddingVertical: spacing.xs,
            }}
          >
            <Text style={{ ...typography.caption, fontStyle: "italic" }}>
              {introMessagePreview}
            </Text>
          </View>

          <View style={{ flexDirection: "row", gap: spacing.sm }}>
            <RipplePressable
              onPress={onSendNow}
              haptic="success"
              accessibilityRole="button"
              accessibilityLabel="Open WhatsApp and send the intro message"
              style={{
                flex: 1,
                backgroundColor: colors.accent.whatsapp,
                borderRadius: radius.sm,
                paddingVertical: spacing.md,
                flexDirection: "row",
                alignItems: "center",
                justifyContent: "center",
                gap: spacing.xs,
              }}
            >
              <Ionicons name="logo-whatsapp" size={iconSize.sm} color={colors.text.inverse} />
              <Text style={{ ...typography.bodyBold, color: colors.text.inverse }}>
                Send via WhatsApp
              </Text>
            </RipplePressable>

            <RipplePressable
              onPress={onSkipBrief}
              haptic="selection"
              accessibilityRole="button"
              accessibilityLabel="Send the message later — keep going"
              style={{
                paddingVertical: spacing.md,
                paddingHorizontal: spacing.lg,
                borderRadius: radius.sm,
                borderWidth: 1,
                borderColor: colors.border.subtle,
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <Text style={typography.bodyBold}>Later</Text>
            </RipplePressable>
          </View>
        </View>
      )}
    </View>
  );
}
