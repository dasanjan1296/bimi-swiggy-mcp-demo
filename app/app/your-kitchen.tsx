/**
 * Your Kitchen — the personal canon (PRD §4.13).
 *
 * The primary browsing surface for dishes. Replaces Discover-style "Featured /
 * Bestseller" sections with household-relative ones:
 *
 *   • Saved by {name}        — active queue entries (single column, prominent)
 *   • Loved by everyone      — dishes ≥ N-1 members like, no dislikes
 *   • Haven't had in a while — last_served > 21 days, times_made ≥ 2
 *   • Cook just learned this — CAN_COOK edge < 30 days old, times_made == 0
 *   • All your dishes        — long tail (2-up grid)
 *
 * Day-zero (no canon yet) renders an empty-state band that nudges toward
 * onboarding seeding + a single "Browse all dishes" link to the global
 * catalog. Once `has_canon === true`, the full sectioned view takes over.
 *
 * The "Browse all dishes" link at the bottom routes to the existing
 * `dish-catalog.tsx` — that screen is now demoted to the rare-mood fallback
 * surface, not the default browsing experience.
 */

import React, { useCallback } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  Text,
  useWindowDimensions,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { router } from "expo-router";
import { safeBack } from "@/lib/safe-back";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import {
  buttonStyles,
  colors,
  iconSize,
  radius,
  spacing,
  typography,
} from "@/lib/theme";
import {
  useAddToQueue,
  useRemoveFromQueue,
  useYourKitchen,
  type CanonSection,
  type DishHouseholdFacts,
} from "@/lib/your-kitchen-api";
import { HouseholdDishCard } from "@/components/HouseholdDishCard";
import { SectionHeader } from "@/components/SectionHeader";
import { EmptyStateGuide } from "@/components/GuidanceTip";

const GRID_GUTTER = 12;
const GRID_PADDING = 20;

export default function YourKitchenScreen() {
  const canon = useYourKitchen();
  const addQueue = useAddToQueue();
  const removeQueue = useRemoveFromQueue();

  const { width: screenWidth } = useWindowDimensions();
  const insets = useSafeAreaInsets();
  const cellWidth = (screenWidth - GRID_PADDING * 2 - GRID_GUTTER) / 2;
  // Push the title down so the floating BackButton (40px tall, sits at
  // safe-area-top + 16) doesn't overlap the YOUR KITCHEN eyebrow.
  const headerTopPadding = Math.max(insets.top, 12) + 56;

  const openDish = useCallback(
    (slug: string) => router.push({ pathname: "/dish/[slug]", params: { slug } } as any),
    [],
  );

  const toggleQueue = useCallback(
    async (facts: DishHouseholdFacts) => {
      if (facts.is_queued) {
        // Remove path: we don't have the queue_id in facts (intentionally —
        // the canon view is a read-side projection). Re-fetch the queue list
        // and find the matching entry. Cheap because the active queue is
        // typically < 10 items.
        const { listQueue } = await import("@/lib/your-kitchen-api");
        const entries = await listQueue();
        const match = entries.find((e) => e.dish_id === facts.dish_id);
        if (match) {
          await removeQueue.mutateAsync(match.id);
        }
      } else {
        await addQueue.mutateAsync({ slug: facts.slug });
      }
    },
    [addQueue, removeQueue],
  );

  if (canon.isLoading) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.surface.warm }}>
        <BackButton />
        <View style={{ flex: 1, alignItems: "center", justifyContent: "center" }}>
          <ActivityIndicator color={colors.accent.primary} />
        </View>
      </View>
    );
  }

  if (canon.isError) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.surface.warm }}>
        <BackButton />
        <View style={{ flex: 1, padding: spacing.xl, gap: spacing.md, alignItems: "center", justifyContent: "center" }}>
          <Ionicons name="cloud-offline-outline" size={iconSize.xl} color={colors.accent.danger} />
          <Text style={{ ...typography.h3, color: colors.text.primary, textAlign: "center" }}>
            Couldn&apos;t load your kitchen
          </Text>
          <Text style={{ ...typography.caption, color: colors.text.secondary, textAlign: "center", maxWidth: 280 }}>
            Check your connection and try again.
          </Text>
          <Pressable
            onPress={() => canon.refetch()}
            style={{ ...buttonStyles.primary, marginTop: spacing.sm }}
            accessibilityRole="button"
          >
            <Text style={buttonStyles.primaryText}>Try again</Text>
          </Pressable>
        </View>
      </View>
    );
  }

  const data = canon.data;
  const sections: CanonSection[] = data?.sections ?? [];
  const hasCanon = !!data?.has_canon;

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface.warm }}>
      <BackButton />
      <ScrollView
        contentContainerStyle={{
          paddingHorizontal: GRID_PADDING,
          paddingTop: headerTopPadding,
          paddingBottom: 120,
        }}
      >
        <View style={{ marginBottom: spacing.lg }}>
          <Text style={{ ...typography.tiny, color: colors.text.muted }}>YOUR KITCHEN</Text>
          <Text style={{ ...typography.h1, color: colors.text.primary }}>
            The dishes you love
          </Text>
          <Text style={{ ...typography.caption, color: colors.text.secondary, marginTop: 4 }}>
            Your household&apos;s canon — what fits you, when you last had it,
            who&apos;s been craving what.
          </Text>
        </View>

        {!hasCanon ? <DayZeroBand /> : null}

        {sections.map((section) => (
          <SectionView
            key={section.id}
            section={section}
            cellWidth={cellWidth}
            onOpen={openDish}
            onToggleQueue={toggleQueue}
            isQueueMutating={addQueue.isPending || removeQueue.isPending}
          />
        ))}

        {/* Demoted entry to the global catalog */}
        <Pressable
          onPress={() => router.push("/dish-catalog" as any)}
          accessibilityRole="button"
          accessibilityLabel="Browse all dishes"
          testID="browse-all-dishes"
          style={{
            marginTop: spacing.xl,
            padding: spacing.md,
            borderRadius: radius.md,
            borderWidth: 1,
            borderColor: colors.border.subtle,
            backgroundColor: colors.surface.card,
            flexDirection: "row",
            alignItems: "center",
            gap: spacing.md,
          }}
        >
          <Ionicons name="restaurant-outline" size={iconSize.lg} color={colors.accent.primary} />
          <View style={{ flex: 1 }}>
            <Text style={{ ...typography.bodyBold, color: colors.text.primary }}>
              Looking for something new?
            </Text>
            <Text style={{ ...typography.small, color: colors.text.secondary }}>
              Browse all dishes — outside your usual canon
            </Text>
          </View>
          <Ionicons name="chevron-forward" size={iconSize.sm} color={colors.text.secondary} />
        </Pressable>
      </ScrollView>
    </View>
  );
}

function SectionView({
  section,
  cellWidth,
  onOpen,
  onToggleQueue,
  isQueueMutating,
}: {
  section: CanonSection;
  cellWidth: number;
  onOpen: (slug: string) => void;
  onToggleQueue: (facts: DishHouseholdFacts) => void;
  isQueueMutating: boolean;
}) {
  const isSaved = section.id === "saved";
  // The "Saved by ..." section uses a wider single-column card so the credit
  // line + peculiarity get more room. Everything else is the 2-up grid.
  const useFullWidth = isSaved && section.dishes.length <= 3;

  return (
    <View>
      <SectionHeader title={section.title} subtitle={section.subtitle ?? undefined} />
      {useFullWidth ? (
        <View style={{ gap: GRID_GUTTER }}>
          {section.dishes.map((d) => (
            <HouseholdDishCard
              key={d.dish_id}
              facts={d}
              width={cellWidth * 2 + GRID_GUTTER}
              variant="row"
              onOpen={onOpen}
              onToggleQueue={onToggleQueue}
              isQueueMutating={isQueueMutating}
            />
          ))}
        </View>
      ) : (
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: GRID_GUTTER }}>
          {section.dishes.map((d) => (
            <HouseholdDishCard
              key={d.dish_id}
              facts={d}
              width={cellWidth}
              onOpen={onOpen}
              onToggleQueue={onToggleQueue}
              isQueueMutating={isQueueMutating}
            />
          ))}
        </View>
      )}
    </View>
  );
}

/**
 * Floating back button — present on every state of the screen (loading,
 * error, content). The screen is registered with `headerShown: false` in
 * _layout.tsx so the native back button is unavailable; this provides the
 * affordance manually.
 *
 * Uses safe-area insets so it sits below the notch on devices that have
 * one. `safeBack()` falls back to `/(tabs)` when there's nothing in the
 * stack (e.g. the user deep-linked straight here).
 */
function BackButton() {
  const insets = useSafeAreaInsets();
  return (
    <Pressable
      onPress={() => safeBack()}
      accessibilityRole="button"
      accessibilityLabel="Go back"
      hitSlop={12}
      testID="your-kitchen-back"
      style={{
        position: "absolute",
        top: Math.max(insets.top, 12) + 4,
        left: spacing.md,
        zIndex: 10,
        width: 40,
        height: 40,
        borderRadius: radius.pill,
        backgroundColor: colors.surface.elevated,
        borderWidth: 1,
        borderColor: colors.border.subtle,
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <Ionicons name="chevron-back" size={iconSize.sm} color={colors.text.primary} />
    </Pressable>
  );
}

function DayZeroBand() {
  return (
    <View
      testID="day-zero-band"
      style={{
        marginBottom: spacing.xl,
        padding: spacing.lg,
        borderRadius: radius.md,
        backgroundColor: colors.accent.primaryDim,
        borderWidth: 1,
        borderColor: colors.accent.primary,
        gap: spacing.sm,
      }}
    >
      <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
        <Ionicons name="sparkles" size={iconSize.md} color={colors.accent.primary} />
        <Text style={{ ...typography.bodyBold, color: colors.text.primary }}>
          Still building your kitchen
        </Text>
      </View>
      <Text style={{ ...typography.small, color: colors.text.secondary }}>
        Your canon fills up as your household eats together. After a few meals,
        Bimi will surface the dishes that fit you, the ones you haven&apos;t had
        in a while, and what your cook just learned.
      </Text>
      <Pressable
        onPress={() => router.push("/dish-catalog" as any)}
        style={{
          marginTop: spacing.sm,
          alignSelf: "flex-start",
          paddingHorizontal: spacing.md,
          paddingVertical: spacing.sm,
          borderRadius: radius.md,
          backgroundColor: colors.accent.primary,
        }}
        accessibilityRole="button"
        accessibilityLabel="Browse the dish catalog"
      >
        <Text style={{ ...typography.small, fontWeight: "700", color: colors.text.inverse }}>
          Browse the full catalog →
        </Text>
      </Pressable>
    </View>
  );
}
