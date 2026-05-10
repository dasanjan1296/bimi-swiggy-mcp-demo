/**
 * SettingsRow + SettingsSection — list-row pattern using `listRowStyles`
 * dividers instead of one-card-per-row. Replaces six floating cards in
 * notification-settings.tsx, the per-guest cards in guests.tsx, and the
 * member rows pattern in preferences.tsx / settings.tsx.
 */

import React from "react";
import { View, Text, ViewStyle } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { RipplePressable } from "../RipplePressable";
import { colors, cardStyles, listRowStyles, spacing, typography, iconSize } from "@/lib/theme";
import { SectionEyebrow } from "./SectionEyebrow";

export interface SettingsRowProps {
  label: string;
  description?: string;
  leadingIcon?: keyof typeof Ionicons.glyphMap;
  /** Custom right-side element (e.g., a Switch, a chevron-forward, a Pill). */
  trailing?: React.ReactNode;
  /** Show a chevron-forward on the right when no `trailing` is given. */
  chevron?: boolean;
  onPress?: () => void;
  /** When true, removes the bottom divider (for the last row in a card). */
  isLast?: boolean;
  style?: ViewStyle;
}

function SettingsRowImpl({
  label,
  description,
  leadingIcon,
  trailing,
  chevron = false,
  onPress,
  isLast = false,
  style,
}: SettingsRowProps) {
  const inner = (
    <View
      style={{
        ...listRowStyles,
        borderBottomWidth: isLast ? 0 : 1,
        flexDirection: "row",
        alignItems: "center",
        gap: spacing.md,
        ...style,
      }}
    >
      {leadingIcon && (
        <Ionicons name={leadingIcon} size={iconSize.md} color={colors.text.secondary} />
      )}
      <View style={{ flex: 1 }}>
        <Text style={typography.bodyBold}>{label}</Text>
        {description && (
          <Text style={{ ...typography.small, marginTop: 2 }} numberOfLines={2}>
            {description}
          </Text>
        )}
      </View>
      {trailing}
      {!trailing && chevron && (
        <Ionicons name="chevron-forward" size={iconSize.sm} color={colors.text.muted} />
      )}
    </View>
  );

  if (!onPress) return inner;

  return (
    <RipplePressable
      onPress={onPress}
      haptic="selection"
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityHint={description}
    >
      {inner}
    </RipplePressable>
  );
}

/** Memoised so the settings tab's long row list doesn't re-render
 *  every row when any one row's state flips. */
export const SettingsRow = React.memo(SettingsRowImpl);

export interface SettingsSectionProps {
  title?: string;
  /** Optional caption shown above the section label. */
  caption?: string;
  children: React.ReactNode;
  style?: ViewStyle;
}

export function SettingsSection({ title, caption, children, style }: SettingsSectionProps) {
  return (
    <View style={{ marginBottom: spacing.xl, ...style }}>
      {title && <SectionEyebrow>{title}</SectionEyebrow>}
      <View style={{ ...cardStyles, padding: 0, paddingHorizontal: spacing.lg }}>
        {children}
      </View>
      {caption && (
        <Text style={{ ...typography.tiny, marginTop: spacing.sm, marginHorizontal: spacing.xs }}>
          {caption}
        </Text>
      )}
    </View>
  );
}
