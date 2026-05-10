import React from "react";
import { View, Text, TouchableOpacity } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, spacing } from "@/lib/theme";
import type { HouseholdMember, MealVote } from "@/lib/types";

interface VoteProgressProps {
  members: HouseholdMember[];
  votes: MealVote[];
  proxyVotes?: MealVote[];
  /** Active member's id; suppresses the self-nudge button. */
  currentUserId?: string;
  onNudge?: (memberId: string) => void;
}

function VoteProgressImpl({ members, votes, proxyVotes = [], currentUserId, onNudge }: VoteProgressProps) {
  const activeMembers = members.filter((m) => m.isActive && m.isAvailable);

  const skipByMember = new Map<string, boolean>();
  const bestVoteByMember = new Map<string, MealVote>();
  for (const v of votes) {
    if (v.skipped) { skipByMember.set(v.memberId, true); continue; }
    const existing = bestVoteByMember.get(v.memberId);
    if (!existing || v.rating > existing.rating) bestVoteByMember.set(v.memberId, v);
  }
  const proxyByMember = new Map(proxyVotes.map((v) => [v.memberId, v]));

  return (
    <View style={{ gap: spacing.sm }}>
      {activeMembers.map((member) => {
        const isSkipping = skipByMember.get(member.id);
        const vote = bestVoteByMember.get(member.id);
        const proxy = proxyByMember.get(member.id);
        const pick = vote || proxy;
        const isPending = !pick && !isSkipping;

        // P3: ghost avatar + dotted border + confidence chip when we have a
        // proxy vote (PRD 4.5 visual treatment). Real votes still get the
        // solid avatar and rating-style treatment.
        const showProxy = !isSkipping && !vote && !!proxy;
        const confidence =
          proxy?.proxyConfidence !== undefined
            ? Math.round((proxy.proxyConfidence as number) * 100)
            : null;

        return (
          <View
            key={member.id}
            style={{
              flexDirection: "row",
              alignItems: "center",
              gap: spacing.sm,
              opacity: isPending || isSkipping ? 0.55 : 1,
            }}
          >
            <View
              style={{
                width: 24,
                height: 24,
                borderRadius: 12,
                borderWidth: showProxy ? 1.5 : 0,
                borderStyle: showProxy ? "dashed" : "solid",
                borderColor: colors.accent.ai,
                alignItems: "center",
                justifyContent: "center",
                opacity: showProxy ? 0.85 : 1,
              }}
            >
              <Ionicons
                name={showProxy ? "person-circle-outline" : "person-circle"}
                size={20}
                color={
                  showProxy
                    ? colors.accent.ai
                    : isSkipping
                      ? colors.accent.warning
                      : colors.text.secondary
                }
              />
            </View>
            <Text style={{ fontSize: 13, fontWeight: "600", color: colors.text.primary, width: 72 }}>
              {member.name}
            </Text>
            {isSkipping && (
              <Text style={{ fontSize: 13, color: colors.accent.warning, fontStyle: "italic", flex: 1 }}>
                Skipping
              </Text>
            )}
            {!isSkipping && vote && (
              <Text style={{ fontSize: 13, color: colors.text.secondary, flex: 1 }} numberOfLines={1}>
                {vote.dishName}
              </Text>
            )}
            {showProxy && (
              <View style={{ flex: 1, flexDirection: "row", alignItems: "center", gap: 6 }}>
                <Text
                  style={{ fontSize: 13, color: colors.accent.ai, flexShrink: 1 }}
                  numberOfLines={1}
                >
                  {proxy!.dishName}
                </Text>
                {confidence !== null && (
                  <View
                    style={{
                      backgroundColor: colors.accent.aiDim,
                      borderRadius: 8,
                      paddingHorizontal: 6,
                      paddingVertical: 1,
                    }}
                    accessibilityLabel={`Predicted by Bimi, ${confidence}% confidence`}
                  >
                    <Text style={{ fontSize: 10, fontWeight: "700", color: colors.accent.ai }}>
                      {confidence}% by Bimi
                    </Text>
                  </View>
                )}
              </View>
            )}
            {isPending && (
              <Text style={{ fontSize: 13, color: colors.text.muted, flex: 1 }}>
                hasn't picked yet
              </Text>
            )}
            {isPending && !proxy && onNudge && member.id !== currentUserId && (
              <TouchableOpacity
                onPress={() => onNudge(member.id)}
                accessibilityLabel={`Nudge ${member.name} to vote`}
                hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                style={{ flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 12, backgroundColor: colors.surface.elevated }}
              >
                <Ionicons name="notifications-outline" size={12} color={colors.accent.primary} />
                <Text style={{ fontSize: 11, fontWeight: "600", color: colors.accent.primary }}>Nudge</Text>
              </TouchableOpacity>
            )}
          </View>
        );
      })}
    </View>
  );
}

/** Memoised — voting tab parent re-renders every second during the
 *  soft-lock countdown; without memo this whole row list re-rendered. */
export const VoteProgress = React.memo(VoteProgressImpl);
