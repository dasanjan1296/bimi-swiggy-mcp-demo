/**
 * HonestPreview — final onboarding screen. Replaces the previous
 * "Tomorrow's dinner: Rajma Chawal!" preview which lied confidently
 * about a kitchen Bimi knows nothing about.
 *
 * The new shape is two stacked sections:
 *
 *   ┌──────────────────────────────────────────┐
 *   │ HERE'S WHAT I'LL DO TONIGHT              │
 *   │ [Photo: Rajma Chawal]                    │
 *   │ Rajma Chawal · for 2                     │
 *   │ Geeta arrives 7:00 PM                    │
 *   │ I'll WhatsApp her brief at 6:15 PM       │
 *   └──────────────────────────────────────────┘
 *
 *   ┌──────────────────────────────────────────┐
 *   │ AND HERE'S WHAT I DON'T KNOW YET         │
 *   │ • What's actually in your kitchen        │
 *   │   I'll ask after dinner tonight.         │
 *   │ • Geeta's actual specialties             │
 *   │   I just texted her — reply by tomorrow. │
 *   │ • Your grocery delivery preference       │
 *   │   I'll ask when something runs low.      │
 *   └──────────────────────────────────────────┘
 *
 * The "what I don't know" block does the work the old preview lied
 * about: it shows the user that Bimi understands the limits of its
 * Day-1 knowledge and has a plan to close each gap. Trust comes from
 * acknowledging the gap, not from pretending it doesn't exist.
 */

import React from "react";
import { View, Text, Image } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, iconSize, radius, spacing, typography } from "@/lib/theme";
import { getDishImage } from "@/lib/dish-images";

export interface PreviewGap {
  /** Short title — "What's actually in your kitchen" */
  title: string;
  /** How Bimi will close the gap — "I'll ask after dinner tonight" */
  plan: string;
  icon: keyof typeof Ionicons.glyphMap;
}

export interface HonestPreviewProps {
  dishSlug: string;
  dishName: string;
  /** Number of portions Bimi will plan for — drives the "for N" line. */
  portions: number;
  /** Cook display name — "Geeta" / "Akka" / etc. */
  cookDisplayName: string | null;
  /** When the cook arrives (e.g. "7:00 PM"). */
  cookArrivalLabel: string | null;
  /** When Bimi will brief the cook (e.g. "6:15 PM"). */
  briefAtLabel: string | null;
  gaps: PreviewGap[];
}

export function HonestPreview({
  dishSlug,
  dishName,
  portions,
  cookDisplayName,
  cookArrivalLabel,
  briefAtLabel,
  gaps,
}: HonestPreviewProps) {
  const img = getDishImage(dishSlug);

  return (
    <View style={{ gap: spacing.xl }}>
      {/* What I'll do tonight */}
      <View
        style={{
          backgroundColor: colors.surface.elevated,
          borderRadius: radius.xl,
          overflow: "hidden",
          borderWidth: 1,
          borderColor: colors.border.subtle,
        }}
      >
        {img ? (
          <Image
            source={img}
            resizeMode="cover"
            style={{ width: "100%", height: 200 }}
            accessible={false}
            accessibilityIgnoresInvertColors
          />
        ) : (
          <View
            style={{
              width: "100%",
              height: 200,
              backgroundColor: colors.surface.card,
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <Ionicons name="restaurant" size={iconSize.xxl} color={colors.text.muted} />
          </View>
        )}

        <View style={{ padding: spacing.lg, gap: spacing.sm }}>
          <Text
            style={{
              ...typography.smallBold,
              textTransform: "uppercase",
              letterSpacing: 1,
              color: colors.accent.primary,
            }}
          >
            Here's what I'd suggest tonight
          </Text>
          <Text style={typography.h2}>{dishName}</Text>
          <Text style={typography.body}>For {portions === 1 ? "1 person" : `${portions} people`}</Text>

          {cookDisplayName && cookArrivalLabel && (
            <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.xs, marginTop: spacing.xs }}>
              <Ionicons name="time-outline" size={iconSize.sm} color={colors.text.secondary} />
              <Text style={typography.caption}>
                {cookDisplayName} arrives at {cookArrivalLabel}
              </Text>
            </View>
          )}
          {briefAtLabel && (
            <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.xs }}>
              <Ionicons name="logo-whatsapp" size={iconSize.sm} color={colors.accent.whatsapp} />
              <Text style={typography.caption}>I'll WhatsApp her brief at {briefAtLabel}</Text>
            </View>
          )}
        </View>
      </View>

      {/* What I don't know yet */}
      <View
        style={{
          backgroundColor: colors.surface.card,
          borderRadius: radius.lg,
          padding: spacing.lg,
          gap: spacing.md,
        }}
      >
        <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.xs }}>
          <Ionicons name="git-network-outline" size={iconSize.sm} color={colors.text.secondary} />
          <Text
            style={{
              ...typography.smallBold,
              textTransform: "uppercase",
              letterSpacing: 1,
              color: colors.text.secondary,
            }}
          >
            And here's what I don't know yet
          </Text>
        </View>

        {gaps.map((g, i) => (
          <View key={i} style={{ flexDirection: "row", gap: spacing.md, alignItems: "flex-start" }}>
            <View
              style={{
                width: 32,
                height: 32,
                borderRadius: 16,
                backgroundColor: colors.surface.elevated,
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <Ionicons name={g.icon} size={iconSize.sm} color={colors.text.secondary} />
            </View>
            <View style={{ flex: 1, gap: 2 }}>
              <Text style={typography.bodyBold}>{g.title}</Text>
              <Text style={typography.small}>{g.plan}</Text>
            </View>
          </View>
        ))}
      </View>
    </View>
  );
}
