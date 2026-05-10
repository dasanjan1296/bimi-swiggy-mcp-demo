/**
 * OtpInput — 6-digit (or N-digit) one-time-code input. Replaces the
 * hand-rolled 6-square OTP pattern in login.tsx with a token-driven
 * primitive that wires in:
 *
 *   - Auto-focus on the next field on entry
 *   - Backspace returns focus to the previous field
 *   - iOS sms-otp autofill on the first field only (so Apple doesn't try
 *     to fan a 6-char code across all six fields)
 *   - Filled / focus / default states from the strict design tokens
 *   - Per-field accessibility labels
 *
 * Use it for any short numeric code: OTP, PIN, invite code.
 */

import React, { forwardRef, useImperativeHandle, useRef, useState } from "react";
import { TextInput, View, ViewStyle } from "react-native";
import { colors, fontFamily, radius, spacing } from "@/lib/theme";

export interface OtpInputHandle {
  focus: () => void;
  clear: () => void;
}

export interface OtpInputProps {
  value: string;
  onChange: (value: string) => void;
  /** Number of cells. Defaults to 6. */
  length?: number;
  /** Disable input (e.g., during verify). */
  disabled?: boolean;
  /** Wrapper style override. */
  style?: ViewStyle;
  /** Accessibility hint for the whole input. */
  accessibilityLabel?: string;
}

export const OtpInput = forwardRef<OtpInputHandle, OtpInputProps>(function OtpInput(
  {
    value,
    onChange,
    length = 6,
    disabled = false,
    style,
    accessibilityLabel = "Verification code",
  },
  ref,
) {
  const refs = useRef<(TextInput | null)[]>([]);
  const [focusIndex, setFocusIndex] = useState<number | null>(null);

  useImperativeHandle(ref, () => ({
    focus: () => refs.current[0]?.focus(),
    clear: () => onChange(""),
  }));

  const digits = value.padEnd(length, " ").split("").slice(0, length);

  const handleChange = (text: string, idx: number) => {
    const ch = text.slice(-1);
    const next = digits.map((d, i) => (i === idx ? ch : d.trim())).join("");
    onChange(next);
    if (ch && idx < length - 1) {
      refs.current[idx + 1]?.focus();
    }
  };

  const handleKeyPress = (e: any, idx: number) => {
    if (e.nativeEvent.key === "Backspace" && !digits[idx].trim() && idx > 0) {
      refs.current[idx - 1]?.focus();
    }
  };

  return (
    <View
      style={[{ flexDirection: "row", justifyContent: "space-between", gap: spacing.sm }, style]}
      accessibilityLabel={accessibilityLabel}
    >
      {digits.map((d, i) => {
        const filled = !!d.trim();
        const focused = focusIndex === i;
        return (
          <TextInput
            key={i}
            ref={(r) => {
              refs.current[i] = r;
            }}
            value={d.trim()}
            onChangeText={(t) => handleChange(t, i)}
            onKeyPress={(e) => handleKeyPress(e, i)}
            onFocus={() => setFocusIndex(i)}
            onBlur={() => setFocusIndex(null)}
            maxLength={1}
            keyboardType="number-pad"
            editable={!disabled}
            // textContentType=oneTimeCode is what surfaces the iOS SMS-autofill
            // suggestion bar; only set on the first input so iOS doesn't try
            // to fan a 6-char code across all six fields.
            textContentType={i === 0 ? "oneTimeCode" : undefined}
            autoComplete={i === 0 ? "sms-otp" : undefined}
            accessibilityLabel={`Digit ${i + 1} of ${length}`}
            style={{
              flex: 1,
              maxWidth: 56,
              height: 56,
              borderRadius: radius.md,
              backgroundColor: filled ? colors.surface.elevated : colors.surface.input,
              borderWidth: 1,
              borderColor: focused
                ? colors.border.active
                : filled
                  ? colors.border.subtle
                  : "transparent",
              textAlign: "center",
              fontSize: 22,
              fontWeight: "700",
              fontFamily: fontFamily.bold,
              color: colors.text.primary,
            }}
          />
        );
      })}
    </View>
  );
});
