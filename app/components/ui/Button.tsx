/**
 * Button — the canonical pressable in the app.
 *
 * Replaces dozens of inline `TouchableOpacity` + raw style blocks. Driven by
 * `theme.buttonStyles` tokens with consistent padding, accessibility, and a
 * built-in loading state.
 *
 * Usage:
 *   <Button onPress={...}>Continue</Button>
 *   <Button variant="success" leadingIcon="checkmark">Approve</Button>
 *   <Button variant="ghost" trailingIcon="chevron-forward">More options</Button>
 *   <Button variant="primary" loading>Saving…</Button>
 */

import React from "react";
import { View, Text, ActivityIndicator, ViewStyle, TextStyle } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { RipplePressable } from "../RipplePressable";
import { colors, radius, spacing, fontFamily, iconSize } from "@/lib/theme";

export type ButtonVariant =
  | "primary"
  | "secondary"
  | "success"
  | "danger"
  | "ghost"
  | "tertiary";

export type ButtonSize = "sm" | "md" | "lg";

export interface ButtonProps {
  children: React.ReactNode;
  onPress?: () => void;
  variant?: ButtonVariant;
  size?: ButtonSize;
  leadingIcon?: keyof typeof Ionicons.glyphMap;
  trailingIcon?: keyof typeof Ionicons.glyphMap;
  loading?: boolean;
  disabled?: boolean;
  fullWidth?: boolean;
  style?: ViewStyle;
  accessibilityLabel?: string;
  haptic?: "light" | "medium" | "heavy" | "selection";
  testID?: string;
}

type Tone = { bg: string; fg: string; border?: string };

function toneFor(variant: ButtonVariant, disabled: boolean): Tone {
  if (disabled) {
    return { bg: colors.surface.disabled, fg: colors.text.muted };
  }
  switch (variant) {
    case "primary":
      return { bg: colors.accent.primary, fg: colors.text.inverse };
    case "success":
      return { bg: colors.accent.success, fg: colors.text.inverse };
    case "danger":
      return { bg: colors.accent.danger, fg: colors.text.inverse };
    case "secondary":
      // Airbnb pattern: white fill, dark outline (border.active), dark label.
      return { bg: colors.surface.base, fg: colors.text.primary, border: colors.border.active };
    case "ghost":
      return { bg: "transparent", fg: colors.text.primary };
    case "tertiary":
      return { bg: "transparent", fg: colors.accent.primary };
    default:
      return { bg: colors.accent.primary, fg: colors.text.inverse };
  }
}

function sizeFor(size: ButtonSize): { padV: number; padH: number; fontSize: number; iconSize: number; minHeight: number } {
  switch (size) {
    case "sm":
      return { padV: 8, padH: 12, fontSize: 13, iconSize: iconSize.xs, minHeight: 36 };
    case "lg":
      return { padV: 18, padH: 20, fontSize: 17, iconSize: iconSize.md, minHeight: 56 };
    case "md":
    default:
      return { padV: 14, padH: 16, fontSize: 15, iconSize: iconSize.sm, minHeight: 44 };
  }
}

export function Button({
  children,
  onPress,
  variant = "primary",
  size = "md",
  leadingIcon,
  trailingIcon,
  loading = false,
  disabled = false,
  fullWidth = false,
  style,
  accessibilityLabel,
  haptic = "light",
  testID,
}: ButtonProps) {
  const isDisabled = disabled || loading;
  const tone = toneFor(variant, isDisabled);
  const dims = sizeFor(size);

  const label = typeof children === "string" ? children : undefined;

  const containerStyle: ViewStyle = {
    backgroundColor: tone.bg,
    borderRadius: radius.sm,
    paddingVertical: dims.padV,
    paddingHorizontal: dims.padH,
    minHeight: dims.minHeight,
    borderWidth: tone.border ? 1 : 0,
    borderColor: tone.border,
    alignSelf: fullWidth ? "stretch" : undefined,
    opacity: isDisabled ? 0.6 : 1,
    ...style,
  };

  // RipplePressable applies `style` to its outer Animated.View, but
  // children render inside an inner Pressable that defaults to column
  // layout — which makes leading/trailing icons stack vertically.
  // Wrap the children in our own row View to force inline layout.
  const innerRowStyle: ViewStyle = {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
  };

  const textStyle: TextStyle = {
    fontSize: dims.fontSize,
    fontWeight: "700",
    fontFamily: fontFamily.bold,
    color: tone.fg,
  };

  return (
    <RipplePressable
      onPress={isDisabled ? undefined : onPress}
      disabled={isDisabled}
      haptic={haptic}
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? label}
      accessibilityState={{ disabled: isDisabled, busy: loading }}
      style={containerStyle}
      testID={testID}
    >
      <View style={innerRowStyle}>
        {loading ? (
          <ActivityIndicator size="small" color={tone.fg} />
        ) : leadingIcon ? (
          <Ionicons name={leadingIcon} size={dims.iconSize} color={tone.fg} />
        ) : null}
        {typeof children === "string" ? (
          <Text style={textStyle} numberOfLines={1}>
            {children}
          </Text>
        ) : (
          <View>{children}</View>
        )}
        {!loading && trailingIcon ? (
          <Ionicons name={trailingIcon} size={dims.iconSize} color={tone.fg} />
        ) : null}
      </View>
    </RipplePressable>
  );
}
