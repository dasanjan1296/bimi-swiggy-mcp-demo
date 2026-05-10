/**
 * Avatar — colored monogram circle for any household member, cook, or guest.
 *
 * Replaces inline `Ionicons person-circle` patterns and the local `AvatarCircle`
 * in settings.tsx. Uses `colors.persons` palette deterministically from id/name.
 */

import React from "react";
import { View, Text, ViewStyle, Image } from "react-native";
import { colors, fontFamily } from "@/lib/theme";

export type AvatarSize = "xs" | "sm" | "md" | "lg";

export interface AvatarProps {
  /** Display name — also drives initials. */
  name?: string;
  /** Stable id for consistent color across renders. Falls back to name. */
  id?: string;
  /** Optional image URL — when present, replaces monogram. */
  imageUrl?: string;
  size?: AvatarSize;
  /** When true, paints a 2px warm-amber ring (used for "active" state). */
  active?: boolean;
  style?: ViewStyle;
  /** Optional explicit color override; otherwise derived from id/name. */
  color?: string;
}

function dimsFor(size: AvatarSize): { d: number; font: number } {
  switch (size) {
    case "xs": return { d: 24, font: 11 };
    case "sm": return { d: 32, font: 13 };
    case "lg": return { d: 56, font: 22 };
    case "md":
    default:   return { d: 40, font: 16 };
  }
}

function hashCode(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}

function pickColor(seed: string): string {
  const palette = colors.persons;
  return palette[hashCode(seed) % palette.length];
}

function initialsFor(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0]![0]!.toUpperCase();
  return (parts[0]![0]! + parts[parts.length - 1]![0]!).toUpperCase();
}

function AvatarImpl({ name, id, imageUrl, size = "md", active = false, style, color }: AvatarProps) {
  const { d, font } = dimsFor(size);
  const seed = id || name || "?";
  const bg = color ?? pickColor(seed);

  const ring: ViewStyle = active
    ? { borderWidth: 2, borderColor: colors.accent.primary }
    : {};

  const wrapper: ViewStyle = {
    width: d,
    height: d,
    borderRadius: d / 2,
    alignItems: "center",
    justifyContent: "center",
    overflow: "hidden",
    backgroundColor: bg,
    ...ring,
    ...style,
  };

  if (imageUrl) {
    return (
      <View
        style={wrapper}
        accessibilityRole="image"
        accessibilityLabel={name ? `${name} avatar` : undefined}
      >
        <Image
          source={{ uri: imageUrl }}
          style={{ width: d, height: d }}
          // Image's parent View is the labelled element; mark the
          // <Image> itself as decorative so VoiceOver doesn't double-
          // focus it as an unlabelled child.
          accessible={false}
          accessibilityIgnoresInvertColors
        />
      </View>
    );
  }

  return (
    <View style={wrapper} accessibilityRole="image" accessibilityLabel={name ? `${name} avatar` : undefined}>
      <Text style={{ fontSize: font, fontWeight: "700", fontFamily: fontFamily.bold, color: colors.text.inverse }}>
        {initialsFor(name || "?")}
      </Text>
    </View>
  );
}

/** Memoised — Avatars get rendered in lists (member chips, vote progress
 *  rows, settings) where the parent re-renders on unrelated state. */
export const Avatar = React.memo(AvatarImpl);
