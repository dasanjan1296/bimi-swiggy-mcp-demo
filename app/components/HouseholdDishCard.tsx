/**
 * HouseholdDishCard — the card that turns a generic dish into "your household's
 * relationship with this dish" (PRD §4.13).
 *
 * The card stacks (top → bottom):
 *   1. Hero photo with veg/non-veg dot
 *   2. Dish name + small "queued" pill if active
 *   3. Member reactions row (the killer feature — see MemberReactionsRow)
 *   4. Lived-in metadata row: "made 17× · 12 days ago"
 *   5. Pinned peculiarity, if any: "✱ Mom adds extra ghee"
 *   6. Cook status pill: "Malti Didi has this" / "Cook just learned"
 *   7. Action row: tap-to-queue / unqueue + tap-to-open-detail
 *
 * Width is parent-controlled so the same card composes in 1-up rows ("Saved
 * by Anjan") and 2-up grids ("Loved by everyone").
 */

import React, { useCallback, useMemo, useState } from "react";
import { Image, Pressable, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";

import {
  colors,
  iconSize,
  radius,
  spacing,
  typography,
} from "@/lib/theme";
import { API_HOST } from "@/lib/api";
import { getDishImage } from "@/lib/dish-images";
import { MemberReactionsRow } from "@/components/MemberReactionsRow";
import {
  relativeServedLabel,
  type DishHouseholdFacts,
} from "@/lib/your-kitchen-api";

type Variant = "grid" | "row";

export function HouseholdDishCard({
  facts,
  width,
  variant = "grid",
  onOpen,
  onToggleQueue,
  isQueueMutating = false,
  testID,
}: {
  facts: DishHouseholdFacts;
  width: number;
  variant?: Variant;
  onOpen: (slug: string) => void;
  onToggleQueue: (facts: DishHouseholdFacts) => void;
  isQueueMutating?: boolean;
  testID?: string;
}) {
  const handleOpen = useCallback(() => onOpen(facts.slug), [onOpen, facts.slug]);
  const handleToggle = useCallback(
    (e: any) => {
      e?.stopPropagation?.();
      onToggleQueue(facts);
    },
    [onToggleQueue, facts],
  );

  const local = getDishImage(facts.slug);
  const remoteUri =
    facts.image_url && !facts.image_url.startsWith("http")
      ? `${API_HOST}${facts.image_url}`
      : facts.image_url;
  const source = local ?? (remoteUri ? { uri: remoteUri } : null);

  const lastServed = relativeServedLabel(facts.days_since_last_served);
  const metaLine = useMemo(() => {
    const bits: string[] = [];
    if (facts.times_made > 0) bits.push(`made ${facts.times_made}×`);
    if (lastServed && facts.times_made > 0) bits.push(lastServed);
    if (facts.times_made === 0 && facts.in_cook_repertoire) bits.push("not yet served");
    return bits.join(" · ");
  }, [facts.times_made, facts.in_cook_repertoire, lastServed]);

  const cookPill = useMemo(() => {
    if (facts.cook_learned_recently && facts.times_made === 0) {
      return { icon: "school" as const, label: "Cook just learned this", tone: colors.accent.info };
    }
    if (facts.in_cook_repertoire) {
      return { icon: "checkmark-circle" as const, label: "In cook's repertoire", tone: colors.accent.success };
    }
    return null;
  }, [facts.cook_learned_recently, facts.in_cook_repertoire, facts.times_made]);

  return (
    <Pressable
      onPress={handleOpen}
      accessibilityRole="button"
      accessibilityLabel={`Open ${facts.name}`}
      testID={testID ?? `household-dish-${facts.slug}`}
      style={{
        width,
        borderRadius: radius.md,
        backgroundColor: colors.surface.card,
        borderWidth: 1,
        borderColor: facts.is_queued ? colors.accent.warning : colors.border.subtle,
        overflow: "hidden",
      }}
    >
      {/* Photo */}
      <View
        style={{
          width: "100%",
          aspectRatio: variant === "grid" ? 1 : 1.6,
          backgroundColor: colors.accent.primaryDim,
        }}
      >
        {source ? (
          <Image source={source as any} style={{ width: "100%", height: "100%" }} resizeMode="cover" />
        ) : (
          <View style={{ alignItems: "center", justifyContent: "center", flex: 1 }}>
            <Ionicons name="restaurant-outline" size={iconSize.xl} color={colors.text.muted} />
          </View>
        )}

        {/* Veg / non-veg dot */}
        <View
          style={{
            position: "absolute",
            left: 8,
            top: 8,
            backgroundColor: colors.surface.base,
            borderRadius: 3,
            padding: 2,
          }}
        >
          <View
            style={{
              width: 10,
              height: 10,
              borderRadius: 5,
              backgroundColor: facts.is_veg ? colors.accent.success : colors.accent.danger,
            }}
          />
        </View>

        {/* Queued pill (when active) */}
        {facts.is_queued ? (
          <View
            testID="queued-pill"
            style={{
              position: "absolute",
              right: 8,
              top: 8,
              flexDirection: "row",
              alignItems: "center",
              gap: 4,
              paddingHorizontal: 8,
              paddingVertical: 3,
              borderRadius: radius.pill,
              backgroundColor: colors.accent.warningDim,
              borderWidth: 1,
              borderColor: colors.accent.warning,
            }}
          >
            <Ionicons name="bookmark" size={10} color={colors.accent.warning} />
            <Text style={{ ...typography.tiny, color: colors.accent.warning, fontWeight: "700" }}>
              {facts.queued_by_name ? `Saved by ${facts.queued_by_name}` : "Saved"}
            </Text>
          </View>
        ) : null}
      </View>

      {/* Body */}
      <View style={{ padding: spacing.md, gap: 6 }}>
        <Text
          numberOfLines={1}
          style={{ ...typography.bodyBold, color: colors.text.primary }}
        >
          {facts.name}
        </Text>

        {/* Member reactions */}
        {facts.reactions.length > 0 ? (
          <MemberReactionsRow reactions={facts.reactions} maxVisible={5} size={20} />
        ) : null}

        {/* Lived-in metadata */}
        {metaLine ? (
          <Text numberOfLines={1} style={{ ...typography.tiny, color: colors.text.secondary }}>
            {metaLine}
          </Text>
        ) : null}

        {/* Peculiarity */}
        {facts.pinned_note ? (
          <View
            style={{
              flexDirection: "row",
              alignItems: "flex-start",
              gap: 4,
              backgroundColor: colors.accent.aiDim,
              borderRadius: radius.sm,
              paddingHorizontal: 6,
              paddingVertical: 4,
            }}
          >
            <Text style={{ fontSize: 11, color: colors.accent.ai, lineHeight: 14 }}>✱</Text>
            <Text
              numberOfLines={2}
              style={{ ...typography.tiny, color: colors.accent.ai, flex: 1, lineHeight: 14 }}
            >
              {facts.pinned_note}
            </Text>
          </View>
        ) : null}

        {/* Cook status */}
        {cookPill ? (
          <View
            style={{
              flexDirection: "row",
              alignItems: "center",
              gap: 4,
              alignSelf: "flex-start",
            }}
          >
            <Ionicons name={cookPill.icon} size={12} color={cookPill.tone} />
            <Text style={{ ...typography.tiny, color: cookPill.tone }}>{cookPill.label}</Text>
          </View>
        ) : null}

        {/* Queue toggle */}
        <Pressable
          onPress={handleToggle}
          accessibilityRole="button"
          accessibilityLabel={facts.is_queued ? `Unqueue ${facts.name}` : `Queue ${facts.name} for the next meal`}
          accessibilityState={{ disabled: isQueueMutating, selected: facts.is_queued }}
          disabled={isQueueMutating}
          testID="queue-toggle"
          style={{
            marginTop: 4,
            flexDirection: "row",
            alignItems: "center",
            justifyContent: "center",
            gap: 6,
            paddingVertical: 8,
            borderRadius: radius.md,
            borderWidth: 1,
            borderColor: facts.is_queued ? colors.accent.warning : colors.accent.primary,
            backgroundColor: facts.is_queued
              ? colors.accent.warningDim
              : colors.accent.primaryDim,
            opacity: isQueueMutating ? 0.6 : 1,
          }}
        >
          <Ionicons
            name={facts.is_queued ? "bookmark" : "bookmark-outline"}
            size={14}
            color={facts.is_queued ? colors.accent.warning : colors.accent.primary}
          />
          <Text
            style={{
              ...typography.small,
              fontWeight: "700",
              color: facts.is_queued ? colors.accent.warning : colors.accent.primary,
            }}
          >
            {facts.is_queued ? "In your queue" : "Queue for next meal"}
          </Text>
        </Pressable>
      </View>
    </Pressable>
  );
}
