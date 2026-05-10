import { View, Text, ScrollView, TouchableOpacity, TextInput } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useState, useMemo } from "react";
import { useGuestStore, useHouseholdStore, useMealStore } from "@/lib/store";
import { colors, cardStyles, spacing, radius, typography, inputStyles, buttonStyles } from "@/lib/theme";
import { haptic } from "@/lib/haptics";
import { RipplePressable } from "@/components/RipplePressable";
import { GuidanceTip, EmptyStateGuide } from "@/components/GuidanceTip";
import { shareWithCook } from "@/lib/whatsapp-share";
import { showAlert } from "@/lib/dialogs";
import { useFeatureFlags } from "@/lib/feature-flags";
import { localIsoDatePlus, useToday } from "@/lib/local-day";

export default function GuestsScreen() {
  const router = useRouter();
  const profiles = useGuestStore((s) => s.profiles);
  const visits = useGuestStore((s) => s.visits);
  const addProfile = useGuestStore((s) => s.addProfile);
  const addVisit = useGuestStore((s) => s.addVisit);
  const cancelVisit = useGuestStore((s) => s.cancelVisit);
  const totalGuestCount = useGuestStore((s) => s.totalGuestCount);
  const household = useHouseholdStore((s) => s.household);
  // Coordination-only pivot — hide Insta Cook nudges in the guest scaling flow.
  const flags = useFeatureFlags();
  const showInstacookSurfaces = flags.showInstacook;
  const tomorrowsPlans = useMealStore((s) => s.tomorrowsPlans);
  const [showAddForm, setShowAddForm] = useState(false);
  const [guestName, setGuestName] = useState("");
  const [dietaryType, setDietaryType] = useState("");
  const [allergies, setAllergies] = useState("");
  const [guestMealType, setGuestMealType] = useState<"breakfast" | "lunch" | "dinner">("dinner");
  const [headCount, setHeadCount] = useState(1);

  // Local-tomorrow string, reactive to midnight rollover via `useToday()`
  // (so a guest list opened at 11:55 PM Sunday updates to Monday's date
  // when midnight crosses, instead of stranding the user on the wrong
  // date until they manually refresh).
  const today = useToday();
  const tomorrow = useMemo(() => localIsoDatePlus(1, today), [today]);

  const tomorrowGuests = useMemo(() => visits.filter((v) => v.mealDate === tomorrow && v.isActive), [visits, tomorrow]);

  const handleAddGuest = () => {
    if (!guestName.trim()) return;
    haptic("success");
    const existing = profiles.find((p) => p.name.toLowerCase() === guestName.toLowerCase());
    if (!existing) {
      addProfile({
        id: `gp-${Date.now()}`,
        name: guestName,
        dietaryType: dietaryType || undefined,
        allergies: allergies ? allergies.split(",").map((a) => a.trim()) : undefined,
        visitCount: 0,
      });
    }
    addVisit({
      id: `gv-${Date.now()}`,
      guestName,
      mealDate: tomorrow,
      mealType: guestMealType,
      headCount,
      isActive: true,
      dietaryConstraints: dietaryType ? { diet: dietaryType } : undefined,
    });
    const addedName = guestName;
    const addedMeal = guestMealType;
    setGuestName("");
    setDietaryType("");
    setAllergies("");
    setGuestMealType("dinner");
    setHeadCount(1);
    setShowAddForm(false);
    if (household?.hasCook && household.cooks?.[0]) {
      const cook = household.cooks[0];
      showAlert(
        "Guest Added",
        `${addedName} added for tomorrow's ${addedMeal}. Portions will adjust automatically.`,
        [
          { text: "OK", style: "cancel" },
          { text: `Tell ${cook.name}`, onPress: () => shareWithCook(cook.whatsappNumber, `Kal ${addedMeal} mein ${addedName} aa rahe hain. Extra portions chahiye.`) },
        ],
      );
    } else {
      showAlert("Guest Added", `${addedName} (${headCount}) added for tomorrow's ${addedMeal}. Portions and suggestions will adjust automatically.`);
    }
  };

  return (
    // Native Stack header (`Guests`) is registered in `_layout.tsx`; only the
    // body lives here, so safe-area + back button + system gesture come for free.
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.surface.warm }}
      contentContainerStyle={{ padding: spacing.lg, paddingBottom: 40, paddingTop: spacing.md }}
    >
      <Text style={{ ...typography.caption, marginBottom: spacing.lg }}>
        Manage guest visits and dietary needs.
      </Text>

      {tomorrowGuests.length > 0 && (
        <View style={{ ...cardStyles, borderLeftWidth: 4, borderLeftColor: colors.accent.primary, marginBottom: spacing.md }}>
          <Text style={{ ...typography.h3, color: colors.accent.primary, marginBottom: 8 }}>
            Tomorrow: {totalGuestCount(tomorrow)} guest{totalGuestCount(tomorrow) !== 1 ? "s" : ""} expected
          </Text>
          {tomorrowGuests.map((v) => (
            <View key={v.id} style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: 6 }}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                <Ionicons name="person" size={16} color={colors.text.secondary} />
                <Text style={{ ...typography.body, color: colors.text.primary }}>{v.guestName}</Text>
                {v.dietaryConstraints?.diet && (
                  <View style={{ backgroundColor: colors.accent.warningDim, borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2 }}>
                    <Text style={{ fontSize: 10, color: colors.accent.warning }}>{v.dietaryConstraints.diet}</Text>
                  </View>
                )}
              </View>
              <TouchableOpacity
                onPress={() => cancelVisit(v.id)}
                accessibilityRole="button"
                accessibilityLabel={`Cancel ${v.guestName}'s visit`}
                hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}
                style={{ minWidth: 36, minHeight: 36, alignItems: "center", justifyContent: "center" }}
              >
                <Ionicons name="close-circle" size={20} color={colors.accent.danger} />
              </TouchableOpacity>
            </View>
          ))}
        </View>
      )}

      {(() => {
        const memberCount = household?.members.filter((m) => m.isActive).length || 2;
        const guestCount = totalGuestCount(tomorrow);
        const totalPeople = memberCount + guestCount;
        const hasCook = household?.hasCook || false;
        const cookName = household?.cooks?.[0]?.name;
        const tomorrowsPlan = tomorrowsPlans.find(
          (p) => tomorrowGuests.length > 0 && p.mealType === tomorrowGuests[0].mealType && p.selectedMeal
        );
        const tomorrowDay = new Date(tomorrow).getDay();
        const cookSlots = household?.cooks?.[0]?.slots || [];
        const dayNames = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
        const isTomorrowCookOff =
          hasCook &&
          cookSlots.length > 0 &&
          !cookSlots.some((s) => s.workingDays.includes(dayNames[tomorrowDay]));

        // Branch 1: Cook-off + guests
        // With InstaCook on → "Book a cook for X" full booking.
        // With InstaCook off (coordination-only) → simple awareness card so
        // the household can plan ahead.
        if (guestCount >= 1 && isTomorrowCookOff) {
          if (!showInstacookSurfaces) {
            return (
              <View
                style={{
                  ...cardStyles,
                  borderWidth: 1,
                  borderColor: colors.accent.warning,
                  backgroundColor: colors.accent.warningDim,
                  marginBottom: spacing.md,
                }}
              >
                <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.xs, marginBottom: spacing.sm }}>
                  <Ionicons name="sunny" size={14} color={colors.accent.warning} />
                  <Text style={{ ...typography.small, color: colors.accent.warning }}>
                    Cook off tomorrow — plan ahead for guests
                  </Text>
                </View>
                <Text style={{ ...typography.bodyBold, marginBottom: spacing.xs }}>
                  {totalPeople} people for {tomorrowGuests[0]?.mealType || "dinner"}
                </Text>
                <Text style={{ ...typography.small, color: colors.text.muted }}>
                  {cookName || "Your cook"} is off, so cooking for everyone falls on the household. Bimi will help with shopping and the menu.
                </Text>
              </View>
            );
          }
          return (
            <View
              style={{
                ...cardStyles,
                borderWidth: 1,
                borderColor: colors.accent.warning,
                backgroundColor: colors.accent.warningDim,
                marginBottom: spacing.md,
              }}
            >
              <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.xs, marginBottom: spacing.sm }}>
                <Ionicons name="sunny" size={14} color={colors.accent.warning} />
                <Text style={{ ...typography.small, color: colors.accent.warning }}>
                  Cook off tomorrow — you'll need a full InstaCook
                </Text>
              </View>
              <Text style={{ ...typography.bodyBold, marginBottom: spacing.xs }}>
                {totalPeople} people for {tomorrowGuests[0]?.mealType || "dinner"}
              </Text>
              <Text style={{ ...typography.small, color: colors.text.muted, marginBottom: spacing.md }}>
                Since {cookName || "your cook"} is off, Bimi can send a cook who'll make the whole meal for everyone.
              </Text>
                {/* 2026-05-03 audit: the previous "Book a cook for X"
                    CTA pushed to the deleted /instacook screen. Insta
                    Cook is permanently retired (founder call) — the card
                    is now awareness-only, no booking action. */}
            </View>
          );
        }

        // Branch 2: Moderate guest count + cook present → sous cook offer
        // (InstaCook surface — hidden during the coordination-only pivot.)
        if (showInstacookSurfaces && guestCount >= 1 && totalPeople > memberCount + 1 && hasCook && cookName) {
          const extendedFamilyGuests = tomorrowGuests.filter(
            (g) => g.guestType === "extended_family"
          ).length;
          const nudgeCopy =
            extendedFamilyGuests > 0
              ? `Family visiting? ${cookName} makes ${tomorrowsPlan?.selectedMeal || "the main course"}; a sous cook adds a starter and side.`
              : `${cookName} usually cooks for ${memberCount}. A sous cook handles the extra portions${tomorrowsPlan ? ` + a starter to go with ${tomorrowsPlan.selectedMeal}` : ""}.`;
          return (
            <View style={{
              ...cardStyles,
              borderWidth: 1,
              borderColor: colors.accent.primaryDim,
              marginBottom: spacing.md,
            }}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.xs, marginBottom: spacing.sm }}>
                <Ionicons name="restaurant" size={14} color={colors.accent.primary} />
                <Text style={{ ...typography.small, color: colors.accent.primary }}>Scaling help</Text>
              </View>
              <Text style={{ ...typography.bodyBold, marginBottom: spacing.xs }}>
                {totalPeople} people for {tomorrowGuests[0]?.mealType || "dinner"}
              </Text>
              <Text style={{ ...typography.small, color: colors.text.muted, marginBottom: spacing.md }}>
                {nudgeCopy}
              </Text>
              <View style={{ flexDirection: "row", gap: spacing.sm }}>
                {/* 2026-05-03 audit: "Add a sous cook" CTA pushed to
                    the deleted /instacook-assist screen — gone. */}
                <RipplePressable
                  onPress={() => haptic("selection")}
                  haptic="light"
                  style={{ flex: 1, borderRadius: radius.md }}
                >
                  <View style={{
                    backgroundColor: colors.surface.card,
                    borderRadius: radius.md,
                    paddingVertical: 10,
                    alignItems: "center",
                    borderWidth: 1,
                    borderColor: colors.border.subtle,
                  }}>
                    <Text style={{ ...typography.captionBold, color: colors.text.secondary }}>We'll manage</Text>
                  </View>
                </RipplePressable>
              </View>
            </View>
          );
        }
        return null;
      })()}

      <GuidanceTip
        variant="hint"
        icon={"people" as const}
        message="When you add guests, I'll auto-scale portions, suggest guest-worthy dishes, and remember their preferences for next time."
        compact
      />

      {showAddForm ? (
        <View style={{ ...cardStyles, marginTop: spacing.md }}>
          <Text style={{ ...typography.h3, color: colors.text.primary, marginBottom: spacing.sm }}>Add Guest for Tomorrow</Text>
          <TextInput
            style={{ ...inputStyles, marginBottom: spacing.sm }}
            placeholder="Guest name"
            placeholderTextColor={colors.text.muted}
            value={guestName}
            onChangeText={setGuestName}
            accessibilityLabel="Guest name"
            autoCapitalize="words"
            autoComplete="name"
            textContentType="name"
            returnKeyType="next"
          />
          <TextInput
            style={{ ...inputStyles, marginBottom: spacing.sm }}
            placeholder="Dietary type (veg, non-veg, vegan)"
            placeholderTextColor={colors.text.muted}
            value={dietaryType}
            onChangeText={setDietaryType}
            accessibilityLabel="Dietary type"
            autoCapitalize="none"
            returnKeyType="next"
          />
          <TextInput
            style={{ ...inputStyles, marginBottom: spacing.md }}
            placeholder="Allergies (comma-separated)"
            placeholderTextColor={colors.text.muted}
            value={allergies}
            onChangeText={setAllergies}
            accessibilityLabel="Allergies (comma-separated)"
            autoCapitalize="words"
            returnKeyType="done"
          />

          {/* Meal type selector */}
          <Text style={{ ...typography.captionBold, color: colors.text.secondary, marginBottom: 6 }}>Meal</Text>
          <View style={{ flexDirection: "row", gap: spacing.sm, marginBottom: spacing.md }}>
            {(["breakfast", "lunch", "dinner"] as const).map((m) => (
              <TouchableOpacity
                key={m}
                onPress={() => setGuestMealType(m)}
                style={{
                  flex: 1,
                  paddingVertical: 8,
                  borderRadius: 8,
                  alignItems: "center",
                  backgroundColor: guestMealType === m ? colors.accent.primary : colors.surface.elevated,
                  borderWidth: 1,
                  borderColor: guestMealType === m ? colors.accent.primary : colors.border.subtle,
                }}
              >
                <Text style={{ fontSize: 13, fontWeight: guestMealType === m ? "700" : "500", color: guestMealType === m ? colors.text.inverse : colors.text.secondary }}>
                  {m.charAt(0).toUpperCase() + m.slice(1)}
                </Text>
              </TouchableOpacity>
            ))}
          </View>

          {/* Headcount stepper */}
          <Text style={{ ...typography.captionBold, color: colors.text.secondary, marginBottom: 6 }}>Headcount</Text>
          <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md, marginBottom: spacing.md }}>
            <TouchableOpacity
              onPress={() => setHeadCount(Math.max(1, headCount - 1))}
              style={{ width: 36, height: 36, borderRadius: 8, backgroundColor: colors.surface.elevated, borderWidth: 1, borderColor: colors.border.subtle, alignItems: "center", justifyContent: "center" }}
            >
              <Ionicons name="remove" size={18} color={colors.text.secondary} />
            </TouchableOpacity>
            <Text style={{ ...typography.h3, minWidth: 24, textAlign: "center" }}>{headCount}</Text>
            <TouchableOpacity
              onPress={() => setHeadCount(Math.min(20, headCount + 1))}
              style={{ width: 36, height: 36, borderRadius: 8, backgroundColor: colors.accent.primaryDim, borderWidth: 1, borderColor: colors.border.active, alignItems: "center", justifyContent: "center" }}
            >
              <Ionicons name="add" size={18} color={colors.accent.primary} />
            </TouchableOpacity>
          </View>

          <View style={{ flexDirection: "row", gap: spacing.sm }}>
            <TouchableOpacity
              onPress={handleAddGuest}
              style={{ ...buttonStyles.primary, flex: 1, alignItems: "center", paddingVertical: 12 }}
            >
              <Text style={{ fontSize: 14, fontWeight: "700", color: colors.text.inverse }}>Add Guest</Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={() => setShowAddForm(false)}
              style={{ ...buttonStyles.secondary, flex: 1, alignItems: "center", paddingVertical: 12 }}
            >
              <Text style={{ fontSize: 14, fontWeight: "600", color: colors.text.secondary }}>Cancel</Text>
            </TouchableOpacity>
          </View>

          {profiles.length > 0 && (
            <View style={{ marginTop: spacing.md }}>
              <Text style={{ ...typography.caption, color: colors.text.secondary, marginBottom: 6 }}>Quick add from previous guests:</Text>
              <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6 }}>
                {profiles.map((p) => (
                  <TouchableOpacity
                    key={p.id}
                    onPress={() => { setGuestName(p.name); setDietaryType(p.dietaryType || ""); setAllergies(p.allergies?.join(", ") || ""); }}
                    style={{ backgroundColor: colors.surface.elevated, borderRadius: 16, paddingHorizontal: 12, paddingVertical: 6 }}
                  >
                    <Text style={{ fontSize: 12, color: colors.text.primary }}>{p.name}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
          )}
        </View>
      ) : (
        <TouchableOpacity
          onPress={() => setShowAddForm(true)}
          style={{ ...buttonStyles.primary, marginTop: spacing.md, alignItems: "center", paddingVertical: 14, flexDirection: "row", justifyContent: "center", gap: 8, borderRadius: 12 }}
        >
          <Ionicons name="person-add" size={18} color={colors.text.inverse} />
          <Text style={{ fontSize: 15, fontWeight: "700", color: colors.text.inverse }}>Add Guests for Tomorrow</Text>
        </TouchableOpacity>
      )}

      {profiles.length > 0 && (
        <View style={{ marginTop: spacing.xl }}>
          <Text style={{ ...typography.h2, marginBottom: spacing.sm }}>Known Guests</Text>
          {profiles.map((p) => (
            <View key={p.id} style={{ ...cardStyles, marginBottom: spacing.sm }}>
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                <View>
                  <Text style={{ ...typography.h3, color: colors.text.primary }}>{p.name}</Text>
                  <View style={{ flexDirection: "row", gap: 8, marginTop: 4 }}>
                    {p.dietaryType && (
                      <Text style={{ fontSize: 11, color: colors.accent.warning }}>{p.dietaryType}</Text>
                    )}
                    {p.allergies?.map((a) => (
                      <View key={a} style={{ backgroundColor: colors.accent.dangerDim, borderRadius: 4, paddingHorizontal: 6, paddingVertical: 1 }}>
                        <Text style={{ fontSize: 10, color: colors.accent.danger }}>{a}</Text>
                      </View>
                    ))}
                  </View>
                </View>
                <View style={{ alignItems: "flex-end" }}>
                  <Text style={{ ...typography.small, color: colors.text.secondary }}>{p.visitCount} visit{p.visitCount !== 1 ? "s" : ""}</Text>
                  {p.lastVisit && <Text style={{ ...typography.small, color: colors.text.muted }}>Last: {p.lastVisit}</Text>}
                </View>
              </View>
            </View>
          ))}
        </View>
      )}
    </ScrollView>
  );
}
