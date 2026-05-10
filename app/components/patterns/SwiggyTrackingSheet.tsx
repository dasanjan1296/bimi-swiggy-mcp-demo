/**
 * SwiggyTrackingSheet — Swiggy-style order-tracking modal.
 *
 *   ┌──────────┐
 *   │ IN FLIGHT│   ← orange status pill (no fake ETA number)
 *   └──────────┘
 *   Your Swiggy order is in flight
 *
 *   ✓ Order placed       just now
 *   ●  Out for delivery   just now    (pulsing orange dot)
 *   ○  Delivered          —
 *
 *   Your order — 4 items
 *   Atta · Toor dal · Tomatoes · Milk
 *
 *      Open on Swiggy app  ↗      ← demoted text-link escape hatch
 *      Need help? Chat with Swiggy
 *
 * Bimi is the primary tracking surface (status pill + native timeline);
 * the Swiggy-app link is a deliberately small escape hatch so the user
 * doesn't have to leave Bimi for the common "is it almost here" check.
 * Visual language still mirrors the Swiggy app's tracking screen so MCP
 * reviewers immediately recognise the integration.
 *
 * Compliance note (Swiggy Builders Club rules): we do NOT show
 * specific ETA minutes, driver names, ₹ amounts, or absolute
 * timestamps until MCP access lets us source those from real Swiggy
 * data. The DemoSimulationBanner at the top of the body makes the
 * "this is illustrative" framing unmissable.
 *
 * Dev shortcut: long-press the status pill to skip straight to
 * "delivered" (handy in live demos that can't wait the full
 * DEMO_ETA_SECONDS). `__DEV__`-gated so it doesn't ship to production.
 */

import React, { useEffect, useRef, useState } from "react";
import {
  Animated,
  Linking,
  Pressable,
  Text,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { BottomSheet } from "../ui/BottomSheet";
import { Card } from "./Card";
import { DemoSimulationBanner } from "./DemoSimulationBanner";
import { SwiggyBadge, SWIGGY_ORANGE } from "./SwiggyBadge";
import { useSwiggyDeliveryStore } from "@/lib/swiggy-delivery-store";
import {
  colors,
  spacing,
  typography,
} from "@/lib/theme";
import { useReducedMotion } from "@/lib/useReducedMotion";

const SWIGGY_INSTAMART_URL = "https://www.swiggy.com/instamart";

interface SwiggyTrackingSheetProps {
  visible: boolean;
  onClose: () => void;
}

export function SwiggyTrackingSheet({
  visible,
  onClose,
}: SwiggyTrackingSheetProps) {
  const order = useSwiggyDeliveryStore((s) => s.order);
  const state = useSwiggyDeliveryStore((s) => s.state);
  const markDelivered = useSwiggyDeliveryStore((s) => s.markDelivered);
  // Re-render every second while open so the timeline status string
  // ("just now" → eventually "—" if/when we add age strings) stays
  // fresh. Cheap; no specific value depends on the tick.
  const [, forceTick] = useState(0);
  useEffect(() => {
    if (!visible || state !== "out_for_delivery") return;
    const id = setInterval(() => {
      forceTick((t) => (t + 1) % 1_000_000);
    }, 1000);
    return () => clearInterval(id);
  }, [visible, state]);

  const handleOpenSwiggy = () => {
    Linking.openURL(SWIGGY_INSTAMART_URL).catch(() => {});
  };

  if (!order) return null;

  const isDelivered = state === "delivered";

  return (
    <BottomSheet
      visible={visible}
      onClose={onClose}
      title="Order tracking"
      subtitle={`Order #${order.orderId} · simulated`}
      titleAccessory={<SwiggyBadge size="inline" />}
      scrollable
    >
      {/* Compliance disclaimer — first thing in the body so the
          tracking visuals below are framed as illustrative. */}
      <View style={{ marginHorizontal: -spacing.lg, marginBottom: spacing.lg }}>
        <DemoSimulationBanner variant="header" />
      </View>

      {/* Status hero — long-press in __DEV__ to skip to delivered */}
      <StatusPill
        delivered={isDelivered}
        onLongPress={__DEV__ ? markDelivered : undefined}
      />
      <Text
        style={{
          ...typography.caption,
          color: colors.text.secondary,
          textAlign: "center",
          marginTop: spacing.sm,
        }}
      >
        {isDelivered
          ? "Your Swiggy order has been delivered"
          : "Your Swiggy order is in flight"}
      </Text>

      {/* Step timeline */}
      <View style={{ marginTop: spacing.xl }}>
        <TrackingTimeline
          steps={[
            { label: "Order placed", status: "completed", time: "just now" },
            {
              label: "Out for delivery",
              status:
                state === "out_for_delivery"
                  ? "active"
                  : isDelivered
                    ? "completed"
                    : "future",
              time:
                state === "out_for_delivery" || isDelivered
                  ? "just now"
                  : "—",
            },
            {
              label: "Delivered",
              status: isDelivered ? "completed" : "future",
              time: isDelivered ? "just now" : "—",
            },
          ]}
        />
      </View>

      {/* Order summary — item names + count only. ₹ deliberately
          omitted (see file-header compliance note). */}
      <Card variant="elevated" style={{ marginTop: spacing.xl }}>
        <Text style={{ ...typography.bodyBold, marginBottom: spacing.xs }}>
          Your order — {order.items.length} items
        </Text>
        <Text style={{ ...typography.caption, color: colors.text.secondary }}>
          {order.items
            .map((it) => it.itemName ?? it.description)
            .join(" · ")}
        </Text>
      </Card>

      {/* Outlinks — Bimi tracks the order natively (the timeline + pill
          above are the primary surface). The Swiggy-app link below is
          an escape hatch for power users who want Swiggy's full driver-
          map view, deliberately demoted from a bordered CTA to a small
          centred text link so it doesn't compete with native tracking. */}
      <View style={{ marginTop: spacing.xl, alignItems: "center", gap: spacing.xs }}>
        <Pressable
          onPress={handleOpenSwiggy}
          style={({ pressed }) => ({
            flexDirection: "row",
            alignItems: "center",
            gap: 6,
            paddingVertical: spacing.xs,
            paddingHorizontal: spacing.sm,
            opacity: pressed ? 0.5 : 1,
          })}
          accessibilityRole="link"
          accessibilityLabel="Open this order on the Swiggy app"
        >
          <Text style={{ ...typography.caption, color: SWIGGY_ORANGE, fontWeight: "600" }}>
            Open on Swiggy app
          </Text>
          <Ionicons name="open-outline" size={13} color={SWIGGY_ORANGE} />
        </Pressable>
        <Text
          style={{
            ...typography.tiny,
            color: colors.text.muted,
            textAlign: "center",
          }}
        >
          Need help? Chat with Swiggy
        </Text>
      </View>
    </BottomSheet>
  );
}

/**
 * Big orange status pill. Pulses subtly while in flight (skipped
 * under reduced motion). Long-press in dev skips the demo timer.
 *
 * Compliance: shows "IN FLIGHT" / "DELIVERED" labels — never a
 * specific ETA number — until MCP gives us real Swiggy timing data.
 */
function StatusPill({
  delivered,
  onLongPress,
}: {
  delivered: boolean;
  onLongPress?: () => void;
}) {
  const reducedMotion = useReducedMotion();
  const opacity = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    if (delivered || reducedMotion) {
      opacity.setValue(1);
      return;
    }
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, { toValue: 0.85, duration: 800, useNativeDriver: true }),
        Animated.timing(opacity, { toValue: 1, duration: 800, useNativeDriver: true }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [delivered, reducedMotion, opacity]);

  return (
    <View style={{ alignItems: "center" }}>
      <Text
        style={{
          ...typography.tinyBold,
          color: colors.text.secondary,
          letterSpacing: 1.4,
          marginBottom: spacing.xs,
        }}
      >
        {delivered ? "ORDER STATUS" : "ORDER STATUS"}
      </Text>
      <Pressable onLongPress={onLongPress} delayLongPress={600}>
        <Animated.View
          style={{
            backgroundColor: delivered ? colors.accent.success : SWIGGY_ORANGE,
            borderRadius: 999,
            paddingHorizontal: spacing.xl,
            paddingVertical: spacing.md,
            opacity,
          }}
        >
          <Text
            style={{
              ...typography.h2,
              color: colors.text.inverse,
              textAlign: "center",
              letterSpacing: 1.2,
            }}
          >
            {delivered ? "DELIVERED" : "IN FLIGHT"}
          </Text>
        </Animated.View>
      </Pressable>
    </View>
  );
}

type StepStatus = "completed" | "active" | "future";

interface TimelineStep {
  label: string;
  status: StepStatus;
  time: string;
}

/**
 * Vertical 3-step progress timeline, Swiggy-style. Each step:
 *   completed → green check on a green-dim disc
 *   active    → orange pulsing dot on an orange-dim disc
 *   future    → empty muted circle
 *
 * Connector line between steps tints based on the lower step's status.
 */
function TrackingTimeline({ steps }: { steps: TimelineStep[] }) {
  return (
    <View>
      {steps.map((step, idx) => {
        const isLast = idx === steps.length - 1;
        const nextStatus: StepStatus | null = isLast ? null : steps[idx + 1].status;
        return (
          <View key={step.label} style={{ flexDirection: "row" }}>
            {/* Dot column */}
            <View style={{ alignItems: "center", width: 32 }}>
              <StepDot status={step.status} />
              {!isLast ? (
                <View
                  style={{
                    flex: 1,
                    width: 2,
                    minHeight: 28,
                    backgroundColor:
                      step.status === "completed" && nextStatus !== "future"
                        ? colors.accent.success
                        : colors.border.muted,
                    marginVertical: 2,
                  }}
                />
              ) : null}
            </View>

            {/* Label + time column */}
            <View
              style={{
                flex: 1,
                paddingBottom: isLast ? 0 : spacing.md,
                paddingLeft: spacing.sm,
              }}
            >
              <View style={{ flexDirection: "row", alignItems: "center" }}>
                <Text
                  style={{
                    ...typography.body,
                    color:
                      step.status === "future"
                        ? colors.text.muted
                        : colors.text.primary,
                    fontWeight: step.status === "active" ? "700" : "500",
                    flex: 1,
                  }}
                >
                  {step.label}
                  {step.status === "active" ? " (now)" : ""}
                </Text>
                <Text
                  style={{
                    ...typography.caption,
                    color: colors.text.muted,
                  }}
                >
                  {step.time}
                </Text>
              </View>
            </View>
          </View>
        );
      })}
    </View>
  );
}

function StepDot({ status }: { status: StepStatus }) {
  const reducedMotion = useReducedMotion();
  const opacity = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    if (status !== "active" || reducedMotion) {
      opacity.setValue(1);
      return;
    }
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(opacity, { toValue: 0.45, duration: 700, useNativeDriver: true }),
        Animated.timing(opacity, { toValue: 1, duration: 700, useNativeDriver: true }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [status, reducedMotion, opacity]);

  if (status === "completed") {
    return (
      <View
        style={{
          width: 22,
          height: 22,
          borderRadius: 11,
          backgroundColor: colors.accent.successDim,
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <Ionicons name="checkmark" size={14} color={colors.accent.success} />
      </View>
    );
  }
  if (status === "active") {
    return (
      <Animated.View
        style={{
          width: 22,
          height: 22,
          borderRadius: 11,
          backgroundColor: SWIGGY_ORANGE,
          opacity,
        }}
      />
    );
  }
  // future
  return (
    <View
      style={{
        width: 22,
        height: 22,
        borderRadius: 11,
        borderWidth: 1.5,
        borderColor: colors.border.muted,
        backgroundColor: "transparent",
      }}
    />
  );
}
