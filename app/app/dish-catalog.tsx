/**
 * Dish Catalog — Swiggy-inspired primary browsing surface for the
 * household's recipe catalog.
 *
 * 2026-05-03 audit: previously a "buy this dish" flow with savings
 * badges + cart. After "no Insta Cook for now" + "delete Bimi Gold UI"
 * + "Dish Catalog and Recipe Archive are sort of the same", this is
 * now a read-only browse target. The household-context eyebrow reads
 * "RECIPES FOR" (not "ORDERING FOR") — no orders happen here.
 *
 * Layout (top to bottom):
 *   1. Back button (route is registered with headerShown: false)
 *   2. Top bar with "Recipes for {household}" + headcount chip
 *   3. Search bar with clear button
 *   3. Offer banner (first-dinner credit or Gold pitch) — dismissable / one-tap
 *   4. Cuisine chip row (All / North / Bengali / South / Hyderabadi)
 *   5. Meal-type chip row (any meal / breakfast / lunch / dinner)
 *   6. Veg-only toggle
 *   7. *When no filter is active and no search*: a curated section layout
 *      - Featured carousel (4 crowd-pleasers with large hero photos)
 *      - Popular on Bimi (grid, 6 dishes)
 *      - Chef's picks (grid, 4 dishes)
 *      - Quick bites (grid, base_time_minutes ≤ 25)
 *      - Bengali favourites (grid, bengali cuisine)
 *      - South Indian favourites (grid, south_indian cuisine)
 *      - "All {N} dishes" grid at the bottom
 *   8. *When any filter or search is active*: a single two-column grid of
 *      matches with an empty-state fallback.
 *   9. Floating cart CTA pinned to the bottom.
 *
 * Grid sections use `DishGridCard`; the featured carousel uses
 * `FeaturedDishCard`. Cuisine + meal filters live in state here; the
 * actual filtering is done client-side because the API already returns
 * the full catalog with one call.
 */

import React, { useCallback, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  Text,
  TextInput,
  useWindowDimensions,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { router, useLocalSearchParams } from "expo-router";
import { useQuery } from "@tanstack/react-query";
// 2026-05-03 audit: dish-api hooks repointed in Phase B — `fetchDishCatalog`
// now hits /recipe-archive (consolidated per founder call: "Dish Catalog
// and Recipe Archive are sort of the same"). Membership / Credits /
// dish-store are gone.
import {
  fetchDishCatalog,
  type Dish,
} from "@/lib/dish-api";
import { useHouseholdStore } from "@/lib/store";
import {
  buttonStyles,
  colors,
  iconSize,
  radius,
  spacing,
  typography,
} from "@/lib/theme";
import { EmptyStateGuide } from "@/components/GuidanceTip";
import { CuisineChip, type CuisineId } from "@/components/CuisineChip";
import { OfferBanner } from "@/components/OfferBanner";
import { SectionHeader } from "@/components/SectionHeader";
import { safeBack } from "@/lib/safe-back";
// 2026-05-03 audit: FeaturedDishCard was the savings-led carousel
// (showed "Save ₹X vs Swiggy" on dish hero cards) — deleted alongside
// Bimi Gold UI. The "Tonight's specials" carousel below is also
// removed; popular / chef-picks / category sections still render.
import { DishGridCard } from "@/components/DishGridCard";
import type { RibbonVariant } from "@/components/RibbonBadge";

type VegFilter = "all" | "veg" | "non_veg";
type MealFilter = "all" | "breakfast" | "lunch" | "dinner";

/**
 * Curated lists. These are the only places we encode taste — keep them
 * small and meaningful. Order matters: the first dish in `FEATURED_SLUGS`
 * is the very first thing users see on app open.
 */
const FEATURED_SLUGS = [
  "butter-chicken",
  "kosha-mangsho",
  "masala-dosa",
  "paneer-butter-masala",
];
const CHEF_PICK_SLUGS = new Set([
  "kosha-mangsho",
  "chicken-chettinad",
  "fish-moilee",
  "dal-makhani",
]);
const BESTSELLER_SLUGS = new Set([
  "butter-chicken",
  "paneer-butter-masala",
  "chicken-biryani",
  "masala-dosa",
  "rajma-chawal",
]);

function ribbonFor(dish: Dish): RibbonVariant | undefined {
  if (BESTSELLER_SLUGS.has(dish.slug)) return "bestseller";
  if (CHEF_PICK_SLUGS.has(dish.slug)) return "chef_pick";
  if (dish.base_time_minutes <= 25) return "quick";
  return undefined;
}

// 2026-05-03 audit: portion_tiers + swiggy_per_serving were Bimi Gold
// pricing fields. The recipe-archive backend doesn't carry them. The
// `savings` half of the helper is meaningless without backend pricing,
// and `priceFrom` is unused by the read-only catalog. Returning zeros
// keeps the existing call signatures alive without dead behaviour.
function savingsForDish(_d: Dish): { priceFrom: number; saves: number } {
  return { priceFrom: 0, saves: 0 };
}

function headcountLabel(household: ReturnType<typeof useHouseholdStore.getState>["household"]): string {
  const activeMembers = household?.members?.filter((m) => m.isActive).length ?? 0;
  if (!activeMembers) return "Solo";
  if (activeMembers === 1) return "1 person";
  return `${activeMembers} people`;
}

export default function DishCatalogScreen() {
  // The `?cuisine=bengali` deep link lets us open the catalog pre-scoped
  // to a cuisine from other screens (e.g. home "Try Bengali dinner tonight").
  const params = useLocalSearchParams<{ cuisine?: string }>();

  const [vegFilter, setVegFilter] = useState<VegFilter>("all");
  const [mealFilter, setMealFilter] = useState<MealFilter>("all");
  const [cuisineFilter, setCuisineFilter] = useState<CuisineId>(
    (params.cuisine as CuisineId | undefined) &&
      ["all", "north_indian", "bengali", "south_indian", "hyderabadi"].includes(params.cuisine as string)
      ? (params.cuisine as CuisineId)
      : "all",
  );
  const [search, setSearch] = useState("");
  // 2026-05-03 audit: cart, membership, and credit state removed —
  // ordering moved out of the in-app cart. Bimi Recipes (this screen)
  // is now read-only browsing of the recipe archive; queueing a dish
  // for the cook happens via /your-kitchen/queue (existing endpoint).
  const household = useHouseholdStore((s) => s.household);
  const isGold = false;

  const dishesQuery = useQuery<Dish[]>({
    queryKey: ["dishes", vegFilter, mealFilter],
    queryFn: () =>
      fetchDishCatalog({
        is_veg: vegFilter === "veg" ? true : vegFilter === "non_veg" ? false : undefined,
        meal_type: mealFilter !== "all" ? mealFilter : undefined,
      }),
    staleTime: 30_000,
  });

  const filteredDishes = useMemo(() => {
    const list = dishesQuery.data ?? [];
    const q = search.trim().toLowerCase();
    return list.filter((d) => {
      if (cuisineFilter !== "all" && d.cuisine !== cuisineFilter) return false;
      if (!q) return true;
      return (
        d.name.toLowerCase().includes(q) ||
        d.slug.toLowerCase().includes(q) ||
        (d.description ?? "").toLowerCase().includes(q)
      );
    });
  }, [dishesQuery.data, search, cuisineFilter]);

  const cuisineCounts = useMemo(() => {
    const list = dishesQuery.data ?? [];
    const counts: Record<CuisineId, number> = {
      all: list.length,
      north_indian: 0,
      bengali: 0,
      south_indian: 0,
      hyderabadi: 0,
    };
    for (const d of list) {
      if ((counts as Record<string, number>)[d.cuisine] !== undefined) {
        counts[d.cuisine as CuisineId] += 1;
      }
    }
    return counts;
  }, [dishesQuery.data]);

  const hasFilter = cuisineFilter !== "all" || search.trim().length > 0;

  // ─── Curated list resolvers (only used on the sectioned home view) ───

  const allDishes = filteredDishes;

  const featured = useMemo(() => {
    const bySlug = new Map(allDishes.map((d) => [d.slug, d]));
    return FEATURED_SLUGS.map((s) => bySlug.get(s)).filter(Boolean) as Dish[];
  }, [allDishes]);

  const popular = useMemo(
    () => [...allDishes].sort((a, b) => a.display_order - b.display_order).slice(0, 6),
    [allDishes],
  );

  const chefPicks = useMemo(
    () => allDishes.filter((d) => CHEF_PICK_SLUGS.has(d.slug)),
    [allDishes],
  );

  const quickBites = useMemo(
    () =>
      [...allDishes]
        .filter((d) => d.base_time_minutes <= 25)
        .sort((a, b) => a.base_time_minutes - b.base_time_minutes)
        .slice(0, 6),
    [allDishes],
  );

  const bengali = useMemo(
    () => allDishes.filter((d) => d.cuisine === "bengali").slice(0, 6),
    [allDishes],
  );
  const southIndian = useMemo(
    () => allDishes.filter((d) => d.cuisine === "south_indian").slice(0, 6),
    [allDishes],
  );

  // useWindowDimensions subscribes to size changes — matters on web
  // (browser resize) and iPad split-view, where Dimensions.get('window')
  // would have returned the original size and the grid cells would
  // overflow / leave gaps until a route change forced a re-render.
  const { width: screenWidth } = useWindowDimensions();
  const gridGutter = spacing.md;
  const gridPadding = spacing.lg;
  const gridCellWidth = (screenWidth - gridPadding * 2 - gridGutter) / 2;

  // Stable so each DishGridCard's React.memo isn't busted on every
  // search keystroke or filter change. router is a singleton from
  // expo-router; useCallback with empty deps is safe.
  const openDish = useCallback(
    (slug: string) => router.push({ pathname: "/dish/[slug]", params: { slug } }),
    [],
  );

  // ─── Render ───

  return (
    <View style={{ flex: 1, backgroundColor: colors.surface.warm }}>
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{
          paddingHorizontal: gridPadding,
          paddingTop: 60,
          paddingBottom: 140,
        }}
        keyboardShouldPersistTaps="handled"
      >
        {/* Back button — the screen is registered in app/_layout.tsx
            with headerShown: false, so we own the navigation. Sits
            above the household top-bar so it's the first tap target
            in reading order. Uses `safeBack` so a cold-launch deep
            link or hot reload (which leaves the stack empty) still
            lands the user back on the tabs root instead of throwing
            "GO_BACK was not handled". */}
        <Pressable
          onPress={() => safeBack()}
          accessibilityRole="button"
          accessibilityLabel="Back"
          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          style={{
            flexDirection: "row",
            alignItems: "center",
            gap: 4,
            alignSelf: "flex-start",
            marginBottom: spacing.md,
            paddingVertical: spacing.xs,
          }}
        >
          <Ionicons name="chevron-back" size={iconSize.md} color={colors.text.primary} />
          <Text style={{ ...typography.caption, color: colors.text.primary }}>
            Back
          </Text>
        </Pressable>

        {/* Top bar: household + headcount */}
        <View
          style={{
            flexDirection: "row",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: spacing.md,
          }}
        >
          <View style={{ flex: 1 }}>
            <Text style={{ ...typography.tiny, color: colors.text.muted }}>
              RECIPES FOR
            </Text>
            <Text style={{ ...typography.h2, color: colors.text.primary }} numberOfLines={1}>
              {household?.name ?? "Your kitchen"}
            </Text>
          </View>
          <Pressable
            onPress={() => router.push("/settings")}
            accessibilityLabel="Edit household"
            hitSlop={8}
            style={{
              flexDirection: "row",
              alignItems: "center",
              gap: 4,
              paddingHorizontal: 10,
              paddingVertical: 6,
              borderRadius: radius.pill,
              borderWidth: 1,
              borderColor: colors.border.subtle,
              backgroundColor: colors.surface.card,
            }}
          >
            <Ionicons name="people" size={iconSize.xs} color={colors.accent.primary} />
            <Text style={{ ...typography.small, color: colors.text.primary, fontWeight: "600" }}>
              {headcountLabel(household)}
            </Text>
          </Pressable>
        </View>

        {/* Search */}
        <View
          style={{
            flexDirection: "row",
            alignItems: "center",
            backgroundColor: colors.surface.input,
            borderRadius: radius.md,
            borderWidth: 1,
            borderColor: colors.border.subtle,
            paddingHorizontal: spacing.md,
            marginBottom: spacing.md,
          }}
        >
          <Ionicons name="search" size={iconSize.sm} color={colors.text.secondary} />
          <TextInput
            value={search}
            onChangeText={setSearch}
            placeholder="Search dishes or chefs (butter chicken, Ranveer Brar…)"
            placeholderTextColor={colors.text.muted}
            style={{
              flex: 1,
              padding: spacing.md,
              color: colors.text.primary,
              fontSize: 14,
            }}
            testID="dish-search-input"
          />
          {search.length > 0 && (
            <Pressable onPress={() => setSearch("")} accessibilityLabel="Clear search">
              <Ionicons name="close-circle" size={iconSize.sm} color={colors.text.muted} />
            </Pressable>
          )}
        </View>

        {/* 2026-05-03 audit: credit + gold offer banners removed
            alongside Bimi Gold / membership / credits backend retirement. */}

        {/* Cuisine chips */}
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={{ gap: spacing.sm, paddingRight: spacing.md }}
          style={{ marginHorizontal: -gridPadding, paddingHorizontal: gridPadding, marginBottom: spacing.md }}
        >
          {(["all", "north_indian", "bengali", "south_indian", "hyderabadi"] as CuisineId[]).map(
            (c) => (
              <CuisineChip
                key={c}
                cuisine={c}
                active={cuisineFilter === c}
                count={cuisineCounts[c]}
                onPress={() => setCuisineFilter(c)}
              />
            ),
          )}
        </ScrollView>

        {/* Meal + veg row */}
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={{ gap: spacing.sm, paddingRight: spacing.md }}
          style={{ marginHorizontal: -gridPadding, paddingHorizontal: gridPadding, marginBottom: spacing.md }}
        >
          {(
            [
              { id: "all", label: "Any meal", icon: "restaurant-outline" as const },
              { id: "breakfast", label: "Breakfast", icon: "sunny-outline" as const },
              { id: "lunch", label: "Lunch", icon: "partly-sunny-outline" as const },
              { id: "dinner", label: "Dinner", icon: "moon-outline" as const },
            ] as Array<{ id: MealFilter; label: string; icon: keyof typeof Ionicons.glyphMap }>
          ).map((opt) => (
            <FilterChip
              key={`meal-${opt.id}`}
              label={opt.label}
              icon={opt.icon}
              active={mealFilter === opt.id}
              onPress={() => setMealFilter(opt.id)}
            />
          ))}
          <View style={{ width: 2 }} />
          {(
            [
              { id: "all", label: "All", icon: "ellipse-outline" as const },
              { id: "veg", label: "Veg", icon: "leaf-outline" as const },
              { id: "non_veg", label: "Non-veg", icon: "flame-outline" as const },
            ] as Array<{ id: VegFilter; label: string; icon: keyof typeof Ionicons.glyphMap }>
          ).map((opt) => (
            <FilterChip
              key={`veg-${opt.id}`}
              label={opt.label}
              icon={opt.icon}
              active={vegFilter === opt.id}
              onPress={() => setVegFilter(opt.id)}
            />
          ))}
        </ScrollView>

        {/* Content */}
        {dishesQuery.isLoading ? (
          <View style={{ padding: spacing.xxl, alignItems: "center" }}>
            <ActivityIndicator color={colors.accent.primary} />
          </View>
        ) : dishesQuery.isError ? (
          <View style={{ padding: spacing.xxl, alignItems: "center", gap: spacing.md }}>
            <Ionicons
              name="cloud-offline-outline"
              size={iconSize.xl}
              color={colors.accent.danger}
            />
            <Text style={{ ...typography.h3, color: colors.text.primary, textAlign: "center" }}>
              Couldn't load the dish catalog
            </Text>
            <Text
              style={{
                ...typography.caption,
                color: colors.text.secondary,
                textAlign: "center",
                maxWidth: 280,
              }}
            >
              Check your connection and try again. Your selections aren't lost.
            </Text>
            <Pressable
              onPress={() => dishesQuery.refetch()}
              accessibilityRole="button"
              accessibilityLabel="Retry loading dishes"
              style={{ ...buttonStyles.primary, marginTop: spacing.sm }}
            >
              <Text style={buttonStyles.primaryText}>Try again</Text>
            </Pressable>
          </View>
        ) : hasFilter ? (
          filteredDishes.length === 0 ? (
            <EmptyStateGuide
              icon="restaurant-outline"
              title="No dishes match"
              message="Try a different cuisine or clear the search."
            />
          ) : (
            <Grid
              dishes={filteredDishes}
              cellWidth={gridCellWidth}
              gutter={gridGutter}
              onPress={openDish}
              isGold={isGold}
            />
          )
        ) : (
          <SectionedView
            featured={featured}
            popular={popular}
            chefPicks={chefPicks}
            quickBites={quickBites}
            bengali={bengali}
            southIndian={southIndian}
            all={allDishes}
            cellWidth={gridCellWidth}
            gutter={gridGutter}
            gridPadding={gridPadding}
            onPress={openDish}
            onSeeAll={(c: CuisineId) => setCuisineFilter(c)}
            isGold={isGold}
          />
        )}

        {/* Your Kitchen entry point — promotes the personal-canon view as the
            default browsing experience (PRD §4.13). This sits above the
            custom-cooking link because for established households it should
            be the first thing they reach for when they open the catalog. */}
        <Pressable
          onPress={() => router.push("/your-kitchen" as any)}
          accessibilityRole="button"
          accessibilityLabel="Open Your Kitchen — your household's canon"
          testID="enter-your-kitchen"
          style={{
            marginTop: spacing.xl,
            padding: spacing.md,
            borderRadius: radius.md,
            borderWidth: 1,
            borderColor: colors.accent.primary,
            backgroundColor: colors.accent.primaryDim,
            flexDirection: "row",
            alignItems: "center",
            gap: spacing.md,
          }}
        >
          <Ionicons name="bookmark" size={iconSize.lg} color={colors.accent.primary} />
          <View style={{ flex: 1 }}>
            <Text style={{ ...typography.bodyBold, color: colors.text.primary }}>
              Your Kitchen
            </Text>
            <Text style={{ ...typography.small, color: colors.text.secondary }}>
              The dishes your household actually loves
            </Text>
          </View>
          <Ionicons name="chevron-forward" size={iconSize.sm} color={colors.accent.primary} />
        </Pressable>

        {/* 2026-05-03 audit: removed the "voting tab" deep-link
            (voting tab is gone) and the floating cart CTA (in-app
            ordering is gone). This screen is now a read-only
            recipe browse — to queue a dish for the cook, the user
            taps a recipe card and uses Your Kitchen's Queue button. */}
      </ScrollView>
    </View>
  );
}

// ─── Subcomponents ───

function FilterChip({
  label,
  icon,
  active,
  onPress,
}: {
  label: string;
  icon: keyof typeof Ionicons.glyphMap;
  active: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={`${label} filter`}
      accessibilityState={{ selected: active }}
      style={{
        flexDirection: "row",
        alignItems: "center",
        gap: 5,
        paddingHorizontal: 12,
        paddingVertical: 8,
        borderRadius: radius.pill,
        borderWidth: 1,
        borderColor: active ? colors.accent.primary : colors.border.subtle,
        backgroundColor: active ? colors.accent.primary : colors.surface.card,
      }}
    >
      <Ionicons
        name={icon}
        size={iconSize.xs}
        color={active ? colors.text.inverse : colors.accent.primary}
      />
      <Text
        style={{
          fontSize: 13,
          fontWeight: "600",
          color: active ? colors.text.inverse : colors.text.primary,
        }}
      >
        {label}
      </Text>
    </Pressable>
  );
}

function Grid({
  dishes,
  cellWidth,
  gutter,
  onPress,
  isGold,
}: {
  dishes: Dish[];
  cellWidth: number;
  gutter: number;
  onPress: (slug: string) => void;
  isGold: boolean;
}) {
  return (
    <View
      style={{
        flexDirection: "row",
        flexWrap: "wrap",
        gap: gutter,
      }}
    >
      {dishes.map((dish) => (
        <DishGridCard
          key={dish.id}
          dish={dish}
          width={cellWidth}
          isGold={isGold}
          ribbon={ribbonFor(dish)}
          onPress={onPress}
        />
      ))}
    </View>
  );
}

function SectionedView({
  featured,
  popular,
  chefPicks,
  quickBites,
  bengali,
  southIndian,
  all,
  cellWidth,
  gutter,
  gridPadding,
  onPress,
  onSeeAll,
  isGold,
}: {
  featured: Dish[];
  popular: Dish[];
  chefPicks: Dish[];
  quickBites: Dish[];
  bengali: Dish[];
  southIndian: Dish[];
  all: Dish[];
  cellWidth: number;
  gutter: number;
  gridPadding: number;
  onPress: (slug: string) => void;
  onSeeAll: (c: CuisineId) => void;
  isGold: boolean;
}) {
  return (
    <View>
      {/* 2026-05-03 audit: featured carousel removed — see import note. */}

      {popular.length > 0 ? (
        <>
          <SectionHeader title="Popular on Bimi" icon="flame" />
          <Grid dishes={popular} cellWidth={cellWidth} gutter={gutter} onPress={onPress} isGold={isGold} />
        </>
      ) : null}

      {chefPicks.length > 0 ? (
        <>
          <SectionHeader title="Chef's picks" subtitle="Hand-selected from master chefs" icon="star" />
          <Grid dishes={chefPicks} cellWidth={cellWidth} gutter={gutter} onPress={onPress} isGold={isGold} />
        </>
      ) : null}

      {quickBites.length > 0 ? (
        <>
          <SectionHeader title="Quick bites" subtitle="Under 25 minutes" icon="timer" />
          <Grid dishes={quickBites} cellWidth={cellWidth} gutter={gutter} onPress={onPress} isGold={isGold} />
        </>
      ) : null}

      {bengali.length > 0 ? (
        <>
          <SectionHeader
            title="Bengali favourites"
            subtitle="Mustard oil, mishti doi energy"
            actionLabel="See all"
            onAction={() => onSeeAll("bengali")}
          />
          <Grid dishes={bengali} cellWidth={cellWidth} gutter={gutter} onPress={onPress} isGold={isGold} />
        </>
      ) : null}

      {southIndian.length > 0 ? (
        <>
          <SectionHeader
            title="South Indian"
            subtitle="Dosa, idli, curry leaves and coconut"
            actionLabel="See all"
            onAction={() => onSeeAll("south_indian")}
          />
          <Grid dishes={southIndian} cellWidth={cellWidth} gutter={gutter} onPress={onPress} isGold={isGold} />
        </>
      ) : null}

      {all.length > 0 ? (
        <>
          <SectionHeader
            title={`All ${all.length} dishes`}
            subtitle="Every home-cooked meal on Bimi"
            icon="restaurant"
          />
          <Grid dishes={all} cellWidth={cellWidth} gutter={gutter} onPress={onPress} isGold={isGold} />
        </>
      ) : null}
    </View>
  );
}
