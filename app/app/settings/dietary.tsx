import { View, Text, ScrollView, TextInput } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useState, useMemo } from "react";
import { useRouter } from "expo-router";
import { useHouseholdStore } from "@/lib/store";
import { colors, cardStyles, spacing, radius, typography, inputStyles, iconSize } from "@/lib/theme";
import { haptic } from "@/lib/haptics";
import {
  SafeScreen,
  ScreenHeader,
  Button,
  Pill,
  Avatar,
  CalloutCard,
} from "@/components/ui";
import { RipplePressable } from "@/components/RipplePressable";

type PrefType = "allergy" | "intolerance" | "avoidance";

export default function DietaryRoute() {
  const router = useRouter();
  const household = useHouseholdStore((s) => s.household);
  const updateMember = useHouseholdStore((s) => s.updateMember);

  const activeMembers = useMemo(
    () => household?.members.filter((m) => m.isActive) || [],
    [household],
  );

  const [addingPrefFor, setAddingPrefFor] = useState<string | null>(null);
  const [newPrefItem, setNewPrefItem] = useState("");
  const [newPrefType, setNewPrefType] = useState<PrefType>("avoidance");

  const submitPref = (memberId: string, currentPrefs: typeof activeMembers[number]["dietaryPreferences"]) => {
    if (!newPrefItem.trim()) return;
    const safetyClass = newPrefType === "allergy" ? "critical" as const : "flexible" as const;
    const updatedPrefs = [
      ...currentPrefs,
      { item: newPrefItem.trim(), type: newPrefType, safetyClass },
    ];
    updateMember(memberId, { dietaryPreferences: updatedPrefs as any });
    setAddingPrefFor(null);
    setNewPrefItem("");
    haptic("success");
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
          title="Dietary"
          subtitle="Allergies are hard constraints — they block all meals containing the allergen."
        />

        {/* 2026-05-03 audit: the "View what Bimi has learned" link
            pushed to /preferences, which was retired in this PR (per
            redesign §7's settings retirement). Personalised preferences
            now surface inline on Today; the standalone "Bimi's Brain"
            screen is gone. */}

        {activeMembers.map((member) => (
          <View key={member.id} style={{ ...cardStyles, marginBottom: spacing.md }}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, marginBottom: spacing.sm }}>
              <Avatar name={member.name} id={member.id} size="xs" />
              <Text style={{ ...typography.bodyBold, flex: 1 }}>{member.name}</Text>
              <RipplePressable
                onPress={() => {
                  if (addingPrefFor === member.id) {
                    setAddingPrefFor(null);
                  } else {
                    setAddingPrefFor(member.id);
                    setNewPrefItem("");
                    setNewPrefType("avoidance");
                  }
                }}
                hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                accessibilityLabel={`Add restriction for ${member.name}`}
                accessibilityRole="button"
                style={{ minWidth: 36, minHeight: 36, alignItems: "center", justifyContent: "center" }}
              >
                <Ionicons
                  name={addingPrefFor === member.id ? "close-circle" : "add-circle-outline"}
                  size={iconSize.sm}
                  color={colors.accent.primary}
                />
              </RipplePressable>
            </View>

            {member.healthConditions.length > 0 && (
              <View style={{ marginBottom: spacing.sm }}>
                <Text style={{ ...typography.tiny, marginBottom: spacing.xs }}>Health Conditions</Text>
                <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.xs }}>
                  {member.healthConditions.map((cond, i) => (
                    <Pill key={i} tone="warning" size="xs">{cond}</Pill>
                  ))}
                </View>
              </View>
            )}

            {member.dietaryPreferences.length > 0 ? (
              <View style={{ gap: spacing.xs }}>
                {member.dietaryPreferences.map((pref, i) => {
                  const isAllergy = pref.safetyClass === "critical";
                  return (
                    <View
                      key={i}
                      style={{
                        flexDirection: "row",
                        alignItems: "center",
                        gap: spacing.xs,
                        backgroundColor: isAllergy ? colors.accent.dangerDim : colors.accent.warningDim,
                        borderRadius: radius.sm,
                        paddingHorizontal: spacing.sm,
                        paddingVertical: spacing.xs,
                      }}
                    >
                      <Ionicons
                        name={isAllergy ? "alert-circle" : "warning"}
                        size={iconSize.xs}
                        color={isAllergy ? colors.accent.danger : colors.accent.warning}
                      />
                      <Text style={{ ...typography.small, flex: 1 }}>
                        <Text style={{ fontWeight: "600" }}>{pref.item}</Text> — {pref.type}
                        {pref.notes ? ` (${pref.notes})` : ""}
                      </Text>
                    </View>
                  );
                })}
              </View>
            ) : (
              <Text style={{ ...typography.small, fontStyle: "italic", color: colors.text.muted }}>
                No restrictions set
              </Text>
            )}

            {addingPrefFor === member.id && (
              <View
                style={{
                  marginTop: spacing.md,
                  paddingTop: spacing.md,
                  borderTopWidth: 1,
                  borderTopColor: colors.divider.default,
                  gap: spacing.sm,
                }}
              >
                <TextInput
                  value={newPrefItem}
                  onChangeText={setNewPrefItem}
                  placeholder="Item (e.g. Peanuts, Gluten)"
                  placeholderTextColor={colors.text.muted}
                  accessibilityLabel="Dietary item to add"
                  autoCapitalize="words"
                  returnKeyType="done"
                  style={{ ...inputStyles, borderWidth: 1, borderColor: colors.border.subtle }}
                  autoFocus
                />
                <View style={{ flexDirection: "row", gap: spacing.xs }}>
                  {(["allergy", "intolerance", "avoidance"] as PrefType[]).map((t) => (
                    <View key={t} style={{ flex: 1 }}>
                      <Pill
                        tone={t === "allergy" ? "danger" : t === "intolerance" ? "warning" : "primary"}
                        active={newPrefType === t}
                        onPress={() => setNewPrefType(t)}
                        style={{ flex: 1, justifyContent: "center", alignSelf: "stretch" }}
                      >
                        {t.charAt(0).toUpperCase() + t.slice(1)}
                      </Pill>
                    </View>
                  ))}
                </View>
                {newPrefType === "allergy" && (
                  <CalloutCard tone="danger" leadingIcon="alert-circle">
                    Allergies are hard blocks — Bimi will refuse any meal containing this ingredient.
                  </CalloutCard>
                )}
                <View style={{ flexDirection: "row", gap: spacing.sm }}>
                  <View style={{ flex: 1 }}>
                    <Button
                      variant="primary"
                      size="md"
                      fullWidth
                      onPress={() => submitPref(member.id, member.dietaryPreferences)}
                    >
                      Add
                    </Button>
                  </View>
                  <View style={{ flex: 1 }}>
                    <Button
                      variant="secondary"
                      size="md"
                      fullWidth
                      onPress={() => { setAddingPrefFor(null); setNewPrefItem(""); }}
                    >
                      Cancel
                    </Button>
                  </View>
                </View>
              </View>
            )}
          </View>
        ))}
      </ScrollView>
    </SafeScreen>
  );
}
