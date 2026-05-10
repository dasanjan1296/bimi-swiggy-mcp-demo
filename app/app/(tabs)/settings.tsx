import { View, Text, ScrollView, Switch, TextInput, Linking, Share } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useState, useMemo } from "react";
import { useRouter } from "expo-router";
import {
  useHouseholdStore,
  useExpenseStore,
  useCookAbsenceStore,
} from "@/lib/store";
import { useAuthStore } from "@/lib/auth-store";
import { isRealAuth } from "@/lib/auth-flags";
import { usePostCookAbsence } from "@/lib/api";
import { useNotificationStore } from "@/lib/notifications";
import { getHouseholdTypeLabel, getRoleLabel } from "@/lib/household-copy";
import { GuidanceTip } from "@/components/GuidanceTip";
import { RipplePressable } from "@/components/RipplePressable";
import {
  colors,
  cardStyles,
  listRowStyles,
  spacing,
  radius,
  typography,
  inputStyles,
  iconSize,
  tintedBg,
} from "@/lib/theme";
import { haptic } from "@/lib/haptics";
import { useTabScrollToTop } from "@/lib/hooks/useTabScrollToTop";
import { showAlert, showConfirm } from "@/lib/dialogs";
import {
  SafeScreen,
  Button,
  Pill,
  Avatar,
  IconBadge,
  SettingsRow,
  CalloutCard,
} from "@/components/ui";
import { WhatsAppButton } from "@/components/patterns";

async function copyToClipboard(text: string) {
  try {
    const ExpoClipboard = require("expo-clipboard");
    await ExpoClipboard.setStringAsync(text);
  } catch {
    const { Share } = require("react-native");
    await Share.share({ message: text });
  }
}

export default function SettingsHubScreen() {
  const router = useRouter();
  const household = useHouseholdStore((s) => s.household);
  const {
    removeMember,
    leaveHousehold,
    transferAdmin,
    generateInviteCode,
    setMemberAvailability,
  } = useHouseholdStore();
  const expenseSummary = useExpenseStore((s) => s.summary);
  const addNotification = useNotificationStore((s) => s.addNotification);
  const logout = useAuthStore((s) => s.logout);
  const addAbsence = useCookAbsenceStore((s) => s.addAbsence);
  const swapAbsenceId = useCookAbsenceStore((s) => s.swapAbsenceId);
  const familyId = useAuthStore((s) => s.familyId) ?? "";
  const postAbsence = usePostCookAbsence(familyId);

  const [householdAway, setHouseholdAway] = useState(false);
  const [awayFrom, setAwayFrom] = useState("");
  const [awayTo, setAwayTo] = useState("");

  const activeMembers = useMemo(
    () => household?.members.filter((m) => m.isActive) || [],
    [household],
  );
  const currentUser = activeMembers.find((m) => m.isAdmin) || activeMembers[0];
  const primaryCook = household?.cooks?.[0];

  const unsettledAmount = useMemo(() => {
    const mySettlements = expenseSummary.settlements.filter(
      (s) => !s.settled && s.fromMemberId === currentUser?.id,
    );
    return mySettlements.reduce((sum, s) => sum + s.amount, 0);
  }, [expenseSummary, currentUser]);

  const handleRemoveMember = (memberId: string, memberName: string) => {
    showConfirm(
      "Remove member",
      `Remove ${memberName} from ${household?.name}? Their preferences will be preserved.`,
      {
        confirmText: "Remove",
        destructive: true,
        onConfirm: () => {
          removeMember(memberId);
          addNotification({
            type: "member_removed",
            title: `${memberName} removed`,
            body: `${memberName} has been removed from ${household?.name}.`,
          });
        },
      },
    );
  };

  // P3 (PRD 4.7): Member lifecycle — debt-settlement gate, admin auto-handoff,
  // couple-breakup → archive routing.
  const performLeave = () => {
    if (!currentUser || !household) return;
    const wasCouple = household.type === "couple";
    leaveHousehold(currentUser.id);
    addNotification({
      type: "member_left",
      title: "You left",
      body: `You left ${household.name}.`,
    });
    if (wasCouple) {
      // Couple breakup: archive the household so the surface goes empty
      // and the remaining partner sees create/join CTAs on next login.
      useHouseholdStore.getState().archiveHousehold();
    }
    logout();
    router.replace("/login");
  };

  const handleLeave = () => {
    if (!currentUser || !household) return;
    const isCouple = household.type === "couple";
    const baseMsg = isCouple
      ? `Leaving ${household.name} archives this household. Your partner will need to create a new one or invite you back.`
      : `Leave ${household.name}? Your preferences and vote history will be preserved for the remaining members.`;

    if (unsettledAmount > 0) {
      showAlert(
        `You owe ₹${unsettledAmount}`,
        `${baseMsg}\n\nWould you like to settle the debt first?`,
        [
          { text: "Cancel", style: "cancel" },
          {
            text: "Leave anyway",
            style: "destructive",
            onPress: performLeave,
          },
          {
            text: `Settle ₹${unsettledAmount} & Leave`,
            style: "default",
            onPress: () => {
              const summary = useExpenseStore.getState().summary;
              const settle = useExpenseStore.getState().settleDebt;
              for (const s of summary.settlements) {
                if (!s.settled && s.fromMemberId === currentUser.id) {
                  settle(s.fromMemberId, s.toMemberId);
                }
              }
              performLeave();
            },
          },
        ],
      );
      return;
    }

    showAlert(`Leave ${household.name}?`, baseMsg, [
      { text: "Cancel", style: "cancel" },
      { text: "Leave", style: "destructive", onPress: performLeave },
    ]);
  };

  const handleTransferAdmin = (toId: string, toName: string) => {
    if (!currentUser) return;
    showConfirm(
      "Transfer admin",
      `Make ${toName} the admin of ${household?.name}? You'll lose admin privileges.`,
      {
        confirmText: "Transfer",
        onConfirm: () => {
          transferAdmin(currentUser.id, toId);
          showAlert("Admin transferred", `${toName} is now the admin of ${household?.name}.`);
        },
      },
    );
  };

  const handleGenerateInvite = () => {
    const code = generateInviteCode();
    showAlert(
      "Invite code generated",
      `Share this code with your new flatmate:\n\n${code}\n\nExpires in 7 days.`,
    );
  };

  const shareViaWhatsApp = () => {
    const code = household?.inviteCode || generateInviteCode();
    const msg = `Hey! Join my household "${household?.name}" on Bimi\n\nInvite code: ${code}\n\nMeals planned. Groceries ordered. Cook briefed.`;
    const url = `whatsapp://send?text=${encodeURIComponent(msg)}`;
    Linking.canOpenURL(url).then((supported) => {
      if (supported) Linking.openURL(url);
      else Share.share({ message: msg });
    });
  };

  const scrollRef = useTabScrollToTop<ScrollView>();

  return (
    <SafeScreen edges={["top", "bottom"]} ambientBackdrop>
      <ScrollView
        ref={scrollRef}
        style={{ flex: 1 }}
        contentContainerStyle={{ paddingHorizontal: spacing.lg, paddingBottom: 120 }}
      >
        <Text style={{ ...typography.h1, marginBottom: spacing.lg }}>My Household</Text>

        {!household && (
          <View style={{ marginBottom: spacing.lg }}>
            <GuidanceTip
              variant="hint"
              message="Manage your household, set auto-approval rules for groceries, configure your cook's details, and connect grocery platforms here."
            />
          </View>
        )}

        {household && (
          <>
            {/* Household card */}
            <View style={{ ...cardStyles, marginBottom: spacing.lg }}>
              <Text style={{ ...typography.h3, marginBottom: spacing.xs }}>{household.name}</Text>
              <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.xs, flexWrap: "wrap" }}>
                <Pill tone="neutral" active size="xs">{getHouseholdTypeLabel(household.type)}</Pill>
                <Text style={typography.caption}>{activeMembers.length} members</Text>
                {household.hasCook && (
                  <Text style={typography.caption} numberOfLines={1}>· Cook: {primaryCook?.name}</Text>
                )}
              </View>
            </View>

            {/* Members */}
            <Text style={{ ...typography.bodyBold, marginBottom: spacing.md }}>Members</Text>

            {activeMembers.map((member) => (
              <View key={member.id} style={{ ...listRowStyles, paddingVertical: spacing.lg }}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
                  <Avatar name={member.name} id={member.id} size="sm" />
                  <View style={{ flex: 1 }}>
                    <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.xs, flexWrap: "wrap" }}>
                      <Text style={typography.bodyBold}>{member.name}</Text>
                      {member.isAdmin && <Pill tone="success" active size="xs">Admin</Pill>}
                      {member.isPayingMember && <Pill tone="primary" active size="xs">Paying</Pill>}
                      {!member.isAvailable && <Pill tone="warning" active size="xs">Away</Pill>}
                    </View>
                    <Text style={{ ...typography.tiny, marginTop: 2 }}>
                      {getRoleLabel(member.role)} · Joined{" "}
                      {new Date(member.joinedAt).toLocaleDateString("en-IN", { month: "short", year: "numeric" })}
                    </Text>
                  </View>
                  {currentUser?.isAdmin && member.id !== currentUser.id && (
                    <View style={{ flexDirection: "row" }}>
                      <RipplePressable
                        onPress={() => handleTransferAdmin(member.id, member.name)}
                        hitSlop={{ top: 8, bottom: 8, left: 8, right: 4 }}
                        accessibilityLabel={`Make ${member.name} the admin`}
                        accessibilityHint="Transfers admin powers to this member"
                        accessibilityRole="button"
                        style={{ minWidth: 44, minHeight: 44, alignItems: "center", justifyContent: "center" }}
                      >
                        <Ionicons name="shield-outline" size={iconSize.sm} color={colors.accent.success} />
                      </RipplePressable>
                      <RipplePressable
                        onPress={() => handleRemoveMember(member.id, member.name)}
                        hitSlop={{ top: 8, bottom: 8, left: 4, right: 8 }}
                        accessibilityLabel={`Remove ${member.name} from the household`}
                        accessibilityHint="Removes this member from the household"
                        accessibilityRole="button"
                        style={{ minWidth: 44, minHeight: 44, alignItems: "center", justifyContent: "center" }}
                      >
                        <Ionicons name="person-remove-outline" size={iconSize.sm} color={colors.accent.danger} />
                      </RipplePressable>
                    </View>
                  )}
                </View>
                {member.id === currentUser?.id && (
                  <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: spacing.sm, paddingTop: spacing.sm }}>
                    <Text style={typography.small}>Available for meals today</Text>
                    <Switch
                      value={member.isAvailable}
                      onValueChange={(v) => setMemberAvailability(member.id, v)}
                      trackColor={{ false: colors.surface.elevated, true: tintedBg(colors.accent.success, 0.3) }}
                      thumbColor={member.isAvailable ? colors.accent.success : colors.text.muted}
                      accessibilityLabel="Available for meals today"
                    />
                  </View>
                )}
              </View>
            ))}

            {/* Invite code */}
            {household.inviteCode ? (
              <View style={{ ...cardStyles, marginTop: spacing.sm, marginBottom: spacing.lg, gap: spacing.md }}>
                <Text style={typography.tiny}>Invite code</Text>
                <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                  <Text style={typography.inviteCode}>{household.inviteCode}</Text>
                  <Button variant="secondary" size="sm" onPress={() => copyToClipboard(household.inviteCode!)}>
                    Copy
                  </Button>
                </View>
                {household.inviteCodeExpiresAt && (
                  <Text style={typography.tiny}>
                    Expires {new Date(household.inviteCodeExpiresAt).toLocaleDateString()}
                  </Text>
                )}
                <WhatsAppButton fullWidth onPress={shareViaWhatsApp}>
                  Share invite via WhatsApp
                </WhatsAppButton>
              </View>
            ) : (
              <View style={{ marginTop: spacing.sm, marginBottom: spacing.lg }}>
                <Button
                  variant="secondary"
                  size="md"
                  fullWidth
                  leadingIcon="add-circle-outline"
                  onPress={handleGenerateInvite}
                >
                  Generate invite code
                </Button>
              </View>
            )}

            {/* Vacation mode */}
            <View style={{ ...cardStyles, marginBottom: spacing.lg }}>
              <View style={{
                flexDirection: "row",
                alignItems: "center",
                justifyContent: "space-between",
                marginBottom: householdAway ? spacing.md : 0,
              }}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
                  <Ionicons name="airplane-outline" size={iconSize.sm} color={colors.accent.warning} />
                  <Text style={typography.bodyBold}>Everyone's away</Text>
                </View>
                <Switch
                  value={householdAway}
                  onValueChange={(v) => {
                    setHouseholdAway(v);
                    if (!v) { setAwayFrom(""); setAwayTo(""); }
                  }}
                  trackColor={{ false: colors.surface.elevated, true: tintedBg(colors.accent.warning, 0.3) }}
                  thumbColor={householdAway ? colors.accent.warning : colors.text.muted}
                  accessibilityLabel="Household away toggle"
                />
              </View>
              {householdAway && (
                <View style={{ gap: spacing.sm }}>
                  <View style={{ flexDirection: "row", gap: spacing.sm }}>
                    <View style={{ flex: 1 }}>
                      <Text style={{ ...typography.tiny, marginBottom: spacing.xs }}>From (YYYY-MM-DD)</Text>
                      <TextInput
                        value={awayFrom}
                        onChangeText={setAwayFrom}
                        placeholder="2026-04-20"
                        placeholderTextColor={colors.text.muted}
                        style={{ ...inputStyles, borderWidth: 1, borderColor: colors.border.subtle }}
                      />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={{ ...typography.tiny, marginBottom: spacing.xs }}>To (YYYY-MM-DD)</Text>
                      <TextInput
                        value={awayTo}
                        onChangeText={setAwayTo}
                        placeholder="2026-04-25"
                        placeholderTextColor={colors.text.muted}
                        style={{ ...inputStyles, borderWidth: 1, borderColor: colors.border.subtle }}
                      />
                    </View>
                  </View>
                  <Button
                    variant="success"
                    size="md"
                    fullWidth
                    onPress={() => {
                      if (!awayFrom || !awayTo) {
                        showAlert("Missing dates", "Please enter both From and To dates.");
                        return;
                      }
                      const tempId = `temp-vac-${Date.now()}`;
                      addAbsence({
                        id: tempId,
                        cookName: primaryCook?.name || "Cook",
                        date: awayFrom,
                        endDate: awayTo,
                        reason: "Household vacation",
                        replacementBooked: false,
                      });
                      haptic("success");
                      showAlert("Saved", "Cook will be notified via WhatsApp share.");

                      // Backend sync — fire-and-forget. Local
                      // `temp-*` id survives until the POST returns
                      // and we swap to the backend UUID; the next
                      // useLiveSync poll reconciles for other devices.
                      if (isRealAuth() && familyId && primaryCook?.id) {
                        postAbsence
                          .mutateAsync({
                            parentId: primaryCook.id,
                            date: awayFrom,
                            endDate: awayTo,
                            reason: "Household vacation",
                          })
                          .then((created) => swapAbsenceId(tempId, created.id))
                          .catch(() => {
                            // Local entry stays; next online poll
                            // reconciles if the row exists server-side.
                          });
                      }
                    }}
                  >
                    Save
                  </Button>
                </View>
              )}
            </View>

            {/* Navigation rows — sub-routes */}
            <View style={{ ...cardStyles, padding: 0, paddingHorizontal: spacing.lg, marginBottom: spacing.lg }}>
              {household.hasCook && (
                <SettingsRow
                  label="Cook"
                  description={primaryCook ? `${primaryCook.name} · ${primaryCook.schedule}` : undefined}
                  leadingIcon="restaurant-outline"
                  chevron
                  onPress={() => router.push("/settings/cook" as any)}
                />
              )}
              <SettingsRow
                label="Auto-rules"
                description="Auto-approve grocery orders within set limits"
                leadingIcon="flash-outline"
                chevron
                onPress={() => router.push("/settings/auto-rules" as any)}
              />
              <SettingsRow
                label="Dietary"
                description="Allergies, intolerances, and food preferences"
                leadingIcon="heart-outline"
                chevron
                onPress={() => router.push("/settings/dietary" as any)}
                isLast
              />
            </View>

            {/* Quick navigation rows.
                2026-05-03 audit: rows pointing to deleted screens removed —
                Insights, Notification preferences, Grocery platforms (the
                multi-platform connect UI), and Give feedback have all been
                retired alongside the screens. The single surviving row
                points at Bimi Recipes (formerly Dish Catalog). */}
            <View style={{ ...cardStyles, padding: 0, paddingHorizontal: spacing.lg, marginBottom: spacing.lg }}>
              <SettingsRow
                label="Bimi Recipes"
                leadingIcon="restaurant-outline"
                chevron
                onPress={() => router.push("/dish-catalog" as any)}
              />
              <SettingsRow
                label="Saved recipes"
                description="YouTube and Instagram links you've added"
                leadingIcon="bookmark-outline"
                chevron
                onPress={() => router.push("/saved-recipes" as any)}
                isLast
              />
            </View>

            {/* Destructive actions */}
            <View style={{ alignItems: "center", paddingVertical: spacing.md }}>
              <RipplePressable
                onPress={handleLeave}
                accessibilityRole="button"
                accessibilityLabel="Leave this house"
                hitSlop={{ top: 8, bottom: 8, left: 12, right: 12 }}
                style={{ alignItems: "center", paddingVertical: spacing.sm }}
              >
                <Text style={{ ...typography.bodyBold, color: colors.accent.danger }}>Leave this house</Text>
                {unsettledAmount > 0 && (
                  <Text style={{ ...typography.tiny, marginTop: 2 }}>You owe ₹{unsettledAmount}</Text>
                )}
              </RipplePressable>

              <RipplePressable
                onPress={() => { logout(); router.replace("/login"); }}
                accessibilityRole="button"
                accessibilityLabel="Log out"
                hitSlop={{ top: 8, bottom: 8, left: 12, right: 12 }}
                style={{ alignItems: "center", paddingVertical: spacing.sm, marginTop: spacing.xs }}
              >
                <Text style={{ ...typography.caption, color: colors.text.muted }}>Log out</Text>
              </RipplePressable>
            </View>
          </>
        )}

        {!household && (
          <CalloutCard tone="info" leadingIcon="people-outline" title="No household yet">
            Set up a household to start using Bimi's full features.
          </CalloutCard>
        )}
      </ScrollView>
    </SafeScreen>
  );
}
