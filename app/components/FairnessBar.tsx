import { View, Text } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, cardStyles, spacing, typography, iconSize } from "@/lib/theme";
import { MeterBar } from "./ui";
import type { FairnessScore } from "@/lib/types";

interface FairnessBarProps {
  scores: FairnessScore[];
  compact?: boolean;
  householdType?: string;
}

export function FairnessBar({ scores, compact, householdType }: FairnessBarProps) {
  if (!scores || scores.length === 0) return null;

  const isCouple = householdType === "couple" || scores.length === 2;
  const underserved = scores.find((s) => s.isUnderserved);

  if (isCouple && compact) {
    return (
      <View style={{ ...cardStyles, padding: spacing.md }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.xs }}>
          <Ionicons name="scale" size={iconSize.sm} color={colors.accent.success} />
          <Text style={{ ...typography.bodyBold }}>Meal Balance</Text>
        </View>
        {underserved ? (
          <Text style={{ ...typography.caption, color: colors.accent.secondary, fontWeight: "600", marginTop: spacing.xs }}>
            It's {underserved.memberName}'s turn ({underserved.mealsServed} meals this week)
          </Text>
        ) : (
          <Text style={{ ...typography.caption, color: colors.accent.success, fontWeight: "600", marginTop: spacing.xs }}>
            Balanced — both getting their picks equally
          </Text>
        )}
      </View>
    );
  }

  return (
    <View style={{ ...cardStyles, padding: compact ? spacing.md : spacing.lg }}>
      {!compact && (
        <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.xs, marginBottom: spacing.md }}>
          <Ionicons name="scale" size={iconSize.sm} color={colors.accent.success} />
          <Text style={{ ...typography.bodyBold }}>Fairness This Week</Text>
        </View>
      )}
      <View style={{ gap: compact ? spacing.xs : spacing.sm }}>
        {scores.map((score) => (
          <View key={score.memberId}>
            <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 4, gap: spacing.xs }}>
              <Text
                style={{ ...(compact ? typography.small : typography.bodyBold), flex: 1 }}
                numberOfLines={1}
              >
                {score.memberName}
              </Text>
              <Text style={{ ...typography.small, color: colors.text.secondary, flexShrink: 0 }}>
                {score.mealsServed} meals · {score.avgSatisfaction.toFixed(1)}/5
              </Text>
            </View>
            <MeterBar
              value={score.satisfactionScore}
              tone={score.isUnderserved ? "warning" : "success"}
              size={compact ? "md" : "lg"}
            />
          </View>
        ))}
      </View>
    </View>
  );
}
