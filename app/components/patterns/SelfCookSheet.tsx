/**
 * SelfCookSheet — bottom sheet of recipe ideas, opened from the home
 * cook-off banner ("Self cook ideas") and the day-detail modal's
 * per-meal "Self-cook ideas for breakfast/lunch/dinner" link.
 *
 * Two sections (when both have content):
 *   • "Your recipes"   — household-saved YouTube/Instagram links
 *   • "Easy ideas"     — curated quick-recipe seeds from the backend
 *
 * Plus a "+ Add your own" pill at the top so the user can paste a
 * new URL straight from the sheet without leaving the home flow.
 *
 * Card content per recipe (richer-than-link):
 *   • Thumbnail (CDN-served)
 *   • Title (canonical, prefers oEmbed when available)
 *   • Channel name (YouTube oEmbed, lazy-loaded per card)
 *   • Time + difficulty + diet badge (Veg / Non-veg / Vegan)
 *   • One descriptive tag chip (skips redundant "quick" tag)
 *   • "Cooked X times" badge if the household has finalised this dish
 *     before (matched against `useMealStore.mealHistory` by title)
 *   • Watch CTA with platform icon (YouTube red / Instagram pink)
 *
 * Each card is full-width tappable; tap = open the source URL via
 * Linking.openURL. We deliberately don't auto-resolve the cook-off
 * absence on tap — the user might want to flip through several
 * recipes before deciding. Resolution happens upstream: the day
 * sheet's cook-off banner and the home centre card both commit
 * `self_cook` BEFORE opening this sheet, so the absence is already
 * resolved by the time the user is browsing recipes here.
 */

import React, { useCallback, useMemo, useState } from "react";
import { Image, Linking, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { BottomSheet } from "../ui/BottomSheet";
import { RipplePressable } from "../RipplePressable";
import { useMealStore } from "@/lib/store";
import { useQuickRecipes } from "@/lib/use-quick-recipes";
import {
  useSavedRecipes,
  type SavedRecipe,
} from "@/lib/use-saved-recipes";
import { useYouTubeMeta, isYouTubeUrl } from "@/lib/use-youtube-meta";
import type { QuickRecipe } from "@/lib/quick-recipes";
import {
  colors,
  iconSize,
  radius,
  spacing,
  typography,
} from "@/lib/theme";
import type { MealType } from "@/lib/types";
import { AddRecipeSheet } from "./AddRecipeSheet";

const MEAL_LABEL: Record<MealType, string> = {
  breakfast: "Breakfast",
  lunch: "Lunch",
  dinner: "Dinner",
  snack: "Snack",
};

export interface SelfCookSheetProps {
  visible: boolean;
  onClose: () => void;
  /**
   * Which meal is being self-cooked. When supplied (partial-day
   * absence), the recipe filter narrows to that course; when omitted
   * (full-day absence), all courses are shown.
   */
  mealType?: MealType;
  /**
   * Cook's first name for the subtitle copy ("Easy ideas while Malti
   * is off"). Falls back to a neutral phrasing when undefined.
   */
  cookName?: string;
  /**
   * Household identity. Required to surface household-saved recipes
   * and to seed AddRecipeSheet's `family_id` field. When undefined
   * (e.g. demo mode without a hydrated household), the saved section
   * and the "+ Add" affordance are both hidden gracefully.
   */
  familyId?: string;
  /** Display name for "Saved by …" attribution on freshly-added recipes. */
  createdByName?: string;
}

export function SelfCookSheet({
  visible,
  onClose,
  mealType,
  cookName,
  familyId,
  createdByName,
}: SelfCookSheetProps) {
  const { data: curated, isLoading } = useQuickRecipes({ mealType });
  const { data: saved } = useSavedRecipes({
    familyId,
    course: mealType ?? undefined,
  });

  const [addOpen, setAddOpen] = useState(false);

  const handleOpen = useCallback(async (url: string | undefined) => {
    if (!url) return;
    const can = await Linking.canOpenURL(url).catch(() => false);
    if (can) {
      Linking.openURL(url).catch(() => {});
    }
  }, []);

  const title = mealType ? `${MEAL_LABEL[mealType]} ideas` : "Quick recipes";
  const subtitle = cookName
    ? `Easy ideas while ${cookName} is off`
    : "Easy ideas you can make in under 30 minutes";

  const savedList = saved ?? [];
  const curatedList = curated ?? [];
  const hasSaved = savedList.length > 0;
  const hasCurated = curatedList.length > 0;
  const showLoadingShell = isLoading && !hasCurated && !hasSaved;

  return (
    <>
      <BottomSheet
        visible={visible && !addOpen}
        onClose={onClose}
        title={title}
        subtitle={subtitle}
        scrollable
        maxHeightFraction={0.88}
      >
        <View style={{ paddingTop: spacing.md, paddingBottom: spacing.xl, gap: spacing.lg }}>
          {/* Add-your-own pill — always visible (when familyId known)
              so the affordance is discoverable from the first open,
              not hidden behind the cards. */}
          {familyId ? <AddYourOwnPill onPress={() => setAddOpen(true)} /> : null}

          {showLoadingShell ? (
            <View style={{ gap: spacing.md }}>
              <RecipeCardSkeleton />
              <RecipeCardSkeleton />
              <RecipeCardSkeleton />
            </View>
          ) : !hasSaved && !hasCurated ? (
            <EmptyState />
          ) : (
            <>
              {hasSaved ? (
                <SectionBlock title="Your recipes">
                  {savedList.map((s) => (
                    <SavedRecipeRow
                      key={s.id}
                      recipe={s}
                      onWatch={() => handleOpen(s.sourceUrl)}
                    />
                  ))}
                </SectionBlock>
              ) : null}

              {hasCurated ? (
                <SectionBlock title={hasSaved ? "Easy ideas" : undefined}>
                  {curatedList.map((c) => (
                    <CuratedRecipeRow
                      key={c.id}
                      recipe={c}
                      onWatch={() => handleOpen(c.youtubeUrl)}
                    />
                  ))}
                </SectionBlock>
              ) : null}
            </>
          )}
        </View>
      </BottomSheet>

      {/* Sibling sheet — when AddRecipeSheet is open, the SelfCookSheet
          collapses (visible={false}) so the user sees the add form
          full-bleed. Closing the add sheet brings the parent back. */}
      {familyId ? (
        <AddRecipeSheet
          visible={addOpen}
          onClose={() => setAddOpen(false)}
          mode={{ kind: "create", familyId, createdByName }}
        />
      ) : null}
    </>
  );
}

// ── Section scaffold ─────────────────────────────────────────────────

function SectionBlock({
  title,
  children,
}: {
  title?: string;
  children: React.ReactNode;
}) {
  return (
    <View style={{ gap: spacing.sm }}>
      {title ? (
        <Text
          style={{
            ...typography.tinyBold,
            color: colors.text.muted,
            textTransform: "uppercase",
            letterSpacing: 0.6,
          }}
        >
          {title}
        </Text>
      ) : null}
      <View style={{ gap: spacing.md }}>{children}</View>
    </View>
  );
}

// ── Add-your-own pill ────────────────────────────────────────────────

function AddYourOwnPill({ onPress }: { onPress: () => void }) {
  return (
    <RipplePressable
      onPress={onPress}
      haptic="selection"
      accessibilityRole="button"
      accessibilityLabel="Add your own recipe"
      style={{
        flexDirection: "row",
        alignItems: "center",
        gap: spacing.sm,
        paddingVertical: spacing.sm,
        paddingHorizontal: spacing.md,
        borderRadius: radius.md,
        borderWidth: 1,
        borderColor: colors.border.subtle,
        borderStyle: "dashed",
        backgroundColor: colors.surface.base,
      }}
    >
      <View
        style={{
          width: 28,
          height: 28,
          borderRadius: 14,
          backgroundColor: colors.accent.primaryDim,
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <Ionicons name="add" size={iconSize.sm} color={colors.accent.primary} />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={{ ...typography.bodyBold, color: colors.text.primary }}>
          Add your own
        </Text>
        <Text style={{ ...typography.tiny, color: colors.text.muted }}>
          Paste a YouTube or Instagram link.
        </Text>
      </View>
      <Ionicons name="chevron-forward" size={iconSize.sm} color={colors.text.muted} />
    </RipplePressable>
  );
}

// ── Recipe card (shape-agnostic) ─────────────────────────────────────
// Both curated and saved entries render through the same card. The
// row-specific wrappers (CuratedRecipeRow / SavedRecipeRow) compose
// their own metadata + CTA copy around it.

const CARD_IMAGE_SIZE = 100;

type DietBadge = "veg" | "non_veg" | "vegan" | "egg";

interface RecipeCardProps {
  imageUrl?: string;
  title: string;
  /** YouTube channel name (lazy oEmbed) or attribution byline. */
  channelLine?: string;
  description?: string;
  timeMins?: number;
  difficulty?: "easy" | "medium" | "hard";
  diet?: DietBadge;
  /** First descriptive tag (excludes "quick" since time meta covers it). */
  tag?: string;
  /** Times the household has cooked this dish before (from local meal history). */
  cookedCount?: number;
  /** "Saved by Anjan" / "From Bimi" type attribution. */
  byline?: string;
  watchLabel: string;
  watchIcon: keyof typeof Ionicons.glyphMap;
  watchTone?: "youtube" | "instagram" | "neutral";
  onWatch: () => void;
}

function RecipeCard({
  imageUrl,
  title,
  channelLine,
  description,
  timeMins,
  difficulty,
  diet,
  tag,
  cookedCount,
  byline,
  watchLabel,
  watchIcon,
  watchTone = "neutral",
  onWatch,
}: RecipeCardProps) {
  // Image-load error fallback. Saved recipes from a removed YouTube
  // video, or web URLs whose og:image stops resolving, would otherwise
  // ship a broken-image tile. Swap to the placeholder icon instead.
  const [imageBroken, setImageBroken] = useState(false);
  const showFallback = !imageUrl || imageBroken;

  const watchColor =
    watchTone === "youtube"
      ? colors.brand.youtube
      : watchTone === "instagram"
      ? colors.brand.instagram
      : colors.accent.primary;

  // Meta line — "12 min · Easy". Either side optional.
  const metaParts: string[] = [];
  if (timeMins != null) metaParts.push(`${timeMins} min`);
  if (difficulty) metaParts.push(capitalise(difficulty));
  const metaLine = metaParts.join(" · ");

  // IMPORTANT: layout structure note.
  //
  // RipplePressable forwards `flexDirection / gap / alignItems / justifyContent`
  // from its `style` onto the inner Pressable. When the consumer also
  // doesn't express "fill" intent (no `flex` / `height`), the Pressable
  // shrink-wraps to its content. A child with `flex: 1` inside a shrink-
  // wrapped row collapses to zero width — which is exactly what hid the
  // entire text column on this card in the previous revision.
  //
  // Safe pattern (mirrors `DayCardRow` and `DayMealSheet`'s `MealRow`):
  // keep ONLY chrome on the RipplePressable (background, radius, border,
  // overflow). Put the row layout on an INNER View. That inner View is
  // a column-axis child of the (default-column) Pressable, so it
  // stretches to the Pressable's full width — and the content column's
  // `flex: 1` then expands as expected.
  return (
    <RipplePressable
      onPress={onWatch}
      haptic="selection"
      accessibilityRole="link"
      accessibilityLabel={`${title}${
        channelLine ? `, ${channelLine}` : ""
      }${metaLine ? `, ${metaLine}` : ""}, ${watchLabel}`}
      style={{
        backgroundColor: colors.surface.card,
        borderRadius: radius.lg,
        overflow: "hidden",
      }}
    >
      <View
        style={{
          flexDirection: "row",
          gap: spacing.md,
          padding: spacing.sm,
        }}
      >
        <View
          style={{
            width: CARD_IMAGE_SIZE,
            height: CARD_IMAGE_SIZE,
            borderRadius: radius.md,
            overflow: "hidden",
            backgroundColor: colors.accent.primaryDim,
          }}
        >
          {showFallback ? (
            <View
              style={{
                flex: 1,
                alignItems: "center",
                justifyContent: "center",
                backgroundColor: colors.accent.primaryDim,
              }}
            >
              <Ionicons
                name="restaurant"
                size={iconSize.xl}
                color={colors.accent.primary}
              />
            </View>
          ) : (
            <Image
              source={{ uri: imageUrl! }}
              style={{ width: "100%", height: "100%" }}
              resizeMode="cover"
              onError={() => setImageBroken(true)}
            />
          )}
          {/* Cook-count corner badge — surfaces household familiarity
              without crowding the metadata column. */}
          {cookedCount != null && cookedCount > 0 ? (
            <View
              style={{
                position: "absolute",
                top: 4,
                right: 4,
                paddingHorizontal: 5,
                paddingVertical: 2,
                borderRadius: radius.sm,
                backgroundColor: "rgba(0,0,0,0.6)",
                flexDirection: "row",
                alignItems: "center",
                gap: 2,
              }}
            >
              <Ionicons name="flame" size={10} color={colors.text.inverse} />
              <Text
                style={{
                  ...typography.tinyBold,
                  color: colors.text.inverse,
                  fontSize: 10,
                }}
              >
                {cookedCount}×
              </Text>
            </View>
          ) : null}
        </View>

        <View style={{ flex: 1, justifyContent: "space-between", paddingVertical: 2 }}>
          <View style={{ gap: 2 }}>
            <Text
              style={{ ...typography.bodyBold, color: colors.text.primary }}
              numberOfLines={2}
            >
              {title}
            </Text>
            {channelLine ? (
              <Text
                style={{ ...typography.tiny, color: colors.text.secondary }}
                numberOfLines={1}
              >
                {channelLine}
              </Text>
            ) : null}
            {description ? (
              <Text
                style={{ ...typography.tiny, color: colors.text.muted, marginTop: 2 }}
                numberOfLines={2}
              >
                {description}
              </Text>
            ) : null}

            {/* Chip row — diet + tag + cook-count text on small screens */}
            {(diet || tag) ? (
              <View
                style={{
                  flexDirection: "row",
                  flexWrap: "wrap",
                  gap: 4,
                  marginTop: 4,
                }}
              >
                {diet ? <DietPill diet={diet} /> : null}
                {tag ? <TagPill label={tag} /> : null}
              </View>
            ) : null}

            {byline ? (
              <Text
                style={{
                  ...typography.tinyBold,
                  color: colors.text.muted,
                  marginTop: 4,
                }}
                numberOfLines={1}
              >
                {byline}
              </Text>
            ) : null}
          </View>

          <View
            style={{
              flexDirection: "row",
              alignItems: "center",
              justifyContent: "space-between",
              gap: spacing.sm,
              marginTop: 6,
            }}
          >
            <View style={{ flexDirection: "row", alignItems: "center", gap: 4, flexShrink: 1 }}>
              {metaLine ? (
                <>
                  <Ionicons
                    name="time-outline"
                    size={iconSize.xs}
                    color={colors.text.muted}
                  />
                  <Text
                    style={{ ...typography.tinyBold, color: colors.text.muted }}
                    numberOfLines={1}
                  >
                    {metaLine}
                  </Text>
                </>
              ) : null}
            </View>

            <View style={{ flexDirection: "row", alignItems: "center", gap: 3 }}>
              <Text
                style={{
                  ...typography.tinyBold,
                  color: watchColor,
                  letterSpacing: 0.3,
                  textTransform: "uppercase",
                }}
              >
                {watchLabel}
              </Text>
              <Ionicons
                name={watchIcon}
                size={iconSize.sm}
                color={watchColor}
              />
            </View>
          </View>
        </View>
      </View>
    </RipplePressable>
  );
}

// ── Curated row (QuickRecipe → RecipeCard) ──────────────────────────

function CuratedRecipeRow({
  recipe,
  onWatch,
}: {
  recipe: QuickRecipe;
  onWatch: () => void;
}) {
  const yt = useYouTubeMeta(recipe.youtubeUrl);
  const cookedCount = useCookCount(recipe.title);

  // First non-redundant descriptive tag. "quick" is omitted because
  // the time meta already conveys it; "easy" is omitted because the
  // difficulty meta does the same.
  const tag = pickDescriptiveTag(recipe.tags);
  const diet = mapDiet(recipe.dietType);
  const channelLine = yt.data?.channelName
    ? `by ${yt.data.channelName}`
    : undefined;

  // Prefer canonical YouTube title only if it's meaningfully different
  // from the seed title — otherwise the seed (which is short + curated)
  // wins for legibility.
  const title =
    yt.data?.title && yt.data.title.toLowerCase() !== recipe.title.toLowerCase()
      ? recipe.title // keep curated label even when oEmbed differs
      : recipe.title;

  return (
    <RecipeCard
      imageUrl={recipe.imageUrl}
      title={title}
      channelLine={channelLine}
      description={recipe.description}
      timeMins={recipe.totalTimeMins}
      difficulty={recipe.difficulty}
      diet={diet}
      tag={tag}
      cookedCount={cookedCount}
      watchLabel="Watch"
      watchIcon="logo-youtube"
      watchTone="youtube"
      onWatch={onWatch}
    />
  );
}

// ── Saved row (SavedRecipe → RecipeCard) ────────────────────────────

function SavedRecipeRow({
  recipe,
  onWatch,
}: {
  recipe: SavedRecipe;
  onWatch: () => void;
}) {
  // Lazy oEmbed for YouTube saves — fills in the channel name we
  // don't store locally.
  const yt = useYouTubeMeta(
    isYouTubeUrl(recipe.sourceUrl) ? recipe.sourceUrl : undefined,
  );
  const cookedCount = useCookCount(recipe.title);

  // Platform-specific watch CTA so the user knows where the link will
  // take them.
  const { watchLabel, watchIcon, watchTone } = (() => {
    switch (recipe.sourcePlatform) {
      case "youtube":
        return {
          watchLabel: "Watch" as const,
          watchIcon: "logo-youtube" as const,
          watchTone: "youtube" as const,
        };
      case "instagram":
        return {
          watchLabel: "View" as const,
          watchIcon: "logo-instagram" as const,
          watchTone: "instagram" as const,
        };
      default:
        return {
          watchLabel: "Open" as const,
          watchIcon: "open-outline" as const,
          watchTone: "neutral" as const,
        };
    }
  })();

  const channelLine = yt.data?.channelName
    ? `by ${yt.data.channelName}`
    : undefined;

  const tag = pickDescriptiveTag(recipe.tags);

  // Byline — "Saved by Anjan". Falls back to "Saved" when we don't
  // have a name (shared cook scenarios, older rows).
  const byline = recipe.createdByName
    ? `Saved by ${recipe.createdByName}`
    : "Saved";

  return (
    <RecipeCard
      imageUrl={recipe.imageUrl ?? undefined}
      title={recipe.title}
      channelLine={channelLine}
      description={recipe.description ?? undefined}
      timeMins={recipe.totalTimeMins ?? undefined}
      tag={tag}
      cookedCount={cookedCount}
      byline={byline}
      watchLabel={watchLabel}
      watchIcon={watchIcon}
      watchTone={watchTone}
      onWatch={onWatch}
    />
  );
}

// ── Pills (diet, tag) ────────────────────────────────────────────────

const DIET_THEME: Record<DietBadge, { label: string; bg: string; fg: string }> = {
  veg: { label: "Veg", bg: colors.accent.successDim, fg: colors.accent.success },
  non_veg: { label: "Non-veg", bg: colors.accent.dangerDim, fg: colors.accent.danger },
  vegan: { label: "Vegan", bg: colors.accent.successDim, fg: colors.accent.success },
  egg: { label: "Egg", bg: colors.accent.warningDim, fg: colors.accent.warning },
};

function DietPill({ diet }: { diet: DietBadge }) {
  const t = DIET_THEME[diet];
  return (
    <View
      style={{
        paddingHorizontal: spacing.xs + 2,
        paddingVertical: 1,
        borderRadius: radius.sm,
        backgroundColor: t.bg,
      }}
    >
      <Text
        style={{
          ...typography.tinyBold,
          color: t.fg,
          fontSize: 10,
          letterSpacing: 0.4,
          textTransform: "uppercase",
        }}
      >
        {t.label}
      </Text>
    </View>
  );
}

function TagPill({ label }: { label: string }) {
  return (
    <View
      style={{
        paddingHorizontal: spacing.xs + 2,
        paddingVertical: 1,
        borderRadius: radius.sm,
        backgroundColor: colors.surface.base,
        borderWidth: 1,
        borderColor: colors.border.subtle,
      }}
    >
      <Text
        style={{
          ...typography.tinyBold,
          color: colors.text.secondary,
          fontSize: 10,
          letterSpacing: 0.4,
          textTransform: "uppercase",
        }}
      >
        {label}
      </Text>
    </View>
  );
}

// ── Skeleton + empty state ──────────────────────────────────────────

function RecipeCardSkeleton() {
  return (
    <View
      style={{
        flexDirection: "row",
        gap: spacing.md,
        padding: spacing.sm,
        backgroundColor: colors.surface.card,
        borderRadius: radius.lg,
      }}
    >
      <View
        style={{
          width: CARD_IMAGE_SIZE,
          height: CARD_IMAGE_SIZE,
          borderRadius: radius.md,
          backgroundColor: colors.surface.elevated,
        }}
      />
      <View style={{ flex: 1, gap: spacing.sm, paddingVertical: 4 }}>
        <View style={{ height: 16, width: "60%", borderRadius: radius.sm, backgroundColor: colors.surface.elevated }} />
        <View style={{ height: 12, width: "90%", borderRadius: radius.sm, backgroundColor: colors.surface.elevated }} />
        <View style={{ height: 12, width: "40%", borderRadius: radius.sm, backgroundColor: colors.surface.elevated }} />
      </View>
    </View>
  );
}

function EmptyState() {
  return (
    <View
      style={{
        alignItems: "center",
        paddingVertical: spacing.xxxl,
        gap: spacing.md,
      }}
    >
      <Ionicons
        name="restaurant-outline"
        size={iconSize.xl}
        color={colors.text.muted}
      />
      <Text
        style={{ ...typography.body, color: colors.text.secondary, textAlign: "center" }}
      >
        Nothing to suggest right now.
      </Text>
      <Text
        style={{ ...typography.caption, color: colors.text.muted, textAlign: "center" }}
      >
        Tap "Add your own" to paste a recipe link.
      </Text>
    </View>
  );
}

// ── Helpers ──────────────────────────────────────────────────────────

function capitalise(s: string): string {
  return s.length === 0 ? s : s[0].toUpperCase() + s.slice(1);
}

function mapDiet(d: QuickRecipe["dietType"]): DietBadge | undefined {
  if (d === "vegetarian") return "veg";
  if (d === "non_vegetarian") return "non_veg";
  if (d === "vegan") return "vegan";
  if (d === "egg_only") return "egg";
  return undefined;
}

// "quick" duplicates the time meta, "easy" duplicates difficulty —
// both get filtered out so we never show the user redundant chips.
const NOISY_TAGS = new Set(["quick", "easy"]);

function pickDescriptiveTag(tags: readonly string[] | null | undefined): string | undefined {
  if (!tags || tags.length === 0) return undefined;
  for (const t of tags) {
    if (!NOISY_TAGS.has(t.toLowerCase())) return t;
  }
  return undefined;
}

/**
 * Counts how many times this household has finalised the dish (matched
 * by case-insensitive title) in their meal history. Exists as a hook
 * so the count is reactive to live syncs from other devices — when
 * Mayank's phone finalises another Maggi, Anjan's recipe card ticks up.
 */
function useCookCount(dishName: string): number {
  const history = useMealStore((s) => s.mealHistory);
  return useMemo(() => {
    const target = dishName.trim().toLowerCase();
    if (!target) return 0;
    return history.filter(
      (e) => e.selectedMeal.trim().toLowerCase() === target,
    ).length;
  }, [history, dishName]);
}
