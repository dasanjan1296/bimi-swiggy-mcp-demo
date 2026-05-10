/**
 * FormSection — section title + optional helper text + grouped inputs.
 * Use for any non-trivial form: settings/dietary, settings/cook, household
 * setup, feedback, etc.
 *
 * Replaces ad-hoc "<Text style={typography.h2}>Section</Text><InputField />
 * <InputField />" block patterns scattered across form screens.
 */

import React from "react";
import { Text, View, ViewStyle } from "react-native";
import { colors, spacing, typography } from "@/lib/theme";

export interface FormSectionProps {
  title: string;
  /** Helper text under the title — explains the section briefly. */
  helper?: string;
  children: React.ReactNode;
  /** Optional trailing slot in the section header (e.g., a count badge). */
  trailing?: React.ReactNode;
  /** Spacing applied between this section and the previous one. Defaults to xxl. */
  topSpacing?: number;
  style?: ViewStyle;
}

export function FormSection({
  title,
  helper,
  children,
  trailing,
  topSpacing = spacing.xxl,
  style,
}: FormSectionProps) {
  return (
    <View style={[{ marginTop: topSpacing }, style]}>
      <View
        style={{
          flexDirection: "row",
          alignItems: "flex-start",
          gap: spacing.md,
          marginBottom: spacing.md,
        }}
      >
        <View style={{ flex: 1 }}>
          <Text style={typography.h2}>{title}</Text>
          {helper ? (
            <Text
              style={{
                ...typography.caption,
                color: colors.text.secondary,
                marginTop: spacing.xs,
              }}
            >
              {helper}
            </Text>
          ) : null}
        </View>
        {trailing}
      </View>
      <View style={{ gap: spacing.md }}>{children}</View>
    </View>
  );
}
