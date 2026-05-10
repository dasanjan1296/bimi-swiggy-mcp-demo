/**
 * MemberReactionsRow — the "❤ Anjan ❤ Mom · Sister" avatar strip on a
 * household-aware dish card (PRD §4.13).
 *
 * The row is the killer feature of Your Kitchen. It turns an abstract
 * "Bimi knows my family" into something the user can see at a glance: who
 * loved this dish, who hasn't tried it, who would rather skip. The
 * sentiment dot on each avatar is the entire UI affordance for "this dish
 * fits us".
 *
 * Up to `maxVisible` avatars render inline; the remainder collapses into a
 * "+N" pill so the row stays single-line on a 2-up grid.
 */

import React from "react";
import { Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";

import {
  colors,
  iconSize,
  radius,
  spacing,
  typography,
} from "@/lib/theme";
import {
  initialsFor,
  sortReactionsForDisplay,
  type MemberReaction,
} from "@/lib/your-kitchen-api";

const SENTIMENT_RING: Record<MemberReaction["sentiment"], string> = {
  love: colors.accent.danger,        // soft red — visceral love
  like: colors.accent.success,       // green — happy
  dislike: colors.text.muted,        // muted grey — actively de-emphasised
  untried: colors.border.subtle,     // hairline — quietly absent
};

const SENTIMENT_BADGE: Record<MemberReaction["sentiment"], { name: keyof typeof Ionicons.glyphMap; color: string } | null> = {
  love: { name: "heart", color: colors.accent.danger },
  like: { name: "happy", color: colors.accent.success },
  dislike: { name: "remove", color: colors.text.muted },
  untried: null,
};

export function MemberReactionsRow({
  reactions,
  maxVisible = 5,
  size = 22,
  testID,
}: {
  reactions: MemberReaction[];
  maxVisible?: number;
  size?: number;
  testID?: string;
}) {
  if (reactions.length === 0) return null;

  const ordered = sortReactionsForDisplay(reactions);
  const visible = ordered.slice(0, maxVisible);
  const overflow = Math.max(0, ordered.length - visible.length);

  // Build a compact accessibility label: "Anjan loves it, Mom likes it,
  // Sister hasn't tried it".
  const a11y = ordered
    .map((r) => {
      switch (r.sentiment) {
        case "love":
          return `${r.name} loves it`;
        case "like":
          return `${r.name} likes it`;
        case "dislike":
          return `${r.name} doesn't like it`;
        case "untried":
          return `${r.name} hasn't tried it`;
      }
    })
    .join(", ");

  return (
    <View
      testID={testID ?? "member-reactions-row"}
      accessibilityRole="text"
      accessibilityLabel={a11y}
      style={{
        flexDirection: "row",
        alignItems: "center",
        gap: 4,
      }}
    >
      {visible.map((r) => (
        <Avatar key={r.person_id} reaction={r} size={size} />
      ))}
      {overflow > 0 ? (
        <View
          style={{
            paddingHorizontal: 6,
            paddingVertical: 2,
            borderRadius: radius.pill,
            backgroundColor: colors.surface.elevated,
          }}
        >
          <Text style={{ ...typography.tiny, color: colors.text.secondary, fontWeight: "600" }}>
            +{overflow}
          </Text>
        </View>
      ) : null}
    </View>
  );
}

function Avatar({ reaction, size }: { reaction: MemberReaction; size: number }) {
  const ring = SENTIMENT_RING[reaction.sentiment];
  const badge = SENTIMENT_BADGE[reaction.sentiment];
  return (
    <View style={{ width: size + 4, height: size + 4 }}>
      <View
        style={{
          width: size,
          height: size,
          borderRadius: size / 2,
          borderWidth: 1.5,
          borderColor: ring,
          backgroundColor: colors.surface.elevated,
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <Text
          style={{
            fontSize: Math.max(9, size * 0.42),
            color: colors.text.primary,
            fontWeight: "700",
          }}
        >
          {initialsFor(reaction.name)}
        </Text>
      </View>
      {badge ? (
        <View
          style={{
            position: "absolute",
            right: -2,
            bottom: -2,
            backgroundColor: colors.surface.base,
            borderRadius: radius.pill,
            padding: 1,
          }}
        >
          <Ionicons name={badge.name} size={Math.max(8, size * 0.42)} color={badge.color} />
        </View>
      ) : null}
    </View>
  );
}
