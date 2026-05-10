/**
 * TabSwitcher — underlined tab pattern for switching between conceptually
 * primary surfaces (e.g. Pending / Next Order / Past in Approvals;
 * Breakfast / Lunch / Dinner in Voting; By Category / Checklist in Smart Cart).
 *
 * Distinct from <Pill>: pills are filter/chip semantics (often scrollable,
 * many items), TabSwitcher is for a small fixed N (2–5) of mutually-exclusive
 * primary views. The active tab anchors the eye via a 2px amber baseline.
 *
 * Reference implementation modelled on the previous inline tab JSX in
 * `(tabs)/approvals.tsx` (lines 208–241), which the audit praised as the
 * cleanest tab pattern in the app.
 */

import React from "react";
import { View, Text, ViewStyle } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { RipplePressable } from "../RipplePressable";
import { colors, spacing, radius, typography, iconSize } from "@/lib/theme";

export interface TabSwitcherTab<K extends string = string> {
  key: K;
  label: string;
  /** Optional integer count badge shown next to the label. */
  badge?: number;
  /** Optional leading icon (Ionicon name). */
  icon?: keyof typeof Ionicons.glyphMap;
  /** Optional accessibility label override; defaults to the label. */
  accessibilityLabel?: string;
}

export interface TabSwitcherProps<K extends string = string> {
  tabs: TabSwitcherTab<K>[];
  activeKey: K;
  onChange: (key: K) => void;
  /** When true, tabs distribute equally with `flex: 1`. Default: true. */
  fullWidth?: boolean;
  style?: ViewStyle;
}

export function TabSwitcher<K extends string>({
  tabs,
  activeKey,
  onChange,
  fullWidth = true,
  style,
}: TabSwitcherProps<K>) {
  return (
    <View
      accessibilityRole={"tablist" as any}
      style={{
        flexDirection: "row",
        borderBottomWidth: 1,
        borderBottomColor: colors.divider.default,
        marginBottom: spacing.md,
        ...style,
      }}
    >
      {tabs.map((tab) => {
        const active = tab.key === activeKey;
        return (
          <RipplePressable
            key={tab.key}
            onPress={() => onChange(tab.key)}
            haptic="selection"
            accessibilityRole="tab"
            accessibilityState={{ selected: active }}
            accessibilityLabel={tab.accessibilityLabel ?? tab.label}
            style={{
              flex: fullWidth ? 1 : undefined,
              paddingHorizontal: fullWidth ? spacing.sm : spacing.md,
              paddingVertical: spacing.sm + 2,
              minHeight: 44,
              alignItems: "center",
              justifyContent: "center",
              flexDirection: "row",
              gap: spacing.xs,
              // The active tab's 2px baseline overlaps the container's 1px hairline,
              // visually replacing it under the active tab — same effect as approvals.tsx.
              borderBottomWidth: 2,
              borderBottomColor: active ? colors.accent.primary : "transparent",
              marginBottom: -1,
            }}
          >
            {tab.icon && (
              <Ionicons
                name={tab.icon}
                size={iconSize.sm}
                color={active ? colors.accent.primary : colors.text.muted}
              />
            )}
            <Text
              style={{
                ...typography.bodyBold,
                color: active ? colors.accent.primary : colors.text.secondary,
              }}
              numberOfLines={1}
            >
              {tab.label}
            </Text>
            {typeof tab.badge === "number" && tab.badge > 0 && (
              <View
                style={{
                  backgroundColor: active ? colors.accent.primary : colors.surface.elevated,
                  borderRadius: radius.pill,
                  minWidth: 20,
                  height: 20,
                  paddingHorizontal: 6,
                  alignItems: "center",
                  justifyContent: "center",
                  marginLeft: 2,
                }}
              >
                <Text
                  style={{
                    ...typography.tiny,
                    fontWeight: "700",
                    color: active ? colors.text.inverse : colors.text.secondary,
                  }}
                >
                  {tab.badge > 99 ? "99+" : tab.badge}
                </Text>
              </View>
            )}
          </RipplePressable>
        );
      })}
    </View>
  );
}
