/**
 * AddRecipeSheet — paste-URL bottom sheet for the household-curated
 * saved-recipes catalog. Used by:
 *   • Home SelfCookSheet's "+ Add" header pill (quick add)
 *   • Settings → Saved recipes management screen (add + edit)
 *
 * Two modes via prop:
 *   • create  → user pastes a URL; YouTube auto-fills title/image via
 *                server oEmbed; Instagram & web require user title.
 *   • edit    → URL field is locked (changing the source would
 *                effectively be a different recipe); user can adjust
 *                title / course / time / notes / tags.
 *
 * Server-side validation is the source of truth — the FE flag for
 * "Instagram requires manual title" is just a UX hint to surface the
 * field; the server still enforces 422 if title is missing.
 */

import React, { useCallback, useEffect, useState } from "react";
import { Image, Text, TextInput, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { BottomSheet } from "../ui/BottomSheet";
import { Button } from "../ui/Button";
import { RipplePressable } from "../RipplePressable";
import { toast } from "@/lib/toast";
import {
  colors,
  iconSize,
  inputStyles,
  radius,
  spacing,
  typography,
} from "@/lib/theme";
import {
  detectRecipePlatform,
  extractYouTubeId,
  useCreateSavedRecipe,
  usePatchSavedRecipe,
  type SavedRecipe,
  type SavedRecipeCourse,
  type SavedRecipeSourcePlatform,
} from "@/lib/use-saved-recipes";

type Mode =
  | { kind: "create"; familyId: string; createdByName?: string | null }
  | { kind: "edit"; recipe: SavedRecipe };

export interface AddRecipeSheetProps {
  visible: boolean;
  onClose: () => void;
  mode: Mode;
}

const COURSE_OPTIONS: { value: SavedRecipeCourse; label: string }[] = [
  { value: "any", label: "Any" },
  { value: "breakfast", label: "Breakfast" },
  { value: "lunch", label: "Lunch" },
  { value: "dinner", label: "Dinner" },
  { value: "snack", label: "Snack" },
];

const PLATFORM_META: Record<
  SavedRecipeSourcePlatform,
  { icon: keyof typeof Ionicons.glyphMap; label: string; color: string }
> = {
  youtube: { icon: "logo-youtube", label: "YouTube", color: colors.brand.youtube },
  instagram: { icon: "logo-instagram", label: "Instagram", color: colors.brand.instagram },
  web: { icon: "link-outline", label: "Link", color: colors.accent.info },
};

export function AddRecipeSheet({ visible, onClose, mode }: AddRecipeSheetProps) {
  const create = useCreateSavedRecipe();
  const patch = usePatchSavedRecipe();

  // ── Form state ──
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [imageUrl, setImageUrl] = useState("");
  const [course, setCourse] = useState<SavedRecipeCourse>("any");
  const [timeStr, setTimeStr] = useState("");
  const [notes, setNotes] = useState("");

  // Reset on open. For edit mode, seed from the existing recipe so
  // the user sees a pre-filled form they can tweak.
  useEffect(() => {
    if (!visible) return;
    if (mode.kind === "edit") {
      const r = mode.recipe;
      setUrl(r.sourceUrl);
      setTitle(r.title);
      setImageUrl(r.imageUrl ?? "");
      setCourse(r.course);
      setTimeStr(r.totalTimeMins != null ? String(r.totalTimeMins) : "");
      setNotes(r.notes ?? "");
    } else {
      setUrl("");
      setTitle("");
      setImageUrl("");
      setCourse("any");
      setTimeStr("");
      setNotes("");
    }
  }, [visible, mode]);

  const platform = url.trim().length > 0 ? detectRecipePlatform(url) : null;
  const platformMeta = platform ? PLATFORM_META[platform] : null;

  // For YouTube the server's oEmbed call will hydrate the title if
  // we don't pass one. For IG/web the server will 422 without a
  // title — surface that requirement in the UI.
  const titleRequired = platform != null && platform !== "youtube";

  // Local YouTube preview: if we can extract the video ID, show the
  // hqdefault thumbnail so the user has something to confirm before
  // hitting save (instant feedback, no round-trip).
  const ytId = platform === "youtube" ? extractYouTubeId(url) : null;
  const previewImage =
    imageUrl.trim() || (ytId ? `https://img.youtube.com/vi/${ytId}/hqdefault.jpg` : null);

  // ── Validation ──
  const trimmedUrl = url.trim();
  const trimmedTitle = title.trim();
  const isValidUrl = trimmedUrl.length > 0 && /^https?:\/\//i.test(trimmedUrl);
  const isFormValid =
    isValidUrl && (!titleRequired || trimmedTitle.length > 0);

  const submitting = create.isPending || patch.isPending;

  const handleSubmit = useCallback(async () => {
    if (!isFormValid || submitting) return;

    const totalTimeMins =
      timeStr.trim().length > 0 && /^\d+$/.test(timeStr.trim())
        ? parseInt(timeStr.trim(), 10)
        : null;

    try {
      if (mode.kind === "edit") {
        await patch.mutateAsync({
          id: mode.recipe.id,
          familyId: mode.recipe.familyId,
          title: trimmedTitle.length > 0 ? trimmedTitle : null,
          imageUrl: imageUrl.trim() || null,
          course,
          totalTimeMins,
          notes: notes.trim() || null,
        });
        toast.success("Recipe updated");
      } else {
        await create.mutateAsync({
          familyId: mode.familyId,
          createdByName: mode.createdByName ?? null,
          sourceUrl: trimmedUrl,
          title: trimmedTitle.length > 0 ? trimmedTitle : null,
          imageUrl: imageUrl.trim() || null,
          course,
          totalTimeMins,
          notes: notes.trim() || null,
        });
        toast.success(
          "Saved",
          "It'll appear in your recipe ideas.",
        );
      }
      onClose();
    } catch (err) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "Couldn't save. Try again.";
      toast.error("Couldn't save", message);
    }
  }, [
    isFormValid,
    submitting,
    timeStr,
    mode,
    patch,
    create,
    trimmedTitle,
    trimmedUrl,
    imageUrl,
    course,
    notes,
    onClose,
  ]);

  const sheetTitle = mode.kind === "edit" ? "Edit recipe" : "Save a recipe";
  const sheetSubtitle =
    mode.kind === "edit"
      ? "Tweak details below."
      : "Paste a YouTube or Instagram link.";

  return (
    <BottomSheet
      visible={visible}
      onClose={onClose}
      title={sheetTitle}
      subtitle={sheetSubtitle}
      maxHeightFraction={0.92}
      scrollable
    >
      <View style={{ paddingTop: spacing.md, paddingBottom: spacing.xl, gap: spacing.lg }}>
        {/* URL field — locked in edit mode (changing the URL would be
            a new recipe, not an edit). */}
        <FieldGroup label="URL" required>
          <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
            <TextInput
              style={[inputStyles, { flex: 1, opacity: mode.kind === "edit" ? 0.6 : 1 }]}
              value={url}
              onChangeText={setUrl}
              placeholder="https://www.youtube.com/watch?v=…"
              placeholderTextColor={colors.text.muted}
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="url"
              editable={mode.kind === "create"}
            />
            {platformMeta ? (
              <View
                style={{
                  flexDirection: "row",
                  alignItems: "center",
                  gap: 4,
                  paddingHorizontal: spacing.sm,
                  paddingVertical: spacing.xs,
                  borderRadius: radius.sm,
                  backgroundColor: colors.surface.card,
                }}
              >
                <Ionicons
                  name={platformMeta.icon}
                  size={iconSize.sm}
                  color={platformMeta.color}
                />
                <Text style={{ ...typography.smallBold, color: colors.text.secondary }}>
                  {platformMeta.label}
                </Text>
              </View>
            ) : null}
          </View>
        </FieldGroup>

        {/* Live preview if we can build a thumbnail URL right now. */}
        {previewImage ? (
          <View
            style={{
              borderRadius: radius.md,
              overflow: "hidden",
              backgroundColor: colors.surface.card,
              aspectRatio: 16 / 9,
            }}
          >
            <PreviewImage uri={previewImage} />
          </View>
        ) : null}

        {/* Title — required for IG/web, optional for YouTube (oEmbed). */}
        <FieldGroup
          label="Title"
          required={titleRequired}
          hint={
            !titleRequired && platform === "youtube"
              ? "We'll fetch this from YouTube if you leave it blank."
              : undefined
          }
        >
          <TextInput
            style={inputStyles}
            value={title}
            onChangeText={setTitle}
            placeholder={
              platform === "youtube" ? "Maggi Masala" : "What's this recipe called?"
            }
            placeholderTextColor={colors.text.muted}
            maxLength={120}
          />
        </FieldGroup>

        {/* Course picker — pill row. */}
        <FieldGroup label="Best for">
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.xs }}>
            {COURSE_OPTIONS.map((opt) => {
              const isActive = course === opt.value;
              return (
                <RipplePressable
                  key={opt.value}
                  onPress={() => setCourse(opt.value)}
                  haptic="selection"
                  accessibilityRole="button"
                  accessibilityState={{ selected: isActive }}
                  style={{
                    paddingHorizontal: spacing.md,
                    paddingVertical: spacing.xs + 2,
                    borderRadius: radius.pill,
                    backgroundColor: isActive
                      ? colors.accent.primary
                      : colors.surface.card,
                  }}
                >
                  <Text
                    style={{
                      ...typography.smallBold,
                      color: isActive ? colors.text.inverse : colors.text.primary,
                    }}
                  >
                    {opt.label}
                  </Text>
                </RipplePressable>
              );
            })}
          </View>
        </FieldGroup>

        {/* Optional total time. */}
        <FieldGroup label="Total time" hint="Minutes — optional.">
          <TextInput
            style={[inputStyles, { width: 120 }]}
            value={timeStr}
            onChangeText={(t) => setTimeStr(t.replace(/[^\d]/g, "").slice(0, 3))}
            placeholder="15"
            placeholderTextColor={colors.text.muted}
            keyboardType="number-pad"
            maxLength={3}
          />
        </FieldGroup>

        {/* Optional household notes. */}
        <FieldGroup label="Notes" hint="Optional. e.g. 'Mayank's favourite'.">
          <TextInput
            style={[inputStyles, { minHeight: 72, textAlignVertical: "top" }]}
            value={notes}
            onChangeText={setNotes}
            placeholder="Anything to remember?"
            placeholderTextColor={colors.text.muted}
            multiline
            maxLength={400}
          />
        </FieldGroup>

        <View style={{ paddingHorizontal: spacing.md, marginTop: spacing.sm }}>
          <Button
            variant="primary"
            size="md"
            onPress={handleSubmit}
            disabled={!isFormValid || submitting}
            loading={submitting}
            fullWidth
          >
            {mode.kind === "edit" ? "Save changes" : "Save recipe"}
          </Button>
        </View>
      </View>
    </BottomSheet>
  );
}

// ── Sub-components ───────────────────────────────────────────────────

function FieldGroup({
  label,
  required,
  hint,
  children,
}: {
  label: string;
  required?: boolean;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <View style={{ paddingHorizontal: spacing.md, gap: spacing.xs }}>
      <Text
        style={{
          ...typography.tinyBold,
          color: colors.text.muted,
          textTransform: "uppercase",
          letterSpacing: 0.6,
        }}
      >
        {label}
        {required ? <Text style={{ color: colors.accent.warning }}> *</Text> : null}
      </Text>
      {children}
      {hint ? (
        <Text style={{ ...typography.tiny, color: colors.text.muted }}>
          {hint}
        </Text>
      ) : null}
    </View>
  );
}

function PreviewImage({ uri }: { uri: string }) {
  // Local image-error state so a broken link gracefully falls back to
  // a placeholder instead of leaving an empty box.
  const [broken, setBroken] = useState(false);
  if (broken) {
    return (
      <View
        style={{
          flex: 1,
          alignItems: "center",
          justifyContent: "center",
          backgroundColor: colors.accent.primaryDim,
        }}
      >
        <Ionicons name="image-outline" size={iconSize.xl} color={colors.accent.primary} />
      </View>
    );
  }
  return (
    <Image
      source={{ uri }}
      style={{ width: "100%", height: "100%" }}
      resizeMode="cover"
      onError={() => setBroken(true)}
    />
  );
}
