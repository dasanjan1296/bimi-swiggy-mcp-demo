/**
 * MealCard — image-led voting card for the Plan / Voting screen. At rest:
 * a confident dish photo + dish name + chevron toggle. Everything else
 * (time, match %, advance prep, fairness, recipe link, suggested-by line)
 * is hidden behind the chevron and revealed in an expanded tray.
 *
 * Tap the photo region to vote (calls `onSelect`). Tap the chevron / row
 * beneath the photo to toggle the detail tray (does NOT vote).
 *
 * Replaces the previous metadata-stuffed card. The dark-theme version of
 * this component is preserved on prior commits.
 */

import React, { useCallback, useState } from "react";
import {
  Image,
  LayoutAnimation,
  Linking,
  Platform,
  Pressable,
  Text,
  UIManager,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRecipeSourceStore } from "@/lib/store";
import { getDishImageByName } from "@/lib/dish-images";
import { MeterBar } from "../ui/MeterBar";
import { PhotoCard, type PhotoCardRibbon } from "./PhotoCard";
import {
  colors,
  iconSize,
  radius,
  spacing,
  typography,
} from "@/lib/theme";
import type { MealSuggestion, MealType } from "@/lib/types";

if (Platform.OS === "android" && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

export interface MealCardProps {
  suggestion: MealSuggestion;
  /** Selected by the user (their vote in this round). */
  isSelected?: boolean;
  /** Same as isSelected — kept for API compat. */
  isMyPick?: boolean;
  /** Tomorrow's locked-in winner. */
  isWinner?: boolean;
  /** Member names this dish was picked by (besides the user). */
  pickedBy?: string[];
  /** Vote handler. Called with the suggestion id. */
  onSelect?: (suggestionId: string) => void;
  /** Optional handler for "link a recipe" affordance in the detail tray. */
  onLinkRecipe?: (dishName: string) => void;
  /** When the regular cook is off on the serve day — flips advance-prep copy. */
  cookOffOnServeDay?: boolean;
  /** Cook name for advance-prep copy. */
  cookName?: string;
  /** Reserved for analytics / routing context. */
  mealType?: MealType;
  /**
   * Deprecated — the previous metadata-stuffed card had `compact` and
   * `variant: "compact" | "hero" | "standard"` size knobs. The image-led
   * card derives its layout from the photo, so these are accepted (for
   * existing call-sites) but ignored.
   */
  compact?: boolean;
  variant?: "compact" | "hero" | "standard";
  /** Reserved for future visual treatments — accepted, currently ignored. */
  recentIngredientOverlap?: number;
}

function MealCardImpl({
  suggestion,
  isSelected,
  isMyPick,
  isWinner,
  pickedBy,
  onSelect,
  onLinkRecipe,
  cookOffOnServeDay,
  cookName,
  mealType: _mealType,
  compact: _compact,
  variant: _variant,
  recentIngredientOverlap: _recentIngredientOverlap,
}: MealCardProps) {
  const [expanded, setExpanded] = useState(false);
  const defaultRecipe = useRecipeSourceStore((s) =>
    s.getDefaultForDish(suggestion.dishName),
  );
  const recipeCount = useRecipeSourceStore((s) =>
    s.getForDish(suggestion.dishName).length,
  );

  const image = getDishImageByName(suggestion.dishName);
  const ribbon: PhotoCardRibbon | undefined = isWinner
    ? { label: "Tomorrow's meal", tone: "success" }
    : isMyPick || isSelected
    ? { label: "Your pick", tone: "primary" }
    : undefined;

  const handleSelect = useCallback(() => {
    if (onSelect) onSelect(suggestion.id);
  }, [onSelect, suggestion.id]);

  const toggleExpand = useCallback(() => {
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    setExpanded((e) => !e);
  }, []);

  const confidencePercent = Math.round(suggestion.confidence * 100);

  return (
    <View style={{ marginBottom: spacing.md }}>
      <PhotoCard
        image={image}
        title=""
        textless
        aspectRatio={16 / 10}
        onPress={handleSelect}
        ribbon={ribbon}
        badge={
          suggestion.plateType === "non_veg"
            ? { kind: "non-veg" }
            : suggestion.plateType === "veg"
            ? { kind: "veg" }
            : undefined
        }
        accessibilityLabel={`${suggestion.dishName}${ribbon ? `, ${ribbon.label}` : ""}, tap to vote`}
      />

      <Pressable
        onPress={toggleExpand}
        accessibilityRole="button"
        accessibilityLabel={`${suggestion.dishName}${expanded ? ", hide details" : ", show details"}`}
        accessibilityState={{ expanded }}
        style={{
          flexDirection: "row",
          alignItems: "center",
          paddingVertical: spacing.md,
          paddingHorizontal: spacing.sm,
          gap: spacing.sm,
        }}
      >
        <Text style={{ ...typography.h2, flex: 1 }} numberOfLines={2}>
          {suggestion.dishName}
        </Text>
        <Ionicons
          name={expanded ? "chevron-up" : "chevron-down"}
          size={iconSize.md}
          color={colors.text.secondary}
        />
      </Pressable>

      {expanded && (
        <View
          style={{
            backgroundColor: colors.surface.card,
            borderRadius: radius.lg,
            padding: spacing.md,
            gap: spacing.md,
          }}
        >
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.md }}>
            <DetailItem icon="time-outline" label={suggestion.prepTime} />
            <DetailItem
              icon="analytics-outline"
              label={`${confidencePercent}% match`}
              tone="success"
            />
            {suggestion.noveltyBonus > 0.3 && (
              <DetailItem icon="sparkles" label="New" tone="warning" />
            )}
          </View>

          {(isMyPick || (pickedBy && pickedBy.length > 0)) && (
            <Text style={typography.small}>
              {isMyPick ? "Your pick" : ""}
              {isMyPick && pickedBy && pickedBy.length > 0 ? " · " : ""}
              {pickedBy && pickedBy.length > 0 ? pickedBy.join(" · ") : ""}
            </Text>
          )}

          {suggestion.needsAdvancePrep && (
            <View
              style={{
                backgroundColor: colors.accent.warningDim,
                borderRadius: radius.sm,
                padding: spacing.sm,
                flexDirection: "row",
                alignItems: "center",
                gap: spacing.sm,
              }}
            >
              <Ionicons
                name="alert-circle"
                size={iconSize.sm}
                color={colors.accent.warning}
              />
              <Text style={{ ...typography.small, color: colors.text.primary, flex: 1 }}>
                {cookOffOnServeDay
                  ? `Needs advance prep tonight — you'll need to ${suggestion.advancePrepNote?.toLowerCase() ?? "prep ingredients"}`
                  : cookName
                  ? `${cookName} will need to ${suggestion.advancePrepNote?.toLowerCase()}`
                  : `You'll need to ${suggestion.advancePrepNote?.toLowerCase()}`}
              </Text>
            </View>
          )}

          {(suggestion.constraints?.length ?? 0) > 0 && (
            <View style={{ gap: spacing.xs }}>
              {(suggestion.constraints || []).map((c, i) => (
                <View
                  key={i}
                  style={{
                    flexDirection: "row",
                    alignItems: "center",
                    gap: spacing.xs,
                    backgroundColor:
                      c.severity === "block"
                        ? colors.accent.dangerDim
                        : c.severity === "warning"
                        ? colors.accent.warningDim
                        : colors.accent.infoDim,
                    borderRadius: radius.sm,
                    paddingHorizontal: spacing.sm,
                    paddingVertical: spacing.xs,
                  }}
                >
                  <Ionicons
                    name={
                      c.severity === "block"
                        ? "close-circle"
                        : c.severity === "warning"
                        ? "warning"
                        : "information-circle"
                    }
                    size={iconSize.xs}
                    color={
                      c.severity === "block"
                        ? colors.accent.danger
                        : c.severity === "warning"
                        ? colors.accent.warning
                        : colors.accent.info
                    }
                  />
                  <Text style={{ ...typography.small, color: colors.text.primary, flex: 1 }}>
                    {c.description}
                  </Text>
                </View>
              ))}
            </View>
          )}

          {(suggestion.missingIngredients?.length ?? 0) > 0 && (
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.xs, alignItems: "center" }}>
              <Text style={{ ...typography.smallBold, color: colors.accent.danger }}>
                Missing:
              </Text>
              {(suggestion.missingIngredients || []).map((ing, i) => (
                <View
                  key={i}
                  style={{
                    backgroundColor: colors.accent.dangerDim,
                    borderRadius: radius.sm,
                    paddingHorizontal: spacing.xs + 2,
                    paddingVertical: 2,
                  }}
                >
                  <Text style={{ ...typography.tiny, color: colors.accent.danger }}>{ing}</Text>
                </View>
              ))}
            </View>
          )}

          <View
            style={{
              flexDirection: "row",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.xs }}>
              <Text style={typography.small}>Fairness</Text>
              <View style={{ width: 80 }}>
                <MeterBar
                  value={suggestion.fairnessScore}
                  tone={suggestion.fairnessScore > 0.8 ? "success" : "warning"}
                  size="sm"
                />
              </View>
            </View>
            {suggestion.sourceUrl ? (
              <RecipeLink
                onPress={() => Linking.openURL(suggestion.sourceUrl!)}
                platform={suggestion.sourcePlatform}
              />
            ) : defaultRecipe ? (
              <RecipeLink
                onPress={() => Linking.openURL(defaultRecipe.youtubeUrl)}
                platform="youtube"
                channel={defaultRecipe.channelName ?? undefined}
                extraCount={recipeCount > 1 ? recipeCount - 1 : 0}
              />
            ) : onLinkRecipe ? (
              <Pressable
                onPress={() => onLinkRecipe(suggestion.dishName)}
                hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
                style={{ flexDirection: "row", alignItems: "center", gap: 4 }}
              >
                <Ionicons name="link-outline" size={iconSize.xs} color={colors.accent.primary} />
                <Text style={{ ...typography.smallBold, color: colors.accent.primary }}>
                  Link recipe
                </Text>
              </Pressable>
            ) : null}
          </View>

          {suggestion.suggestedByName ? (
            <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
              <Ionicons name="person-outline" size={iconSize.xs} color={colors.text.muted} />
              <Text style={typography.small}>
                Suggested by {suggestion.suggestedByName}
              </Text>
            </View>
          ) : null}
        </View>
      )}
    </View>
  );
}

function DetailItem({
  icon,
  label,
  tone = "neutral",
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  tone?: "neutral" | "success" | "warning";
}) {
  const fg =
    tone === "success"
      ? colors.accent.success
      : tone === "warning"
      ? colors.accent.warning
      : colors.text.secondary;
  return (
    <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.xs }}>
      <Ionicons name={icon} size={iconSize.xs} color={fg} />
      <Text style={{ ...typography.small, color: fg }}>{label}</Text>
    </View>
  );
}

function RecipeLink({
  onPress,
  platform,
  channel,
  extraCount,
}: {
  onPress: () => void;
  platform?: "youtube" | "instagram" | "other";
  channel?: string;
  extraCount?: number;
}) {
  const icon =
    platform === "youtube"
      ? "logo-youtube"
      : platform === "instagram"
      ? "logo-instagram"
      : "link-outline";
  const fg =
    platform === "youtube"
      ? colors.brand.youtube
      : platform === "instagram"
      ? colors.brand.instagram
      : colors.accent.info;
  const label =
    channel ??
    (platform === "youtube"
      ? "YouTube"
      : platform === "instagram"
      ? "Reel"
      : "Recipe");
  return (
    <Pressable
      onPress={onPress}
      hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
      style={{ flexDirection: "row", alignItems: "center", gap: 4 }}
    >
      <Ionicons name={icon as any} size={iconSize.xs} color={fg} />
      <Text style={typography.small}>{label}</Text>
      {extraCount && extraCount > 0 ? (
        <Text style={typography.tiny}>+{extraCount}</Text>
      ) : null}
    </Pressable>
  );
}

export const MealCard = React.memo(MealCardImpl);
