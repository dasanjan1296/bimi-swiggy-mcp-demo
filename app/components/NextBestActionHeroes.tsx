/**
 * Hero variants for the Home's NextBestAction slot.
 *
 * Migrated to consume `<HeroCard>` from `components/patterns` so the home
 * priority tree stays in sync with the canonical HeroCard visual. Each
 * variant is a thin wrapper that picks the tone, icon, copy, and the
 * tap action — no per-variant styling is allowed.
 *
 * Strict design rule (per design-system.md §7): one primary CTA, no
 * secondary actions, no dismiss buttons, no nested links.
 *
 * Brand voice per .cursor/skills/bimi-app-development/SKILL.md:
 * first-person Bimi, warm guardian, Indian-context fluent ("didi",
 * "ghar", "khana"), understated.
 */

import React from "react";
import { View } from "react-native";
import { router } from "expo-router";
import type { ActionItem, MealPlan } from "@/lib/types";
import { HeroCard } from "@/components/patterns/HeroCard";
import { SwiggyBadge } from "@/components/patterns/SwiggyBadge";
import { cardStyles, colors, radius, spacing } from "@/lib/theme";

// Re-export for any caller that imported the previous custom HeroCard.
export { HeroCard } from "@/components/patterns/HeroCard";
export type { HeroCardProps, HeroTone } from "@/components/patterns/HeroCard";

// ──────────────────────────────────────────────────────────────────
// Hero variants
//
// 2026-05-03 audit (FRONTEND-BACKEND-COORDINATION.md): the
// `ActiveBookingHero` + `RateLastMealHero` variants are removed —
// they pushed users into the retired `/instacook-bookings` and
// `/feedback` screens. Insta Cook is no longer a Bimi feature.
// ──────────────────────────────────────────────────────────────────

// 2026-05-10 audit: the pre-Swiggy `GroceryApprovalHero` (and its
// `<CartApprovalSheet>`) were retired with the legacy auto-grocery-
// order approval flow. Swiggy MCP is now the single grocery path —
// the cook flags items, the household reviews + adds to Swiggy cart,
// inventory auto-restocks on delivery. See plan Phase 1.5.

// ──────────────────────────────────────────────────────────────────
// Plan + meal-status heroes
//
// 2026-05-03 audit: the voting tab is gone (folded into Today per
// redesign §7) — but the inline "What's for dinner?" picker that was
// supposed to replace it isn't built yet. CTAs that previously deep-
// linked to /(tabs)/voting now route to /your-kitchen (the closest
// surviving "what should we eat?" surface).
// ──────────────────────────────────────────────────────────────────

export function TomorrowVoteHero({ plan }: { plan: MealPlan }) {
  const mealLabel = plan.mealType.charAt(0).toUpperCase() + plan.mealType.slice(1);
  return (
    <HeroCard
      tone="warning"
      icon="calendar"
      title={`Tomorrow's ${mealLabel.toLowerCase()} isn't sorted yet`}
      subtitle="Open Your Kitchen and queue something for tomorrow."
      ctaLabel="Plan tomorrow"
      testID="hero-tomorrow-vote"
      onPress={() => router.push("/your-kitchen" as never)}
    />
  );
}

export function TodayMealStatusHero({ plan }: { plan: MealPlan | null }) {
  const isSorted = !!plan?.selectedMeal;
  const title = isSorted
    ? `${plan!.selectedMeal} for ${plan!.mealType}`
    : "Your kitchen's quiet right now";
  const subtitle = isSorted
    ? "I'll ping you if anything's off."
    : "No meal locked in yet — open Your Kitchen to plan one.";

  // When the day is sorted, this hero is pure narration ("Bimi is
  // reassuring you everything's fine"). A CTA chevron pointing at
  // /your-kitchen would imply an action that doesn't exist (the user
  // ISN'T being asked to plan anything — they already are planned).
  // The earlier "Open Your Kitchen" CTA on the sorted state was a
  // hold-over from the unset-meal copy and showed up as the bug
  // "tap this hero, nothing relevant opens". Calm narration only.
  if (isSorted) {
    return (
      <HeroCard
        tone="success"
        icon="leaf"
        title={title}
        subtitle={subtitle}
        testID="hero-today-meal"
      />
    );
  }

  return (
    <HeroCard
      tone="success"
      icon="leaf"
      title={title}
      subtitle={subtitle}
      ctaLabel="Open Your Kitchen"
      testID="hero-today-meal"
      onPress={() => router.push("/your-kitchen" as never)}
    />
  );
}

// 2026-05-03 audit: `OrderDinnerHero` was the no-cook ICP variant
// that pushed first-time users into /dish-catalog with a ₹500 credit
// pitch. Bimi now serves cook-households only (per NextBestAction
// scope note) AND Bimi Gold credits are gone (per founder call).
// `UnansweredCookPromptHero` pointed at /cook-question which was
// deleted with the ICP-pivot retirement. Both heroes are unreferenced
// — removed entirely.

// ──────────────────────────────────────────────────────────────────
// Cross-branch heroes
// ──────────────────────────────────────────────────────────────────

/** Matrix #6 — surfaces unread cook messages inline as a one-tap "Review &
 *  approve" surface. The CTA opens a CookActionsSheet (passed in by the
 *  parent) instead of routing into /cook-chat. The sheet presents each
 *  action as a one-tap decision, honoring the brand promise that Bimi
 *  pre-decides and the user just confirms.
 *
 *  Swiggy MCP demo branch: when every unresolved item is a structured
 *  grocery action (`itemName` populated by the cook-message intent
 *  parser, or by the curated demo seed in `mock-data.ts`), the hero
 *  swaps into a Swiggy-attributed cart-summary mode — sharper title
 *  ("4 grocery items from Malti"), aggregated price + ETA subtitle,
 *  "Review cart" CTA, and a "Powered by Swiggy" pill in the top-right
 *  corner. Otherwise falls back to the generic copy. */
export function UnreadCookMessageHero({
  primary,
  count,
  actions,
  onOpenSheet,
}: {
  primary: ActionItem;
  count: number;
  /** Full list of user-facing unresolved actions. The Swiggy-cart
   *  variant uses these to verify every item is structured-grocery
   *  shaped before swapping into the cart-summary copy. */
  actions: ActionItem[];
  /** Required — opens the CookActionsSheet bottom sheet on home. */
  onOpenSheet: () => void;
}) {
  // Swiggy-cart variant: every unresolved item is a structured grocery
  // request, so the hero presents itself as a placeable cart routed
  // through Swiggy MCP rather than a generic chat decision queue.
  const allStructuredGroceries =
    actions.length > 0 &&
    actions.every(
      (a) =>
        (a.type === "supply_request" || a.type === "low_stock") &&
        !!a.itemName,
    );

  if (allStructuredGroceries) {
    // Compliance: Swiggy Builders Club rules forbid surfacing prices /
    // ETAs we haven't fetched from real MCP. We compute neither here.
    // Driver name + per-item ₹ are kept in the data shape (in case we
    // want them later) but never rendered — see `<DemoSimulationBanner>`
    // mounted on the cart sheet that this hero opens.
    const cookFirstName = (actions[0]?.requestedBy ?? "")
      .split(" ")[0]
      ?.trim();

    const titleText = cookFirstName
      ? `${cookFirstName}'s grocery list · ${count}`
      : `${count} grocery item${count > 1 ? "s" : ""}`;

    return (
      <HeroCard
        // Keep red/danger — earlier explicit user preference for "action
        // required" framing. Swiggy attribution lives in `topRight`
        // instead of taking over the tone.
        tone="danger"
        icon="basket-outline"
        title={titleText}
        subtitle={`${count} item${count > 1 ? "s" : ""} · ready to place via Swiggy`}
        ctaLabel="Review cart"
        topRight={<SwiggyBadge size="pill" />}
        testID="hero-unread-cook-message"
        onPress={onOpenSheet}
      />
    );
  }

  // Generic fallback (mixed action types, no structured fields).
  const subtitle = (() => {
    switch (primary.type) {
      case "supply_request":
        return primary.description ||
          "She needs ingredients before she can keep going.";
      case "meal_query":
        return primary.description ||
          "She's checking what to make. Quick nod and she's off.";
      case "low_stock":
        return primary.description ||
          "Something's running low — she wants to know if she should use it.";
      case "absence":
        return primary.description ||
          "She's flagging an absence. Tap to acknowledge.";
      case "prep_failed":
        return primary.description ||
          "Today's prep didn't work out — she has a backup plan to suggest.";
      case "prep_note":
      default:
        return primary.description ||
          "She left a note about today's meal.";
    }
  })();

  const title =
    count > 1
      ? `${count} things from your cook`
      : "Your cook needs a quick nod";

  const subtitleWithTail =
    count > 1 ? `${subtitle} · +${count - 1} more` : subtitle;

  const ctaLabel = count > 1 ? "Review & approve" : "Approve";

  return (
    <HeroCard
      tone="danger"
      icon="chatbubble-ellipses"
      title={title}
      subtitle={subtitleWithTail}
      ctaLabel={ctaLabel}
      testID="hero-unread-cook-message"
      onPress={onOpenSheet}
    />
  );
}

/** Matrix #8 — festival lands tomorrow + cook on. */
export function FestivalTomorrowHero({
  name,
  description,
  dietaryOverride,
}: {
  name: string;
  description: string;
  dietaryOverride?: "pure_veg" | "sattvic" | "no_onion_garlic" | "fasting";
}) {
  const subtitle = (() => {
    if (dietaryOverride === "fasting") {
      return `${description}. I'll suggest fasting-friendly meals tomorrow.`;
    }
    if (dietaryOverride === "sattvic") {
      return `${description}. I'll lean sattvic for tomorrow's plan.`;
    }
    if (dietaryOverride === "pure_veg") {
      return `${description}. Tomorrow's suggestions will stay pure-veg.`;
    }
    if (dietaryOverride === "no_onion_garlic") {
      return `${description}. No onion / garlic in tomorrow's options.`;
    }
    return `${description}. Want help planning tomorrow's meal?`;
  })();

  return (
    <HeroCard
      tone="warning"
      icon="sparkles"
      title={`${name} tomorrow`}
      subtitle={subtitle}
      ctaLabel="Plan a festival meal"
      testID="hero-festival-tomorrow"
      onPress={() => router.push("/your-kitchen" as never)}
    />
  );
}

/** Matrix #2 — when all today's meals are rated AND every tomorrow slot is
 *  finalized, render a single "you're set" surface instead of a degraded
 *  version of the busy state. */
export function DayCompleteHero() {
  return (
    <HeroCard
      tone="success"
      icon="checkmark-circle"
      title="Tomorrow's sorted. Everyone's fed today."
      subtitle="I'll ping you only if anything actually needs you. Otherwise, take the evening back."
      ctaLabel="See tomorrow's plan"
      testID="hero-day-complete"
      onPress={() => router.push("/your-kitchen" as never)}
    />
  );
}

// ──────────────────────────────────────────────────────────────────
// Skeleton while hooks load
// ──────────────────────────────────────────────────────────────────

export function HeroSkeleton() {
  return (
    <View
      style={{
        ...cardStyles,
        backgroundColor: colors.surface.card,
        paddingVertical: spacing.md,
        paddingHorizontal: spacing.md,
        minHeight: 84,
      }}
    >
      <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
        <View
          style={{
            width: 40,
            height: 40,
            borderRadius: radius.pill,
            backgroundColor: colors.surface.elevated,
          }}
        />
        <View style={{ flex: 1, gap: 6 }}>
          <View
            style={{
              width: "60%",
              height: 14,
              borderRadius: 4,
              backgroundColor: colors.surface.elevated,
            }}
          />
          <View
            style={{
              width: "85%",
              height: 11,
              borderRadius: 4,
              backgroundColor: colors.surface.elevated,
            }}
          />
          <View
            style={{
              width: "30%",
              height: 9,
              borderRadius: 4,
              backgroundColor: colors.surface.elevated,
            }}
          />
        </View>
      </View>
    </View>
  );
}
