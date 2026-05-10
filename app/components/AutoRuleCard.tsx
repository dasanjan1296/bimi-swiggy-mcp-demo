import { View, Text, Switch, TouchableOpacity } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, cardStyles, radius } from "@/lib/theme";
import type { AutoApprovalRule } from "@/lib/types";

interface AutoRuleCardProps {
  rule: AutoApprovalRule;
  onToggle: () => void;
  onDelete: () => void;
}

export function AutoRuleCard({ rule, onToggle, onDelete }: AutoRuleCardProps) {
  return (
    <View
      style={{
        ...cardStyles,
        borderColor: rule.enabled ? `rgba(52,211,153,0.25)` : colors.border.subtle,
        marginBottom: 12,
        opacity: rule.enabled ? 1 : 0.6,
      }}
    >
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <Ionicons name="flash" size={18} color={rule.enabled ? colors.accent.success : colors.text.muted} />
          <Text style={{ fontSize: 15, fontWeight: "700", color: colors.text.primary }}>Auto-Approve Rule</Text>
        </View>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <TouchableOpacity
            onPress={onDelete}
            accessibilityRole="button"
            accessibilityLabel="Delete this auto-rule"
            hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}
            style={{ minWidth: 44, minHeight: 44, alignItems: "center", justifyContent: "center" }}
          >
            <Ionicons name="trash-outline" size={18} color={colors.accent.danger} />
          </TouchableOpacity>
          <Switch
            value={rule.enabled}
            onValueChange={onToggle}
            accessibilityLabel={rule.enabled ? "Auto-rule is on" : "Auto-rule is off"}
            trackColor={{ false: colors.surface.elevated, true: `rgba(52,211,153,0.3)` }}
            thumbColor={rule.enabled ? colors.accent.success : colors.text.muted}
          />
        </View>
      </View>

      <View style={{ gap: 8 }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <View style={{ backgroundColor: colors.accent.primaryDim, borderRadius: 6, padding: 6 }}>
            <Ionicons name="cash-outline" size={14} color={colors.accent.primary} />
          </View>
          <Text style={{ fontSize: 13, color: colors.text.primary }}>
            Order under <Text style={{ fontWeight: "700" }}>₹{rule.maxAmount}</Text>
          </Text>
        </View>

        <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
          <View style={{ backgroundColor: colors.accent.primaryDim, borderRadius: 6, padding: 6 }}>
            <Ionicons name="calendar-outline" size={14} color={colors.accent.primary} />
          </View>
          <Text style={{ fontSize: 13, color: colors.text.primary }}>
            At least <Text style={{ fontWeight: "700" }}>{rule.minDaysSinceLastOrder} days</Text> since last order
          </Text>
        </View>

        {rule.trustedItems.length > 0 && (
          <View style={{ flexDirection: "row", alignItems: "flex-start", gap: 8 }}>
            <View style={{ backgroundColor: colors.accent.successDim, borderRadius: 6, padding: 6, marginTop: 2 }}>
              <Ionicons name="shield-checkmark-outline" size={14} color={colors.accent.success} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ fontSize: 13, color: colors.text.primary, marginBottom: 4 }}>Trusted items only</Text>
              <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 4 }}>
                {rule.trustedItems.map((item, i) => (
                  <View key={i} style={{ backgroundColor: colors.accent.successDim, borderRadius: 6, paddingHorizontal: 8, paddingVertical: 3 }}>
                    <Text style={{ fontSize: 11, color: colors.accent.success, fontWeight: "500" }}>{item}</Text>
                  </View>
                ))}
              </View>
            </View>
          </View>
        )}
      </View>

      <Text style={{ fontSize: 11, color: colors.text.muted, marginTop: 10 }}>
        Created by {rule.createdBy}
      </Text>
    </View>
  );
}
