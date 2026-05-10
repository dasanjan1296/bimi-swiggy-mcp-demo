/**
 * ToastHost — renders the toast queue. Mount once in `app/_layout.tsx`
 * (just under the AuthGate so it floats over every screen).
 *
 * - Top-anchored, respects safe-area insets.
 * - Slide + fade in via reanimated (FadeInUp).
 * - Auto-dismisses after `duration` ms.
 * - Tap-to-dismiss. Action button (if present) fires + dismisses.
 * - Tone-aware: success/info/warning/error palette.
 * - Reduced-motion: instant fade.
 * - Accessibility: announces via `accessibilityLiveRegion="polite"`.
 */

import React, { useEffect } from "react";
import { View, Text, Pressable } from "react-native";
import Animated, { FadeInUp, FadeOutUp } from "react-native-reanimated";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useToastStore, type ToastItem, type ToastType } from "@/lib/toast";
import { colors, spacing, radius, typography, iconSize } from "@/lib/theme";
import { haptic } from "@/lib/haptics";
import { useReducedMotion } from "@/lib/useReducedMotion";

const TONE: Record<ToastType, { bg: string; border: string; fg: string; icon: keyof typeof Ionicons.glyphMap }> = {
  success: {
    bg: colors.accent.successDim,
    border: colors.accent.success,
    fg: colors.accent.success,
    icon: "checkmark-circle",
  },
  info: {
    bg: colors.accent.infoDim,
    border: colors.accent.info,
    fg: colors.accent.info,
    icon: "information-circle",
  },
  warning: {
    bg: colors.accent.warningDim,
    border: colors.accent.warning,
    fg: colors.accent.warning,
    icon: "alert-circle",
  },
  error: {
    bg: colors.accent.dangerDim,
    border: colors.accent.danger,
    fg: colors.accent.danger,
    icon: "close-circle",
  },
};

function ToastRow({ item, onDismiss }: { item: ToastItem; onDismiss: () => void }) {
  const tone = TONE[item.type];

  useEffect(() => {
    haptic(item.type === "error" ? "warning" : "light");
    const timer = setTimeout(onDismiss, item.duration);
    return () => clearTimeout(timer);
  }, [item.id]);

  return (
    <Pressable
      onPress={onDismiss}
      accessible
      accessibilityRole="alert"
      accessibilityLiveRegion="polite"
      accessibilityLabel={`${item.title}${item.message ? `. ${item.message}` : ""}`}
      hitSlop={8}
      style={{
        marginHorizontal: spacing.md,
        marginBottom: spacing.sm,
      }}
    >
      <View
        style={{
          flexDirection: "row",
          alignItems: "center",
          gap: spacing.sm,
          backgroundColor: tone.bg,
          borderRadius: radius.md,
          paddingHorizontal: spacing.md,
          paddingVertical: spacing.sm + 2,
          borderWidth: 1,
          borderColor: tone.border,
          // Soft shadow so the toast reads as floating, not fixed-banner.
          shadowColor: colors.shadow.default,
          shadowOpacity: 0.25,
          shadowRadius: 8,
          shadowOffset: { width: 0, height: 4 },
          elevation: 6,
        }}
      >
        <Ionicons name={tone.icon} size={iconSize.md} color={tone.fg} />
        <View style={{ flex: 1 }}>
          <Text style={{ ...typography.captionBold, color: tone.fg }} numberOfLines={2}>
            {item.title}
          </Text>
          {item.message && (
            <Text
              style={{ ...typography.tiny, color: colors.text.secondary, marginTop: 2 }}
              numberOfLines={2}
            >
              {item.message}
            </Text>
          )}
        </View>
        {item.action && (
          <Pressable
            onPress={(e) => {
              e.stopPropagation();
              item.action!.onPress();
              onDismiss();
            }}
            hitSlop={8}
            accessibilityRole="button"
            accessibilityLabel={item.action.label}
            style={{
              paddingHorizontal: spacing.sm,
              paddingVertical: spacing.xs,
              borderRadius: radius.sm,
              backgroundColor: tone.fg,
            }}
          >
            <Text style={{ ...typography.tiny, fontWeight: "700", color: colors.text.inverse }}>
              {item.action.label}
            </Text>
          </Pressable>
        )}
      </View>
    </Pressable>
  );
}

export function ToastHost() {
  const queue = useToastStore((s) => s.queue);
  const dismiss = useToastStore((s) => s.dismiss);
  const insets = useSafeAreaInsets();
  const reducedMotion = useReducedMotion();

  if (queue.length === 0) return null;

  return (
    <View
      pointerEvents="box-none"
      style={{
        position: "absolute",
        top: insets.top + spacing.xs,
        left: 0,
        right: 0,
        zIndex: 9999,
      }}
    >
      {queue.map((item) => (
        <Animated.View
          key={item.id}
          entering={reducedMotion ? undefined : FadeInUp.duration(220)}
          exiting={reducedMotion ? undefined : FadeOutUp.duration(180)}
        >
          <ToastRow item={item} onDismiss={() => dismiss(item.id)} />
        </Animated.View>
      ))}
    </View>
  );
}
