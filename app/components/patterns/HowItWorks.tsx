/**
 * HowItWorks — step-by-step flow explainer. Use as a first-run
 * orientation surface (empty Voting tab, empty Approvals tab, etc).
 *
 * Each step is { icon, label }. The component renders a vertically
 * connected list of icon dots + labels.
 */

import React from "react";
import { Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import {
  colors,
  iconSize,
  radius,
  spacing,
  typography,
} from "@/lib/theme";

export interface HowItWorksStep {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
}

export interface HowItWorksProps {
  title: string;
  steps: HowItWorksStep[];
}

export function HowItWorks({ title, steps }: HowItWorksProps) {
  return (
    <View
      style={{
        backgroundColor: colors.surface.card,
        borderRadius: radius.lg,
        padding: spacing.lg,
      }}
    >
      <View
        style={{
          flexDirection: "row",
          alignItems: "center",
          gap: spacing.xs,
          marginBottom: spacing.md,
        }}
      >
        <Ionicons
          name="help-circle-outline"
          size={iconSize.sm}
          color={colors.accent.primary}
        />
        <Text style={typography.bodyBold}>{title}</Text>
      </View>
      {steps.map((step, idx) => {
        const isLast = idx === steps.length - 1;
        return (
          <View
            key={idx}
            style={{
              flexDirection: "row",
              alignItems: "center",
              gap: spacing.md,
              marginBottom: isLast ? 0 : spacing.md,
            }}
          >
            <View style={{ alignItems: "center", width: 32 }}>
              <View
                style={{
                  width: 28,
                  height: 28,
                  borderRadius: 14,
                  backgroundColor: colors.accent.primaryDim,
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <Ionicons
                  name={step.icon}
                  size={iconSize.xs}
                  color={colors.accent.primary}
                />
              </View>
              {!isLast && (
                <View
                  style={{
                    width: 1,
                    height: 12,
                    backgroundColor: colors.divider.default,
                    marginTop: 2,
                  }}
                />
              )}
            </View>
            <Text style={{ ...typography.caption, flex: 1 }}>{step.label}</Text>
          </View>
        );
      })}
    </View>
  );
}
