/**
 * WizardLayout — single chrome for the 5 onboarding screens
 * (login → household-setup → join-house → cook-interview → cook-verify).
 *
 * Replaces 5 different header styles, 5 different progress treatments, and
 * 5 different CTA shapes with one consistent shell.
 *
 *   <WizardLayout
 *     step={2}
 *     of={4}
 *     title="Add your household"
 *     subtitle="Everyone who eats at home"
 *     onBack={...}
 *     primaryCTA={<Button>Next</Button>}
 *     secondaryCTA={<TextLink>Skip for now</TextLink>}
 *   >
 *     ...form content...
 *   </WizardLayout>
 *
 * Notes:
 *  - Step indicator is a row of dots that auto-fills past steps.
 *  - The footer is a sticky bar above safe-area inset; primaryCTA sits on the right.
 *  - Set `step` to undefined to omit the indicator (use for screens like login that aren't part of a stepped flow).
 *  - When `keyboardAvoiding` is true, the body is wrapped in a KeyboardAvoidingView.
 */

import React from "react";
import {
  View,
  Text,
  ScrollView,
  ScrollViewProps,
  ViewStyle,
  KeyboardAvoidingView,
  Platform,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { safeBack } from "@/lib/safe-back";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { RipplePressable } from "../RipplePressable";
import { colors, spacing, radius, typography, iconSize } from "@/lib/theme";
import { AmbientBackdrop } from "./AmbientBackdrop";

export interface WizardLayoutProps {
  /** 1-indexed current step. Omit to hide the indicator (e.g., login). */
  step?: number;
  /** Total number of steps. Omit to hide the indicator. */
  of?: number;
  /** Optional centered title rendered above the body. */
  title?: string;
  /** Optional caption below the title. */
  subtitle?: string;
  /** Show a back-arrow on the left. Defaults to `safeBack()` (pops the
   *  stack if possible, otherwise routes to `/(tabs)`). */
  onBack?: () => void;
  /** When true, render no back affordance even if onBack is provided. */
  hideBack?: boolean;
  /** Right-side header element (e.g., a "Skip" link). */
  rightAction?: React.ReactNode;
  /** Body content. */
  children: React.ReactNode;
  /** Sticky footer primary CTA (typically a <Button variant="primary" />). */
  primaryCTA?: React.ReactNode;
  /** Sticky footer secondary CTA / link. */
  secondaryCTA?: React.ReactNode;
  /** When true, body is wrapped in a KeyboardAvoidingView (default true). */
  keyboardAvoiding?: boolean;
  /** When true, body is rendered inside a ScrollView (default true). */
  scrollable?: boolean;
  scrollViewProps?: Omit<ScrollViewProps, "children">;
  /** Optional ambient blob backdrop (defaults to true for the warm onboarding feel). */
  ambientBackdrop?: boolean;
  /** Centered body alignment (used by login). */
  centered?: boolean;
  bodyStyle?: ViewStyle;
}

export function WizardLayout({
  step,
  of,
  title,
  subtitle,
  onBack,
  hideBack = false,
  rightAction,
  children,
  primaryCTA,
  secondaryCTA,
  keyboardAvoiding = true,
  scrollable = true,
  scrollViewProps,
  ambientBackdrop = true,
  centered = false,
  bodyStyle,
}: WizardLayoutProps) {
  const insets = useSafeAreaInsets();

  const handleBack = () => {
    if (onBack) onBack();
    else safeBack();
  };

  const showStepIndicator = typeof step === "number" && typeof of === "number" && of > 1;
  const showHeader = !hideBack || rightAction || showStepIndicator;
  const hasFooter = !!primaryCTA || !!secondaryCTA;

  const headerBar = showHeader ? (
    <View
      style={{
        flexDirection: "row",
        alignItems: "center",
        gap: spacing.sm,
        paddingHorizontal: spacing.lg,
        paddingTop: insets.top + spacing.sm,
        paddingBottom: spacing.sm,
      }}
    >
      {!hideBack ? (
        <RipplePressable
          onPress={handleBack}
          hitSlop={{ top: 12, left: 12, right: 12, bottom: 12 }}
          accessibilityRole="button"
          accessibilityLabel="Go back"
          haptic="selection"
          style={{ width: 40, height: 40, alignItems: "center", justifyContent: "center" }}
        >
          <Ionicons name="chevron-back" size={iconSize.lg} color={colors.text.primary} />
        </RipplePressable>
      ) : (
        <View style={{ width: 40 }} />
      )}

      {showStepIndicator ? (
        <View
          style={{ flex: 1, flexDirection: "row", justifyContent: "center", alignItems: "center", gap: 6 }}
          accessibilityRole={"progressbar" as any}
          accessibilityLabel={`Step ${step} of ${of}`}
          accessibilityValue={{ now: step!, min: 1, max: of! }}
        >
          {Array.from({ length: of! }).map((_, i) => {
            const filled = i < step!;
            const current = i === step! - 1;
            return (
              <View
                key={i}
                style={{
                  width: current ? 22 : 6,
                  height: 6,
                  borderRadius: 3,
                  backgroundColor: filled ? colors.accent.primary : colors.surface.elevated,
                }}
              />
            );
          })}
        </View>
      ) : (
        <View style={{ flex: 1 }} />
      )}

      <View style={{ minWidth: 40, alignItems: "flex-end" }}>{rightAction}</View>
    </View>
  ) : (
    <View style={{ height: insets.top }} />
  );

  const titleBlock = (title || subtitle) ? (
    <View
      style={{
        paddingHorizontal: spacing.lg,
        marginTop: spacing.lg,
        marginBottom: spacing.xl,
        alignItems: centered ? "center" : "flex-start",
      }}
    >
      {title && (
        <Text style={[typography.h1, centered && { textAlign: "center" }]}>
          {title}
        </Text>
      )}
      {subtitle && (
        <Text
          style={[
            { ...typography.subtitle, marginTop: spacing.xs },
            centered && { textAlign: "center" },
          ]}
        >
          {subtitle}
        </Text>
      )}
    </View>
  ) : null;

  const body = (
    <View
      style={{
        flex: 1,
        paddingHorizontal: spacing.lg,
        paddingBottom: hasFooter ? spacing.xl : spacing.xxl,
        ...bodyStyle,
      }}
    >
      {children}
    </View>
  );

  const wrappedBody = scrollable ? (
    <ScrollView
      style={{ flex: 1 }}
      contentContainerStyle={{ flexGrow: 1 }}
      keyboardShouldPersistTaps="handled"
      showsVerticalScrollIndicator={false}
      {...scrollViewProps}
    >
      {titleBlock}
      {body}
    </ScrollView>
  ) : (
    <>
      {titleBlock}
      {body}
    </>
  );

  const footer = hasFooter ? (
    <View
      style={{
        paddingHorizontal: spacing.lg,
        paddingTop: spacing.md,
        paddingBottom: insets.bottom + spacing.md,
        borderTopWidth: 1,
        borderTopColor: colors.divider.default,
        backgroundColor: colors.surface.base,
        gap: spacing.sm,
      }}
    >
      {primaryCTA}
      {secondaryCTA && <View style={{ alignItems: "center" }}>{secondaryCTA}</View>}
    </View>
  ) : null;

  const contents = (
    <View style={{ flex: 1, backgroundColor: colors.surface.base }}>
      {ambientBackdrop && <AmbientBackdrop />}
      {headerBar}
      {wrappedBody}
      {footer}
    </View>
  );

  if (!keyboardAvoiding) return contents;

  return (
    <KeyboardAvoidingView
      style={{ flex: 1 }}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      {contents}
    </KeyboardAvoidingView>
  );
}
