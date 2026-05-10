import { useState, useCallback } from "react";
import { View, Text, TextInput } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, spacing, typography, inputStyles, iconSize } from "@/lib/theme";
import { haptic } from "@/lib/haptics";
import { BottomSheet, Button } from "@/components/ui";
import type { MealSuggestion } from "@/lib/types";

interface SuggestDishSheetProps {
  visible: boolean;
  onClose: () => void;
  onSubmit: (suggestion: MealSuggestion) => void;
  suggestedById?: string;
  suggestedByName?: string;
}

type DetectedPlatform = "youtube" | "instagram" | "other" | null;

function detectPlatform(url: string): DetectedPlatform {
  if (!url.trim()) return null;
  const lower = url.toLowerCase();
  if (lower.includes("youtube.com") || lower.includes("youtu.be")) return "youtube";
  if (lower.includes("instagram.com")) return "instagram";
  if (lower.startsWith("http://") || lower.startsWith("https://")) return "other";
  return null;
}

const PLATFORM_META: Record<string, { icon: keyof typeof Ionicons.glyphMap; label: string; color: string }> = {
  youtube: { icon: "logo-youtube", label: "YouTube", color: colors.brand.youtube },
  instagram: { icon: "logo-instagram", label: "Instagram", color: colors.brand.instagram },
  other: { icon: "link-outline", label: "Link", color: colors.accent.info },
};

export function SuggestDishSheet({
  visible,
  onClose,
  onSubmit,
  suggestedById,
  suggestedByName,
}: SuggestDishSheetProps) {
  const [dishName, setDishName] = useState("");
  const [linkUrl, setLinkUrl] = useState("");
  const [noteForCook, setNoteForCook] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const platform = detectPlatform(linkUrl);

  const reset = useCallback(() => {
    setDishName("");
    setLinkUrl("");
    setNoteForCook("");
    setSubmitting(false);
  }, []);

  const handleClose = () => {
    reset();
    onClose();
  };

  const handleSubmit = async () => {
    const name = dishName.trim();
    if (!name) return;

    setSubmitting(true);
    haptic("selection");

    const suggestion: MealSuggestion = {
      id: `custom-${Date.now()}`,
      dishName: name,
      confidence: 0.5,
      fairnessScore: 0.5,
      noveltyBonus: 1.0,
      constraints: [],
      prepTime: "30 min",
      needsAdvancePrep: false,
      ingredients: [],
      missingIngredients: [],
      sourceUrl: linkUrl.trim() || undefined,
      sourcePlatform: platform || undefined,
      suggestedById,
      suggestedByName,
      noteForCook: noteForCook.trim() || undefined,
    };

    onSubmit(suggestion);
    haptic("success");
    reset();
    onClose();
  };

  return (
    <BottomSheet
      visible={visible}
      onClose={handleClose}
      title="Suggest a dish"
      subtitle="Add a custom dish to the voting list."
    >
      {/* @gorhom/bottom-sheet handles keyboard via keyboardBehavior="interactive" — no manual KeyboardAvoidingView wrapper needed. */}
      <View style={{ gap: spacing.lg }}>
          <View style={{ gap: spacing.xs }}>
            <Text style={{ ...typography.smallBold, color: colors.text.secondary }}>
              Dish name
            </Text>
            <TextInput
              value={dishName}
              onChangeText={setDishName}
              placeholder="e.g. Butter Chicken, Pav Bhaji"
              placeholderTextColor={colors.text.muted}
              style={{ ...inputStyles, borderWidth: 1, borderColor: colors.border.subtle }}
              autoFocus
              returnKeyType="next"
            />
          </View>

          <View style={{ gap: spacing.xs }}>
            <Text style={{ ...typography.smallBold, color: colors.text.secondary }}>
              Recipe link <Text style={{ ...typography.tiny, fontWeight: "400" }}>(optional)</Text>
            </Text>
            <TextInput
              value={linkUrl}
              onChangeText={setLinkUrl}
              placeholder="Paste Instagram Reel or YouTube link"
              placeholderTextColor={colors.text.muted}
              style={{ ...inputStyles, borderWidth: 1, borderColor: colors.border.subtle }}
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="url"
              returnKeyType="next"
            />
            {platform && (
              <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.xs, marginTop: 2 }}>
                <Ionicons
                  name={PLATFORM_META[platform]!.icon}
                  size={iconSize.xs}
                  color={PLATFORM_META[platform]!.color}
                />
                <Text style={{ ...typography.tiny, color: PLATFORM_META[platform]!.color }}>
                  {PLATFORM_META[platform]!.label} link detected
                </Text>
              </View>
            )}
          </View>

          <View style={{ gap: spacing.xs }}>
            <Text style={{ ...typography.smallBold, color: colors.text.secondary }}>
              Note for cook <Text style={{ ...typography.tiny, fontWeight: "400" }}>(optional)</Text>
            </Text>
            <TextInput
              value={noteForCook}
              onChangeText={setNoteForCook}
              placeholder="e.g. Make it less spicy"
              placeholderTextColor={colors.text.muted}
              style={{ ...inputStyles, borderWidth: 1, borderColor: colors.border.subtle }}
              returnKeyType="done"
              onSubmitEditing={handleSubmit}
            />
          </View>

          <Button
            variant="primary"
            size="lg"
            fullWidth
            leadingIcon="add-circle"
            disabled={!dishName.trim()}
            loading={submitting}
            onPress={handleSubmit}
          >
            Add to voting
          </Button>
        </View>
    </BottomSheet>
  );
}
