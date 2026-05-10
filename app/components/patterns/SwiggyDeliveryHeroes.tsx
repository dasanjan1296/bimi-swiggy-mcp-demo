/**
 * SwiggyDeliveryHeroes — the two heroes that take over the home tab
 * during the Swiggy MCP grocery delivery lifecycle:
 *
 *   <SwiggyDeliveryActiveHero> — when state === "out_for_delivery".
 *     Title "Order in flight"; CTA opens the tracking sheet.
 *     Internally polls every second for the auto-transition to
 *     "delivered" once `(now - placedAt) >= DEMO_ETA_SECONDS * 1000`.
 *
 *   <SwiggyDeliveredHero> — when state === "delivered". The transition
 *     into "delivered" already fired the inventory auto-restock side
 *     effect (in `useSwiggyDeliveryStore.markDelivered`), so the user
 *     has nothing to confirm. "Got it" dismisses to "idle".
 *
 * Both wear the Swiggy "Powered by" pill in the top-right corner so
 * the lifecycle reads as one continuous integration. Both also render
 * the DemoSimulationBanner directly underneath — Swiggy Builders Club
 * rules forbid surfacing prices / ETAs / driver names that aren't
 * sourced from real MCP data, so we're transparent that this is
 * illustrative until MCP access lands.
 */

import React, { useEffect, useState } from "react";
import { View } from "react-native";
import {
  DEMO_ETA_SECONDS,
  useSwiggyDeliveryStore,
} from "@/lib/swiggy-delivery-store";
import { spacing } from "@/lib/theme";
import { DemoSimulationBanner } from "./DemoSimulationBanner";
import { HeroCard } from "./HeroCard";
import { SwiggyBadge } from "./SwiggyBadge";

interface ActiveHeroProps {
  onOpenTracking: () => void;
}

export function SwiggyDeliveryActiveHero({ onOpenTracking }: ActiveHeroProps) {
  const order = useSwiggyDeliveryStore((s) => s.order);
  const markDelivered = useSwiggyDeliveryStore((s) => s.markDelivered);

  // Tick once per second to drive the auto-transition. We don't
  // re-render any value on the hero itself — it just needs the timer.
  useEffect(() => {
    if (!order) return;
    const id = setInterval(() => {
      const elapsedMs = Date.now() - new Date(order.placedAt).getTime();
      if (elapsedMs >= DEMO_ETA_SECONDS * 1000) {
        markDelivered();
      }
    }, 1000);
    return () => clearInterval(id);
  }, [order, markDelivered]);

  if (!order) return null;

  return (
    <View style={{ gap: spacing.xs }}>
      <HeroCard
        tone="info"
        icon="bicycle"
        title="Order in flight"
        subtitle={`${order.items.length} items · tracking live`}
        ctaLabel="Track delivery"
        topRight={<SwiggyBadge size="pill" />}
        testID="hero-swiggy-active-delivery"
        onPress={onOpenTracking}
      />
      <DemoSimulationBanner variant="inline" />
    </View>
  );
}

export function SwiggyDeliveredHero() {
  const order = useSwiggyDeliveryStore((s) => s.order);
  const dismiss = useSwiggyDeliveryStore((s) => s.dismiss);

  if (!order) return null;

  return (
    <View style={{ gap: spacing.xs }}>
      <HeroCard
        tone="success"
        icon="checkmark-circle"
        title="Groceries delivered"
        subtitle={`${order.items.length} items delivered & restocked in your kitchen`}
        ctaLabel="Got it"
        topRight={<SwiggyBadge size="pill" />}
        testID="hero-swiggy-delivered"
        onPress={dismiss}
      />
      <DemoSimulationBanner variant="inline" />
    </View>
  );
}
