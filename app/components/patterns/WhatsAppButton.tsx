/**
 * WhatsAppButton — the single canonical "send via WhatsApp" affordance.
 *
 * Why a dedicated pattern instead of a `whatsapp` variant on <Button>:
 * the eighth design principle ("WhatsApp is a first-class surface, not
 * a fallback") makes "send to WhatsApp" a first-class verb that recurs
 * on at least 5 screens (cook intro, share invite, share meal plan,
 * give-cook-off, ping cook). Each surface needs the same look, the
 * same accessibility, and the same brand-green semantics — exactly
 * what a pattern is for.
 *
 * Variants:
 *   - filled  (default): WhatsApp green surface, white icon + label.
 *                        Use when WhatsApp send IS the screen's
 *                        primary action.
 *   - outlined          : white surface, WhatsApp green icon + label
 *                        + 1px green border. Use when there's already
 *                        a Rausch `<Button variant="primary">` on
 *                        screen — keeps "one filled CTA" rule.
 *
 * Usage:
 *
 *   // Most common: pass phone + message, the button opens WhatsApp.
 *   <WhatsAppButton
 *     phone={cook.whatsappNumber}
 *     message={hindiBrief}
 *     fullWidth
 *   >
 *     Send brief to {cook.name}
 *   </WhatsAppButton>
 *
 *   // Or pass onPress for custom handling (e.g., opening the system
 *   // share sheet, or a no-phone broadcast):
 *   <WhatsAppButton onPress={shareViaSystemSheet}>
 *     Share invite via WhatsApp
 *   </WhatsAppButton>
 *
 * Hard rules baked in:
 *   - The brand-green surface is reserved for THIS pattern only —
 *     never spread `colors.accent.whatsapp` as a `backgroundColor`
 *     on a `<View>` or `<Button>` elsewhere.
 *   - One filled WhatsAppButton per screen max. Pair with `outlined`
 *     when the screen already has a Rausch primary.
 *   - Always carries an Ionicons "logo-whatsapp" leading icon. Never
 *     overridden — the icon is the trust signal.
 */

import React, { useCallback } from "react";
import { Linking, Text, View, ViewStyle } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { RipplePressable } from "../RipplePressable";
import {
  colors,
  fontFamily,
  iconSize,
  radius,
  spacing,
} from "@/lib/theme";

export type WhatsAppButtonVariant = "filled" | "outlined";
export type WhatsAppButtonSize = "sm" | "md" | "lg";

export interface WhatsAppButtonProps {
  children: React.ReactNode;
  /** Phone number — when provided alongside `message`, the button
   *  auto-opens `whatsapp://send?phone=...&text=...`. */
  phone?: string;
  /** Pre-filled message body. Only used when `phone` is set. */
  message?: string;
  /** Custom press handler. Overrides the phone/message auto-open. */
  onPress?: () => void;
  variant?: WhatsAppButtonVariant;
  size?: WhatsAppButtonSize;
  fullWidth?: boolean;
  disabled?: boolean;
  style?: ViewStyle;
  accessibilityLabel?: string;
  testID?: string;
}

function dimsFor(size: WhatsAppButtonSize) {
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

function tonesFor(variant: WhatsAppButtonVariant, disabled: boolean) {
  if (disabled) {
    return {
      bg: colors.surface.disabled,
      fg: colors.text.muted,
      border: "transparent",
    };
  }
  if (variant === "outlined") {
    return {
      bg: colors.surface.base,
      fg: colors.accent.whatsapp,
      border: colors.accent.whatsapp,
    };
  }
  return {
    bg: colors.accent.whatsapp,
    fg: colors.text.contrast,
    border: colors.accent.whatsapp,
  };
}

export function WhatsAppButton({
  children,
  phone,
  message,
  onPress,
  variant = "filled",
  size = "md",
  fullWidth = false,
  disabled = false,
  style,
  accessibilityLabel,
  testID,
}: WhatsAppButtonProps) {
  const dims = dimsFor(size);
  const tones = tonesFor(variant, disabled);

  const handlePress = useCallback(() => {
    if (disabled) return;
    if (onPress) {
      onPress();
      return;
    }
    if (phone) {
      const cleaned = phone.replace(/[^0-9]/g, "");
      const text = message ? `&text=${encodeURIComponent(message)}` : "";
      Linking.openURL(`whatsapp://send?phone=${cleaned}${text}`).catch(() => {
        // Fall back to wa.me when the app handler isn't installed.
        Linking.openURL(`https://wa.me/${cleaned}${text ? `?text=${encodeURIComponent(message ?? "")}` : ""}`);
      });
    }
  }, [disabled, onPress, phone, message]);

  const label = typeof children === "string" ? children : undefined;

  return (
    <RipplePressable
      onPress={handlePress}
      disabled={disabled}
      haptic="light"
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? label}
      accessibilityState={{ disabled }}
      testID={testID}
      style={{
        backgroundColor: tones.bg,
        borderRadius: radius.sm,
        borderWidth: variant === "outlined" ? 1 : 0,
        borderColor: tones.border,
        paddingVertical: dims.padV,
        paddingHorizontal: dims.padH,
        minHeight: dims.minHeight,
        alignSelf: fullWidth ? "stretch" : undefined,
        opacity: disabled ? 0.6 : 1,
        ...style,
      }}
    >
      {/* Inner flex-row wrapper — RipplePressable's outer Animated.View
          gets the `style` prop, but its inner Pressable defaults to
          column layout. Without this wrapper the icon would stack
          above the label. Mirrors the same fix in `<Button>`. */}
      <View
        style={{
          flexDirection: "row",
          alignItems: "center",
          justifyContent: "center",
          gap: spacing.sm,
        }}
      >
        <Ionicons name="logo-whatsapp" size={dims.iconSize} color={tones.fg} />
        {typeof children === "string" ? (
          <Text
            style={{
              fontSize: dims.fontSize,
              fontWeight: "700",
              fontFamily: fontFamily.bold,
              color: tones.fg,
            }}
            numberOfLines={1}
          >
            {children}
          </Text>
        ) : (
          <View>{children}</View>
        )}
      </View>
    </RipplePressable>
  );
}
