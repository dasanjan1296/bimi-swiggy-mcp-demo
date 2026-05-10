/**
 * Saved recipes — household management screen.
 *
 * Linked from `/settings → Saved recipes`. Lists every active saved
 * recipe for the current household; tap a row to open AddRecipeSheet
 * in edit mode, swipe-icon to delete (soft-delete via DELETE).
 *
 * Add affordance is duplicated from the home SelfCookSheet so users
 * who land here directly from settings can still grow the catalog.
 */

import React, { useCallback, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Image,
  Linking,
  Text,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useHouseholdStore } from "@/lib/store";
import { useAuthStore } from "@/lib/auth-store";
import {
  useDeleteSavedRecipe,
  useSavedRecipes,
  type SavedRecipe,
} from "@/lib/use-saved-recipes";
import { showAlert } from "@/lib/dialogs";
import { toast } from "@/lib/toast";
import { haptic } from "@/lib/haptics";
import { AddRecipeSheet } from "@/components/patterns/AddRecipeSheet";
import { RipplePressable } from "@/components/RipplePressable";
import { SafeScreen, ScreenHeader, Button } from "@/components/ui";
import { EmptyStateGuide } from "@/components/GuidanceTip";
import {
  colors,
  iconSize,
  radius,
  spacing,
  typography,
} from "@/lib/theme";

export default function SavedRecipesRoute() {
  const household = useHouseholdStore((s) => s.household);
  const childId = useAuthStore((s) => s.childId);
  const authName = useAuthStore((s) => s.childName);
  const familyId = household?.id;

  const createdByName = (() => {
    if (!household) return authName || undefined;
    const member =
      household.members.find((m) => m.id === childId) ??
      household.members.find((m) => m.isActive);
    return member?.name || authName || undefined;
  })();

  const { data: recipes, isLoading } = useSavedRecipes({ familyId });
  const deleteRecipe = useDeleteSavedRecipe();

  const [sheetMode, setSheetMode] = useState<
    | { kind: "create" }
    | { kind: "edit"; recipe: SavedRecipe }
    | null
  >(null);

  const handleOpenSource = useCallback(async (url: string | undefined) => {
    if (!url) return;
    const can = await Linking.canOpenURL(url).catch(() => false);
    if (can) Linking.openURL(url).catch(() => {});
  }, []);

  const handleDelete = useCallback(
    (recipe: SavedRecipe) => {
      showAlert(
        "Delete this recipe?",
        `"${recipe.title}" will be removed from your saved list. You can re-add it any time.`,
        [
          { text: "Cancel", style: "cancel" },
          {
            text: "Delete",
            style: "destructive",
            onPress: async () => {
              haptic("warning");
              try {
                await deleteRecipe.mutateAsync({
                  id: recipe.id,
                  familyId: recipe.familyId,
                });
                toast.success("Removed");
              } catch {
                toast.error("Couldn't remove", "Try again.");
              }
            },
          },
        ],
      );
    },
    [deleteRecipe],
  );

  return (
    <SafeScreen edges={["top", "bottom"]} ambientBackdrop>
      <ScreenHeader
        back
        title="Saved recipes"
        subtitle="Your household's YouTube and Instagram recipe links."
      />

      {!familyId ? (
        <View style={{ paddingHorizontal: spacing.lg }}>
          <EmptyStateGuide
            icon="bookmark-outline"
            title="Set up a household first"
            message="Saved recipes are shared with everyone in your household. Create or join a household to start saving."
          />
        </View>
      ) : isLoading && !recipes ? (
        <View style={{ paddingTop: spacing.xxl, alignItems: "center" }}>
          <ActivityIndicator color={colors.accent.primary} />
        </View>
      ) : (
        <FlatList
          data={recipes ?? []}
          keyExtractor={(r) => r.id}
          contentContainerStyle={{ paddingHorizontal: spacing.lg, paddingBottom: 140 }}
          ListHeaderComponent={
            <View style={{ marginBottom: spacing.md }}>
              <Button
                variant="primary"
                size="md"
                leadingIcon="add"
                onPress={() => setSheetMode({ kind: "create" })}
                fullWidth
              >
                Add a recipe
              </Button>
            </View>
          }
          ItemSeparatorComponent={() => <View style={{ height: spacing.md }} />}
          ListEmptyComponent={
            <View style={{ marginTop: spacing.xl }}>
              <EmptyStateGuide
                icon="bookmark-outline"
                title="Nothing saved yet"
                message="Found a recipe you love on YouTube or Instagram? Tap 'Add a recipe' above and paste the link."
              />
            </View>
          }
          renderItem={({ item }) => (
            <SavedRow
              recipe={item}
              onOpen={() => handleOpenSource(item.sourceUrl)}
              onEdit={() => setSheetMode({ kind: "edit", recipe: item })}
              onDelete={() => handleDelete(item)}
            />
          )}
        />
      )}

      {familyId && sheetMode ? (
        <AddRecipeSheet
          visible={!!sheetMode}
          onClose={() => setSheetMode(null)}
          mode={
            sheetMode.kind === "create"
              ? { kind: "create", familyId, createdByName }
              : { kind: "edit", recipe: sheetMode.recipe }
          }
        />
      ) : null}
    </SafeScreen>
  );
}

// ── Row ──────────────────────────────────────────────────────────────

const ROW_IMAGE_SIZE = 64;

function SavedRow({
  recipe,
  onOpen,
  onEdit,
  onDelete,
}: {
  recipe: SavedRecipe;
  onOpen: () => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const [imageBroken, setImageBroken] = useState(false);
  const showFallback = !recipe.imageUrl || imageBroken;
  const platformIcon: keyof typeof Ionicons.glyphMap =
    recipe.sourcePlatform === "youtube"
      ? "logo-youtube"
      : recipe.sourcePlatform === "instagram"
      ? "logo-instagram"
      : "link-outline";
  const courseLabel = recipe.course === "any" ? "Any meal" : capitalise(recipe.course);

  return (
    <View
      style={{
        backgroundColor: colors.surface.card,
        borderRadius: radius.lg,
        padding: spacing.sm,
        gap: spacing.sm,
      }}
    >
      <RipplePressable
        onPress={onOpen}
        haptic="selection"
        accessibilityRole="link"
        accessibilityLabel={`Open ${recipe.title}`}
        style={{
          flexDirection: "row",
          alignItems: "center",
          gap: spacing.md,
        }}
      >
        <View
          style={{
            width: ROW_IMAGE_SIZE,
            height: ROW_IMAGE_SIZE,
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
              }}
            >
              <Ionicons
                name="restaurant"
                size={iconSize.lg}
                color={colors.accent.primary}
              />
            </View>
          ) : (
            <Image
              source={{ uri: recipe.imageUrl! }}
              style={{ width: "100%", height: "100%" }}
              resizeMode="cover"
              onError={() => setImageBroken(true)}
            />
          )}
        </View>

        <View style={{ flex: 1, gap: 2 }}>
          <Text
            style={{ ...typography.bodyBold, color: colors.text.primary }}
            numberOfLines={1}
          >
            {recipe.title}
          </Text>
          <View
            style={{
              flexDirection: "row",
              alignItems: "center",
              gap: 6,
              flexWrap: "wrap",
            }}
          >
            <Ionicons
              name={platformIcon}
              size={iconSize.xs}
              color={colors.text.muted}
            />
            <Text style={{ ...typography.tiny, color: colors.text.muted }}>
              {courseLabel}
              {recipe.totalTimeMins != null ? ` · ${recipe.totalTimeMins} min` : ""}
              {recipe.createdByName ? ` · Saved by ${recipe.createdByName}` : ""}
            </Text>
          </View>
          {recipe.notes ? (
            <Text
              style={{ ...typography.tiny, color: colors.text.secondary }}
              numberOfLines={1}
            >
              {recipe.notes}
            </Text>
          ) : null}
        </View>
      </RipplePressable>

      <View
        style={{
          flexDirection: "row",
          justifyContent: "flex-end",
          gap: spacing.sm,
          paddingTop: spacing.xs,
          borderTopWidth: 1,
          borderTopColor: colors.border.subtle,
        }}
      >
        <RipplePressable
          onPress={onEdit}
          haptic="selection"
          accessibilityRole="button"
          accessibilityLabel="Edit"
          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          style={{
            flexDirection: "row",
            alignItems: "center",
            gap: 4,
            paddingVertical: spacing.xs,
            paddingHorizontal: spacing.sm,
          }}
        >
          <Ionicons
            name="pencil-outline"
            size={iconSize.xs}
            color={colors.text.secondary}
          />
          <Text style={{ ...typography.tinyBold, color: colors.text.secondary }}>
            Edit
          </Text>
        </RipplePressable>
        <RipplePressable
          onPress={onDelete}
          haptic="warning"
          accessibilityRole="button"
          accessibilityLabel="Delete"
          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          style={{
            flexDirection: "row",
            alignItems: "center",
            gap: 4,
            paddingVertical: spacing.xs,
            paddingHorizontal: spacing.sm,
          }}
        >
          <Ionicons
            name="trash-outline"
            size={iconSize.xs}
            color={colors.accent.danger}
          />
          <Text style={{ ...typography.tinyBold, color: colors.accent.danger }}>
            Delete
          </Text>
        </RipplePressable>
      </View>
    </View>
  );
}

function capitalise(s: string): string {
  return s.length === 0 ? s : s[0].toUpperCase() + s.slice(1);
}
