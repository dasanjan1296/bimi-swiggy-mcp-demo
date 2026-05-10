/**
 * AuthScreen — strict scaffold for any credential-capture or
 * profile-completion surface (login, OTP, profile, join-house). Owns the
 * vertical rhythm, brand block, keyboard avoidance, scroll behavior, and
 * legal microcopy so screens consume slots, not raw layout primitives.
 *
 * See bimi/app/design-system.md §8.5 for the visual rules.
 *
 * Usage:
 *   <AuthScreen
 *     title="The kitchen, off your mind."
 *     subtitle="Meals, cook, groceries — all of it."
 *     primaryAction={{ label: "Continue", onPress: handleSendOtp, loading }}
 *     tertiaryLinks={[
 *       { label: "Have an invite code? Join a house", onPress: ... },
 *     ]}
 *   >
 *     <InputField label="Phone number" value={phone} onChangeText={setPhone} kind="phone" />
 *   </AuthScreen>
 */

import React from "react";
import {
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  Text,
  View,
  ViewStyle,
} from "react-native";
import { router } from "expo-router";
import { Button, type ButtonProps } from "../ui/Button";
import { TextLink } from "../ui/TextLink";
import { SafeScreen } from "../ui/SafeScreen";
import { colors, fontFamily, radius, spacing, typography } from "@/lib/theme";

export interface AuthPrimaryAction {
  label: string;
  onPress: () => void;
  loading?: boolean;
  disabled?: boolean;
  /** Defaults to "primary". */
  variant?: ButtonProps["variant"];
}

export interface AuthTertiaryLink {
  label: string;
  onPress: () => void;
  testID?: string;
}

export interface AuthScreenProps {
  /** Headline shown beneath the brand mark. typography.hero. */
  title: string;
  /** Optional one-line subhead. typography.body / secondary. */
  subtitle?: string;
  /** Optional override for the brand block. Defaults to "b" mark + "bimi" wordmark. */
  brand?: React.ReactNode;
  /** Slot for the form (typically <InputField> stack or <OtpInput>). */
  children: React.ReactNode;
  /** The single primary action. Renders as <Button variant="primary" fullWidth>. */
  primaryAction: AuthPrimaryAction;
  /** Tertiary links shown beneath the primary action as <TextLink>. */
  tertiaryLinks?: AuthTertiaryLink[];
  /** When true, hides the legal microcopy at the bottom. */
  hideLegal?: boolean;
  /** Optional back-link control rendered above the brand block (for OTP / profile steps). */
  onBack?: () => void;
  /** Override container style. */
  style?: ViewStyle;
}

export function AuthScreen({
  title,
  subtitle,
  brand,
  children,
  primaryAction,
  tertiaryLinks,
  hideLegal = false,
  onBack,
  style,
}: AuthScreenProps) {
  return (
    <SafeScreen>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : "height"}
      >
        <ScrollView
          style={{ flex: 1 }}
          contentContainerStyle={[
            {
              flexGrow: 1,
              paddingHorizontal: spacing.xl,
              paddingTop: spacing.xl,
              paddingBottom: spacing.xl,
            },
            style,
          ]}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {onBack ? (
            <View style={{ marginBottom: spacing.md }}>
              <TextLink onPress={onBack} size="sm" tone="secondary" leadingIcon="chevron-back">
                Back
              </TextLink>
            </View>
          ) : null}

          {brand ?? <DefaultBrandBlock />}

          <View style={{ marginTop: spacing.xxl, alignItems: "flex-start" }}>
            <Text style={{ ...typography.hero, fontSize: 32, lineHeight: 38 }}>
              {title}
            </Text>
            {subtitle ? (
              <Text
                style={{
                  ...typography.body,
                  color: colors.text.secondary,
                  marginTop: spacing.sm,
                }}
              >
                {subtitle}
              </Text>
            ) : null}
          </View>

          <View style={{ marginTop: spacing.xl, gap: spacing.md }}>{children}</View>

          <View style={{ marginTop: spacing.lg, gap: spacing.md }}>
            <Button
              variant={primaryAction.variant ?? "primary"}
              size="lg"
              fullWidth
              onPress={primaryAction.onPress}
              loading={primaryAction.loading}
              disabled={primaryAction.disabled}
            >
              {primaryAction.label}
            </Button>

            {tertiaryLinks && tertiaryLinks.length > 0 ? (
              <View style={{ alignItems: "center", gap: spacing.sm, marginTop: spacing.xs }}>
                {tertiaryLinks.map((l) => (
                  <TextLink
                    key={l.label}
                    onPress={l.onPress}
                    size="sm"
                    tone="secondary"
                  >
                    {l.label}
                  </TextLink>
                ))}
              </View>
            ) : null}
          </View>

          {!hideLegal ? (
            <View style={{ flex: 1 }}>
              <View style={{ flex: 1 }} />
              <LegalMicrocopy />
            </View>
          ) : null}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeScreen>
  );
}

function DefaultBrandBlock() {
  return (
    <View style={{ alignItems: "flex-start", marginTop: spacing.lg }}>
      <View
        style={{
          width: 56,
          height: 56,
          borderRadius: radius.md,
          backgroundColor: colors.surface.card,
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <Text
          style={{
            fontSize: 32,
            fontWeight: "700",
            fontFamily: fontFamily.bold,
            color: colors.accent.primary,
          }}
        >
          b
        </Text>
      </View>
      <Text style={{ ...typography.h2, marginTop: spacing.sm }}>bimi</Text>
    </View>
  );
}

function LegalMicrocopy() {
  return (
    <View style={{ alignItems: "center", marginTop: spacing.xxl }}>
      <Text style={{ ...typography.tiny, textAlign: "center", lineHeight: 16 }}>
        By continuing, you agree to our{" "}
        <Text
          style={{ color: colors.accent.primary, textDecorationLine: "underline" }}
          accessibilityRole="link"
          onPress={() => router.push("/legal/privacy" as never)}
        >
          Privacy Policy
        </Text>
        {" "}and{" "}
        <Text
          style={{ color: colors.accent.primary, textDecorationLine: "underline" }}
          accessibilityRole="link"
          onPress={() => router.push("/legal/terms" as never)}
        >
          Terms of Service
        </Text>
        .
      </Text>
    </View>
  );
}
