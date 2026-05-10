import React, { useEffect } from "react";
import { View, type ViewStyle } from "react-native";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withRepeat,
  withTiming,
  Easing,
} from "react-native-reanimated";
import { colors, radius, spacing, cardStyles, listRowStyles } from "@/lib/theme";
import { useReducedMotion } from "@/lib/useReducedMotion";

interface SkeletonBlockProps {
  width: number | `${number}%`;
  height: number;
  style?: ViewStyle;
}

function SkeletonBlock({ width, height, style }: SkeletonBlockProps) {
  const reducedMotion = useReducedMotion();
  const opacity = useSharedValue(reducedMotion ? 0.6 : 0.4);

  useEffect(() => {
    if (reducedMotion) return;
    opacity.value = withRepeat(
      withTiming(0.8, { duration: 1000, easing: Easing.inOut(Easing.ease) }),
      -1,
      true,
    );
  }, [opacity, reducedMotion]);

  const shimmer = useAnimatedStyle(() => ({
    opacity: opacity.value,
  }));

  return (
    <Animated.View
      style={[
        {
          width,
          height,
          borderRadius: radius.sm,
          backgroundColor: colors.surface.elevated,
        },
        shimmer,
        style,
      ]}
    />
  );
}

// Each skeleton's outer View already declares
// accessibilityRole="progressbar" + accessibilityState.busy + a polite
// live region. That's sufficient for VoiceOver to announce "Loading"
// once per skeleton group — adding announceForAccessibility on top
// caused 3-4 duplicate announcements when a SkeletonList with N>1
// rendered, drowning the user. Keeping the helper as a no-op so call
// sites don't have to be edited en-masse; we'll prune them
// progressively as we touch each variant.
function useLoadingAnnouncement(_label: string) {
  // Intentionally no-op. See block comment above.
}

export function SkeletonCard() {
  useLoadingAnnouncement("Loading");
  return (
    <View
      accessibilityRole={"progressbar" as any}
      accessibilityLabel="Loading"
      accessibilityState={{ busy: true }}
      accessibilityLiveRegion="polite"
      style={{ ...cardStyles, marginBottom: spacing.md }}
    >
      <View style={{ flexDirection: "row", justifyContent: "space-between", marginBottom: spacing.md }}>
        <SkeletonBlock width="60%" height={18} />
        <SkeletonBlock width={48} height={18} />
      </View>
      <SkeletonBlock width="80%" height={14} style={{ marginBottom: spacing.sm }} />
      <SkeletonBlock width="40%" height={14} />
    </View>
  );
}

export function SkeletonMealCard() {
  useLoadingAnnouncement("Loading meal suggestions");
  return (
    <View
      accessibilityRole={"progressbar" as any}
      accessibilityLabel="Loading meal suggestions"
      accessibilityState={{ busy: true }}
      accessibilityLiveRegion="polite"
      style={{ ...cardStyles, marginBottom: spacing.md }}
    >
      <View style={{ flexDirection: "row", justifyContent: "space-between", marginBottom: spacing.md }}>
        <View style={{ flex: 1, gap: spacing.sm }}>
          <SkeletonBlock width="70%" height={20} />
          <View style={{ flexDirection: "row", gap: spacing.md }}>
            <SkeletonBlock width={80} height={14} />
            <SkeletonBlock width={90} height={14} />
          </View>
        </View>
        <SkeletonBlock width={28} height={28} style={{ borderRadius: radius.lg }} />
      </View>
      <View style={{ flexDirection: "row", gap: spacing.xs, marginBottom: spacing.sm }}>
        <SkeletonBlock width={60} height={22} />
        <SkeletonBlock width={72} height={22} />
      </View>
      <View style={{
        flexDirection: "row",
        justifyContent: "center",
        gap: spacing.sm,
        paddingTop: spacing.sm,
        borderTopWidth: 1,
        borderTopColor: colors.border.subtle,
      }}>
        {[1, 2, 3, 4, 5].map((i) => (
          <SkeletonBlock key={i} width={28} height={28} style={{ borderRadius: radius.lg }} />
        ))}
      </View>
    </View>
  );
}

/**
 * Approval/order card skeleton — mirrors the real ApprovalCard shape: status
 * pill on the left, requester name, items + total, action buttons row.
 */
export function SkeletonApprovalCard() {
  useLoadingAnnouncement("Loading orders");
  return (
    <View
      accessibilityRole={"progressbar" as any}
      accessibilityLabel="Loading orders"
      accessibilityState={{ busy: true }}
      accessibilityLiveRegion="polite"
      style={{
        ...cardStyles,
        marginBottom: spacing.md,
        borderLeftWidth: 4,
        borderLeftColor: colors.surface.elevated,
      }}
    >
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.sm }}>
        <SkeletonBlock width={120} height={16} />
        <SkeletonBlock width={56} height={20} style={{ borderRadius: radius.sm }} />
      </View>
      <View style={{ gap: spacing.xs, marginBottom: spacing.md }}>
        <SkeletonBlock width="90%" height={13} />
        <SkeletonBlock width="75%" height={13} />
        <SkeletonBlock width="60%" height={13} />
      </View>
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.md }}>
        <SkeletonBlock width={48} height={14} />
        <SkeletonBlock width={64} height={20} />
      </View>
      <View style={{ flexDirection: "row", gap: spacing.sm }}>
        <SkeletonBlock width="48%" height={44} style={{ borderRadius: radius.md }} />
        <SkeletonBlock width="48%" height={44} style={{ borderRadius: radius.md }} />
      </View>
    </View>
  );
}

/**
 * Inventory row skeleton — mirrors InventoryItemRow: name + qty/days, urgency
 * chip on the right. Uses listRowStyles so it composes with real rows.
 */
export function SkeletonInventoryRow() {
  return (
    <View
      accessibilityRole={"progressbar" as any}
      accessibilityLabel="Loading inventory"
      accessibilityState={{ busy: true }}
      accessibilityLiveRegion="polite"
      style={{
        ...listRowStyles,
        flexDirection: "row",
        alignItems: "center",
        gap: spacing.sm,
      }}
    >
      <SkeletonBlock width={28} height={28} style={{ borderRadius: 14 }} />
      <View style={{ flex: 1, gap: 6 }}>
        <SkeletonBlock width="55%" height={14} />
        <SkeletonBlock width="35%" height={11} />
      </View>
      <SkeletonBlock width={60} height={20} style={{ borderRadius: radius.sm }} />
    </View>
  );
}

/**
 * Chat-bubble skeleton — alternates left (cook) and right (user) sides via the
 * `from` prop so loading a thread looks like a real conversation.
 */
export function SkeletonChatBubble({ from = "cook" }: { from?: "cook" | "user" }) {
  const isUser = from === "user";
  const widths: Array<`${number}%`> = ["60%", "80%", "70%"];
  const idx = (from.length + (isUser ? 1 : 0)) % widths.length;
  return (
    <View
      accessibilityRole={"progressbar" as any}
      accessibilityLabel="Loading messages"
      accessibilityState={{ busy: true }}
      accessibilityLiveRegion="polite"
      style={{
        marginBottom: spacing.sm,
        alignItems: isUser ? "flex-end" : "flex-start",
        paddingHorizontal: spacing.lg,
      }}
    >
      <View
        style={{
          backgroundColor: isUser ? colors.accent.primaryDim : colors.surface.card,
          borderRadius: radius.lg,
          borderTopLeftRadius: isUser ? radius.lg : 4,
          borderTopRightRadius: isUser ? 4 : radius.lg,
          paddingVertical: spacing.sm,
          paddingHorizontal: spacing.md,
          maxWidth: "80%",
          gap: 6,
        }}
      >
        <SkeletonBlock width={widths[idx]!} height={12} />
        <SkeletonBlock width="50%" height={12} />
      </View>
    </View>
  );
}

/**
 * InstaCook status-card skeleton — mirrors InstaCookStatusCard layout (icon,
 * label, sub, chevron) for placeholder rendering on Voting/Home.
 */
export function SkeletonStatusCard() {
  return (
    <View
      accessibilityRole={"progressbar" as any}
      accessibilityLabel="Loading status"
      accessibilityState={{ busy: true }}
      accessibilityLiveRegion="polite"
      style={{
        ...cardStyles,
        marginBottom: spacing.md,
        flexDirection: "row",
        alignItems: "center",
        gap: spacing.md,
      }}
    >
      <SkeletonBlock width={36} height={36} style={{ borderRadius: 18 }} />
      <View style={{ flex: 1, gap: 6 }}>
        <SkeletonBlock width="50%" height={14} />
        <SkeletonBlock width="75%" height={11} />
      </View>
      <SkeletonBlock width={16} height={16} />
    </View>
  );
}

export function SkeletonList({ count = 3 }: { count?: number }) {
  return (
    <View>
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonCard key={i} />
      ))}
    </View>
  );
}

export function SkeletonInventoryList({ count = 4 }: { count?: number }) {
  return (
    <View style={{ ...cardStyles, padding: 0, paddingHorizontal: spacing.lg }}>
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonInventoryRow key={i} />
      ))}
    </View>
  );
}

export function SkeletonChatThread({ count = 4 }: { count?: number }) {
  return (
    <View style={{ paddingVertical: spacing.md }}>
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonChatBubble key={i} from={i % 2 === 0 ? "cook" : "user"} />
      ))}
    </View>
  );
}
