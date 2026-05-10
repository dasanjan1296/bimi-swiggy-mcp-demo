/**
 * Onboarding showcase. Reference layout for any "step in a flow"
 * screen — login OTP, household setup, cook interview, dietary
 * preferences. Demonstrates:
 *
 *   - Top illustration / brand mark
 *   - Hero headline + supporting body
 *   - Single primary action (Rausch button) at the bottom
 *   - Ghost skip link beneath the primary action
 *   - Generous spacing rhythm (xxl / xxxl)
 *
 * Strict rules visible here:
 *   - No second primary button.
 *   - No inline color / spacing literals.
 *   - All copy comes from the brand voice ("First, let me…", "I'll…").
 */

import React from "react";
import { Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { safeBack } from "@/lib/safe-back";
import { Button, SafeScreen, TextLink } from "@/components/ui";
import {
  colors,
  iconSize,
  radius,
  spacing,
  typography,
} from "@/lib/theme";

export default function OnboardingShowcase() {
  return (
    <SafeScreen>
      <View
        style={{
          flex: 1,
          padding: spacing.xl,
          paddingBottom: spacing.xxl,
        }}
      >
        {/* Brand mark */}
        <View
          style={{
            alignItems: "center",
            marginTop: spacing.xxxl,
          }}
        >
          <View
            style={{
              width: 72,
              height: 72,
              borderRadius: radius.xl,
              backgroundColor: colors.surface.card,
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <Text style={typography.brandMark}>b</Text>
          </View>
        </View>

        {/* Hero block — pinned to upper third */}
        <View
          style={{
            flex: 1,
            justifyContent: "center",
            gap: spacing.md,
          }}
        >
          <Text style={typography.hero}>
            Welcome to Bimi
          </Text>
          <Text style={{ ...typography.body, color: colors.text.secondary }}>
            I'll keep your kitchen running while you're away — meals planned,
            groceries sorted, your cook handled. Let's set up your home in a
            minute.
          </Text>

          {/* Three quiet trust badges */}
          <View
            style={{
              flexDirection: "row",
              gap: spacing.md,
              marginTop: spacing.lg,
              flexWrap: "wrap",
            }}
          >
            <TrustBadge icon="time-outline" label="Set up in 60 seconds" />
            <TrustBadge icon="lock-closed-outline" label="Private to your home" />
            <TrustBadge icon="heart-outline" label="No spam, ever" />
          </View>
        </View>

        {/* Primary action footer */}
        <View style={{ gap: spacing.md }}>
          <Button
            variant="primary"
            fullWidth
            size="lg"
            onPress={() => safeBack()}
            accessibilityLabel="Get started"
          >
            Get started
          </Button>
          <View style={{ alignItems: "center" }}>
            <TextLink onPress={() => safeBack()}>
              I already have an account
            </TextLink>
          </View>
        </View>
      </View>
    </SafeScreen>
  );
}

function TrustBadge({
  icon,
  label,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
}) {
  return (
    <View
      style={{
        flexDirection: "row",
        alignItems: "center",
        gap: spacing.xs,
        backgroundColor: colors.surface.card,
        borderRadius: radius.pill,
        paddingHorizontal: spacing.md,
        paddingVertical: spacing.xs + 2,
      }}
    >
      <Ionicons name={icon} size={iconSize.xs} color={colors.text.secondary} />
      <Text style={typography.smallBold}>{label}</Text>
    </View>
  );
}
