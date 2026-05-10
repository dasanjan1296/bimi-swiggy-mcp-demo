// Centralized dialog helpers — replaces ~15 per-file showAlert duplicates.
// Web Alert.alert silently swallows multi-button dialogs; we polyfill with window.alert / window.confirm.

import { Alert, Platform } from "react-native";

export type DialogButton = {
  text: string;
  onPress?: () => void;
  style?: "default" | "cancel" | "destructive";
};

/**
 * Cross-platform alert. On web: window.alert (single-button) or window.confirm
 * (multi-button — confirm fires the first non-cancel onPress, dismiss fires cancel).
 * On native: forwards to Alert.alert.
 */
export function showAlert(
  title: string,
  message: string,
  buttons?: DialogButton[],
): void {
  if (Platform.OS === "web") {
    if (buttons && buttons.length > 1) {
      const confirmed = (globalThis as any).window?.confirm?.(`${title}\n\n${message}`);
      const fallback = confirmed
        ? buttons.find((b) => b.style !== "cancel")
        : buttons.find((b) => b.style === "cancel");
      fallback?.onPress?.();
    } else {
      (globalThis as any).window?.alert?.(`${title}\n\n${message}`);
      buttons?.find((b) => !b.style || b.style === "default")?.onPress?.();
    }
    return;
  }
  Alert.alert(title, message, buttons as any);
}

/** Convenience wrapper for OK/Cancel-style confirms. */
export function showConfirm(
  title: string,
  message: string,
  opts: {
    confirmText?: string;
    cancelText?: string;
    destructive?: boolean;
    onConfirm: () => void;
    onCancel?: () => void;
  },
): void {
  showAlert(title, message, [
    { text: opts.cancelText ?? "Cancel", style: "cancel", onPress: opts.onCancel },
    {
      text: opts.confirmText ?? "OK",
      style: opts.destructive ? "destructive" : "default",
      onPress: opts.onConfirm,
    },
  ]);
}
