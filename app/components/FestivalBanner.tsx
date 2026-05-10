import { View, Text, Pressable } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useMemo } from "react";

import { getActiveFestival, getUpcomingFestivals } from "@/lib/festivals";
import { localIsoDate, useToday } from "@/lib/local-day";
import { colors, spacing, radius, typography } from "@/lib/theme";

const OVERRIDE_LABEL: Record<string, string> = {
  pure_veg: "Bimi will suggest pure-veg dishes",
  sattvic: "Bimi will suggest sattvic / no onion-garlic dishes",
  no_onion_garlic: "Bimi will skip onion and garlic in suggestions",
  fasting: "Bimi will surface vrat-friendly meals",
};

/**
 * P3 (PRD 4.1 — festival/seasonal awareness): A slim banner above the meal
 * carousel showing either the in-progress festival OR the next one within
 * 7 days. Tapping it explains how Bimi will adapt suggestions.
 */
export function FestivalBanner({ onPress }: { onPress?: () => void }) {
  // Live local day so the banner refreshes when midnight rolls in
  // (the in-progress festival can end overnight; the "next within 7
  // days" window slides forward each day).
  const today = useToday();
  const todayIso = localIsoDate(today);
  const { active, upcoming } = useMemo(() => {
    return {
      active: getActiveFestival(),
      upcoming: getUpcomingFestivals(7).find((f) => f.date > todayIso),
    };
  }, [todayIso]);

  const fest = active || upcoming;
  if (!fest) return null;

  const isActive = !!active;
  const daysAway = isActive
    ? 0
    : Math.max(0, Math.ceil((new Date(fest.date).getTime() - Date.now()) / 86400000));
  const overrideHint = fest.dietaryOverride ? OVERRIDE_LABEL[fest.dietaryOverride] : null;

  return (
    <Pressable
      onPress={onPress}
      accessibilityLabel={
        isActive
          ? `${fest.name} today. ${overrideHint || fest.description}`
          : `${fest.name} in ${daysAway} day${daysAway === 1 ? "" : "s"}. ${overrideHint || fest.description}`
      }
      style={{
        flexDirection: "row",
        alignItems: "center",
        gap: spacing.sm,
        backgroundColor: isActive ? colors.accent.aiDim : colors.surface.card,
        borderRadius: radius.md,
        paddingHorizontal: spacing.md,
        paddingVertical: spacing.sm,
        marginBottom: spacing.md,
        borderWidth: 1,
        borderColor: isActive ? colors.accent.ai : colors.border.subtle,
      }}
    >
      <Ionicons
        name="sparkles"
        size={16}
        color={isActive ? colors.accent.ai : colors.accent.warning}
      />
      <View style={{ flex: 1 }}>
        <Text
          style={{
            ...typography.captionBold,
            color: isActive ? colors.accent.ai : colors.text.primary,
          }}
        >
          {isActive
            ? `${fest.name} today`
            : `${fest.name} in ${daysAway} day${daysAway === 1 ? "" : "s"}`}
        </Text>
        <Text style={{ ...typography.tiny, color: colors.text.muted, marginTop: 2 }}>
          {overrideHint || fest.description}
        </Text>
      </View>
      <Ionicons name="chevron-forward" size={14} color={colors.text.muted} />
    </Pressable>
  );
}
