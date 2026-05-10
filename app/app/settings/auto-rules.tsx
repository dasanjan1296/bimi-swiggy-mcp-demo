import { View, Text, ScrollView, TextInput } from "react-native";
import { useState } from "react";
import { useOrderStore, useHouseholdStore } from "@/lib/store";
import { AutoRuleCard } from "@/components/AutoRuleCard";
import { EmptyStateGuide } from "@/components/GuidanceTip";
import { colors, cardStyles, spacing, typography, inputStyles } from "@/lib/theme";
import { haptic } from "@/lib/haptics";
import { showAlert } from "@/lib/dialogs";
import { SafeScreen, ScreenHeader, Button, SectionEyebrow } from "@/components/ui";

export default function AutoRulesRoute() {
  const autoRules = useOrderStore((s) => s.autoRules);
  const toggleRule = useOrderStore((s) => s.toggleRule);
  const removeRule = useOrderStore((s) => s.removeRule);
  const addRule = useOrderStore((s) => s.addRule);
  const household = useHouseholdStore((s) => s.household);
  const activeMembers = household?.members.filter((m) => m.isActive) || [];
  const currentUser = activeMembers.find((m) => m.isAdmin) || activeMembers[0];

  const [newRuleAmount, setNewRuleAmount] = useState("500");
  const [newRuleDays, setNewRuleDays] = useState("5");

  const handleAddRule = () => {
    const amount = parseInt(newRuleAmount);
    const days = parseInt(newRuleDays);
    if (isNaN(amount) || isNaN(days) || amount <= 0 || days <= 0) {
      showAlert("Invalid Input", "Enter valid numbers for amount and days.");
      return;
    }
    haptic("success");
    addRule({
      id: `rule-${Date.now()}`,
      maxAmount: amount,
      minDaysSinceLastOrder: days,
      trustedItems: [],
      enabled: true,
      createdBy: currentUser?.name || "You",
    });
    setNewRuleAmount("500");
    setNewRuleDays("5");
  };

  return (
    <SafeScreen edges={["top", "bottom"]} ambientBackdrop>
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ paddingHorizontal: spacing.lg, paddingBottom: 120 }}
        keyboardShouldPersistTaps="handled"
      >
        <ScreenHeader
          back
          title="Auto-rules"
          subtitle="Orders matching these rules are approved automatically."
        />

        {autoRules.length === 0 && (
          <View style={{ marginBottom: spacing.lg }}>
            <EmptyStateGuide
              icon="flash-outline"
              title="No auto-approval rules yet"
              message="Rules let Bimi approve small grocery orders automatically, so you don't have to approve every cart."
              hint="Add your first rule below"
            />
          </View>
        )}

        {autoRules.map((rule) => (
          <AutoRuleCard
            key={rule.id}
            rule={rule}
            onToggle={() => toggleRule(rule.id)}
            onDelete={() => removeRule(rule.id)}
          />
        ))}

        <View style={{ ...cardStyles, marginTop: spacing.md, gap: spacing.md }}>
          <SectionEyebrow>Add new rule</SectionEyebrow>
          <View>
            <Text style={{ ...typography.tiny, marginBottom: spacing.xs }}>Max order amount (₹)</Text>
            <TextInput
              value={newRuleAmount}
              onChangeText={setNewRuleAmount}
              keyboardType="numeric"
              placeholder="e.g. 500"
              placeholderTextColor={colors.text.muted}
              accessibilityLabel="Maximum order amount in rupees"
              returnKeyType="next"
              style={{ ...inputStyles, borderWidth: 1, borderColor: colors.border.subtle }}
            />
          </View>
          <View>
            <Text style={{ ...typography.tiny, marginBottom: spacing.xs }}>Min days since last order</Text>
            <TextInput
              value={newRuleDays}
              onChangeText={setNewRuleDays}
              keyboardType="numeric"
              placeholder="e.g. 7"
              placeholderTextColor={colors.text.muted}
              accessibilityLabel="Minimum days since last order"
              returnKeyType="done"
              style={{ ...inputStyles, borderWidth: 1, borderColor: colors.border.subtle }}
            />
          </View>
          <Button variant="primary" size="md" fullWidth leadingIcon="add-circle" onPress={handleAddRule}>
            Add rule
          </Button>
        </View>
      </ScrollView>
    </SafeScreen>
  );
}
