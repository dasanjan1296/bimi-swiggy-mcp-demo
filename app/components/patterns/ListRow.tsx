/**
 * ListRow — single canonical row for any list-style content in Bimi:
 * settings rows, household members, today's tomorrow meals, kitchen
 * inventory, notifications, etc.
 *
 * Replaces the dozens of hand-rolled "<TouchableOpacity><Icon /><View>
 * <Text>title</Text><Text>sub</Text></View><Chevron /></TouchableOpacity>"
 * compositions across the app.
 *
 * Variants:
 *   - Resting (no onPress): inert row.
 *   - Interactive (onPress set): RipplePressable + chevron suffix by
 *     default. Suppress with showChevron={false}.
 *
 * Density:
 *   - Default: paddingVertical spacing.md (12), minHeight 56.
 *   - compact: paddingVertical spacing.sm (8),  minHeight 44.
 */

import React from "react";
import { Text, View, ViewStyle } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { RipplePressable } from "../RipplePressable";
import { colors, iconSize, radius, spacing, typography } from "@/lib/theme";

export interface ListRowProps {
  /** Leading slot — Ionicons name, or arbitrary React node (e.g., Avatar). */
  leading?: keyof typeof Ionicons.glyphMap | React.ReactNode;
  /** Tone-color the leading icon. Defaults to text.secondary. */
  leadingTone?: "primary" | "success" | "warning" | "danger" | "info" | "neutral";
  title: string;
  subtitle?: string;
  /** Trailing slot — value text, badge, or arbitrary node. */
  trailing?: React.ReactNode;
  onPress?: () => void;
  showChevron?: boolean;
  compact?: boolean;
  /** When true, the leading icon sits inside a tinted circle. */
  iconBubble?: boolean;
  /** Disabled state — dims everything, blocks press. */
  disabled?: boolean;
  style?: ViewStyle;
  accessibilityLabel?: string;
  testID?: string;
}

function leadingColor(tone: NonNullable<ListRowProps["leadingTone"]>) {
  switch (tone) {
    case "primary": return colors.accent.primary;
    case "success": return colors.accent.success;
    case "warning": return colors.accent.warning;
    case "danger":  return colors.accent.danger;
    case "info":    return colors.accent.info;
    case "neutral":
    default:        return colors.text.primary;
  }
}

function leadingDim(tone: NonNullable<ListRowProps["leadingTone"]>) {
  switch (tone) {
    case "primary": return colors.accent.primaryDim;
    case "success": return colors.accent.successDim;
    case "warning": return colors.accent.warningDim;
    case "danger":  return colors.accent.dangerDim;
    case "info":    return colors.accent.infoDim;
    case "neutral":
    default:        return colors.surface.card;
  }
}

export function ListRow({
  leading,
  leadingTone = "neutral",
  title,
  subtitle,
  trailing,
  onPress,
  showChevron,
  compact = false,
  iconBubble = false,
  disabled = false,
  style,
  accessibilityLabel,
  testID,
}: ListRowProps) {
  const isInteractive = !!onPress && !disabled;
  // Show chevron by default when the row is interactive AND there's no
  // custom trailing slot competing for the right side.
  const renderChevron = showChevron ?? (isInteractive && !trailing);

  const padV = compact ? spacing.sm : spacing.md;
  const minH = compact ? 44 : 56;

  const containerStyle: ViewStyle = {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    paddingVertical: padV,
    paddingHorizontal: spacing.md,
    minHeight: minH,
    opacity: disabled ? 0.5 : 1,
    ...style,
  };

  const Leading = (() => {
    if (!leading) return null;
    if (typeof leading === "string") {
      const fg = leadingColor(leadingTone);
      if (iconBubble) {
        return (
          <View
            style={{
              width: 36,
              height: 36,
              borderRadius: 18,
              backgroundColor: leadingDim(leadingTone),
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <Ionicons name={leading as any} size={iconSize.md} color={fg} />
          </View>
        );
      }
      return <Ionicons name={leading as any} size={iconSize.md} color={fg} />;
    }
    return <View>{leading}</View>;
  })();

  const Body = (
    <View style={{ flex: 1, gap: 2 }}>
      <Text style={typography.h3} numberOfLines={1}>{title}</Text>
      {subtitle ? (
        <Text style={typography.caption} numberOfLines={2}>{subtitle}</Text>
      ) : null}
    </View>
  );

  const Trailing = (() => {
    if (renderChevron) {
      return (
        <Ionicons
          name="chevron-forward"
          size={iconSize.sm}
          color={colors.text.muted}
        />
      );
    }
    if (trailing) return <View>{trailing}</View>;
    return null;
  })();

  const inner = (
    <>
      {Leading}
      {Body}
      {Trailing}
    </>
  );

  if (isInteractive) {
    return (
      <RipplePressable
        onPress={onPress}
        haptic="selection"
        accessibilityRole="button"
        accessibilityLabel={accessibilityLabel ?? title}
        testID={testID}
        style={containerStyle}
      >
        {inner}
      </RipplePressable>
    );
  }

  return (
    <View style={containerStyle} accessibilityLabel={accessibilityLabel} testID={testID}>
      {inner}
    </View>
  );
}

/**
 * Wrapper that gives a stack of ListRows the canonical card surround +
 * hairline dividers between rows. Use when you have 2+ rows that belong
 * to the same group (settings sections, household members, etc).
 */
export function ListRowGroup({ children, style }: { children: React.ReactNode; style?: ViewStyle }) {
  return (
    <View
      style={{
        backgroundColor: colors.surface.card,
        borderRadius: radius.lg,
        overflow: "hidden",
        ...style,
      }}
    >
      {React.Children.map(children, (child, idx) =>
        idx === 0 ? (
          child
        ) : (
          <View>
            <View
              style={{
                height: 1,
                backgroundColor: colors.divider.default,
                marginHorizontal: spacing.md,
              }}
            />
            {child}
          </View>
        ),
      )}
    </View>
  );
}
