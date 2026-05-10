/**
 * InputField — single labelled text-input primitive that wires together
 * the visible label, accessibilityLabel, and sensible per-kind defaults
 * for textContentType / autoComplete / keyboardType / autoCapitalize /
 * returnKeyType. Use this everywhere instead of bare <TextInput> so
 * VoiceOver and iOS autofill both Just Work.
 *
 * Per the audit, every form screen had its own ad-hoc TextInput pattern
 * and almost none had accessibilityLabel; this file consolidates the
 * defaults in one place.
 */

import React, { forwardRef, useId } from "react";
import {
  Platform,
  Text,
  TextInput,
  TextInputProps,
  View,
  ViewStyle,
} from "react-native";

import { colors, inputStyles, spacing, typography } from "@/lib/theme";

/**
 * Semantic kind drives keyboard, autofill, capitalisation, and content
 * types. Pass `kind="phone"` etc. instead of remembering 5 separate
 * props per form field.
 */
export type InputFieldKind =
  | "text" // default
  | "name"
  | "phone"
  | "email"
  | "password"
  | "newPassword"
  | "oneTimeCode"
  | "numeric"
  | "url"
  | "search"
  | "multiline";

export interface InputFieldProps
  extends Omit<TextInputProps, "style" | "accessibilityLabel"> {
  label: string;
  /** Optional hint shown under the label. */
  hint?: string;
  /** Optional error message — when non-empty, swaps the border to danger
   *  tone and announces via accessibilityState. */
  errorText?: string;
  /** Semantic kind for keyboard / autofill defaults. Defaults to "text". */
  kind?: InputFieldKind;
  /** Override accessibilityLabel; defaults to `label`. */
  accessibilityLabel?: string;
  /** Container style (the wrapping <View>, not the <TextInput>). */
  containerStyle?: ViewStyle;
  /** Override the input's style (merged on top of inputStyles). */
  inputStyle?: TextInputProps["style"];
}

const KIND_DEFAULTS: Record<
  InputFieldKind,
  Partial<TextInputProps>
> = {
  text: {
    autoCapitalize: "sentences",
    keyboardType: "default",
    returnKeyType: "next",
  },
  name: {
    autoCapitalize: "words",
    autoComplete: "name",
    textContentType: "name",
    keyboardType: "default",
    returnKeyType: "next",
  },
  phone: {
    autoCapitalize: "none",
    autoComplete: "tel",
    textContentType: "telephoneNumber",
    keyboardType: "phone-pad",
    returnKeyType: "done",
  },
  email: {
    autoCapitalize: "none",
    autoCorrect: false,
    autoComplete: "email",
    textContentType: "emailAddress",
    keyboardType: "email-address",
    returnKeyType: "next",
  },
  password: {
    autoCapitalize: "none",
    autoCorrect: false,
    autoComplete: "current-password",
    textContentType: "password",
    secureTextEntry: true,
    returnKeyType: "done",
  },
  newPassword: {
    autoCapitalize: "none",
    autoCorrect: false,
    autoComplete: "new-password",
    textContentType: "newPassword",
    secureTextEntry: true,
    returnKeyType: "done",
  },
  oneTimeCode: {
    autoCapitalize: "none",
    autoCorrect: false,
    autoComplete: "sms-otp",
    textContentType: "oneTimeCode",
    keyboardType: "number-pad",
    returnKeyType: "done",
  },
  numeric: {
    autoCapitalize: "none",
    autoCorrect: false,
    keyboardType: Platform.select({
      ios: "decimal-pad",
      android: "numeric",
      default: "numeric",
    }),
    returnKeyType: "done",
  },
  url: {
    autoCapitalize: "none",
    autoCorrect: false,
    autoComplete: "url",
    textContentType: "URL",
    keyboardType: "url",
    returnKeyType: "go",
  },
  search: {
    autoCapitalize: "none",
    keyboardType: "default",
    returnKeyType: "search",
  },
  multiline: {
    autoCapitalize: "sentences",
    multiline: true,
    keyboardType: "default",
    returnKeyType: "default",
  },
};

export const InputField = forwardRef<TextInput, InputFieldProps>(function InputField(
  {
    label,
    hint,
    errorText,
    kind = "text",
    accessibilityLabel,
    containerStyle,
    inputStyle,
    ...rest
  },
  ref,
) {
  const reactId = useId();
  const labelId = `${reactId}-label`;
  const hintId = hint ? `${reactId}-hint` : undefined;
  const errorId = errorText ? `${reactId}-error` : undefined;
  const defaults = KIND_DEFAULTS[kind];
  const isError = !!errorText;

  return (
    <View style={[{ marginBottom: spacing.lg }, containerStyle]}>
      <Text
        nativeID={labelId}
        style={{
          ...typography.captionBold,
          color: colors.text.primary,
          marginBottom: spacing.xs,
        }}
      >
        {label}
      </Text>
      {hint ? (
        <Text
          nativeID={hintId}
          style={{ ...typography.small, color: colors.text.secondary, marginBottom: spacing.sm }}
        >
          {hint}
        </Text>
      ) : null}
      <TextInput
        ref={ref}
        accessibilityLabel={accessibilityLabel ?? label}
        accessibilityLabelledBy={labelId as any}
        accessibilityState={{ disabled: rest.editable === false }}
        // The TextInput type doesn't ship with describedBy in older RN
        // versions; cast via any to keep compatibility while still
        // forwarding the attribute when supported.
        {...({ accessibilityDescribedBy: errorId ?? hintId } as any)}
        placeholderTextColor={colors.text.muted}
        {...defaults}
        {...rest}
        style={[
          { ...inputStyles, color: colors.text.primary },
          isError ? { borderColor: colors.accent.danger } : null,
          inputStyle,
        ]}
      />
      {errorText ? (
        <Text
          nativeID={errorId}
          accessibilityLiveRegion="polite"
          style={{
            ...typography.tiny,
            color: colors.accent.danger,
            marginTop: 4,
          }}
        >
          {errorText}
        </Text>
      ) : null}
    </View>
  );
});
