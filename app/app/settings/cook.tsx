import { View, Text, ScrollView, TextInput, Switch, Linking } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useState, useMemo } from "react";
import { useRouter } from "expo-router";
import {
  useHouseholdStore,
  useMealStore,
  useCookAbsenceStore,
} from "@/lib/store";
import { useAuthStore } from "@/lib/auth-store";
import { isRealAuth } from "@/lib/auth-flags";
import { usePostCookAbsence } from "@/lib/api";
import { useCookSettingsStore } from "@/lib/cook-settings-store";
import { getUpcomingFestivals } from "@/lib/festivals";
import { shareWithCook } from "@/lib/whatsapp-share";
import {
  colors,
  cardStyles,
  spacing,
  radius,
  typography,
  inputStyles,
  iconSize,
  tintedBg,
} from "@/lib/theme";
import { haptic } from "@/lib/haptics";
import { showAlert, showConfirm } from "@/lib/dialogs";
import { safeBack } from "@/lib/safe-back";
import {
  SafeScreen,
  ScreenHeader,
  Button,
  Pill,
  TextLink,
  CalloutCard,
  IconBadge,
  MeterBar,
  SectionEyebrow,
} from "@/components/ui";
import { WhatsAppButton } from "@/components/patterns";
import { RipplePressable } from "@/components/RipplePressable";

function getOrdinalSuffix(n: number): string {
  if (n % 100 >= 11 && n % 100 <= 13) return `${n}th`;
  switch (n % 10) {
    case 1: return `${n}st`;
    case 2: return `${n}nd`;
    case 3: return `${n}rd`;
    default: return `${n}th`;
  }
}

type Recurrence = "daily" | "weekdays" | "specific_days" | "one_time";

export default function CookRoute() {
  const router = useRouter();
  const household = useHouseholdStore((s) => s.household);
  const setCook = useHouseholdStore((s) => s.setCook);
  const addCook = useHouseholdStore((s) => s.addCook);
  const removeCook = useHouseholdStore((s) => s.removeCook);
  const todaysPlans = useMealStore((s) => s.todaysPlans);
  const mealHistory = useMealStore((s) => s.mealHistory);
  const absences = useCookAbsenceStore((s) => s.absences);
  const addAbsence = useCookAbsenceStore((s) => s.addAbsence);
  const swapAbsenceId = useCookAbsenceStore((s) => s.swapAbsenceId);
  const familyId = useAuthStore((s) => s.familyId) ?? "";
  const postAbsence = usePostCookAbsence(familyId);

  // Persisted cook settings (holidays + instructions). Survive app restarts.
  const cookHolidays = useCookSettingsStore((s) => s.holidays);
  const addHolidayToStore = useCookSettingsStore((s) => s.addHoliday);
  const removeHolidayFromStore = useCookSettingsStore((s) => s.removeHoliday);
  const cookInstructions = useCookSettingsStore((s) => s.instructions);
  const addInstructionToStore = useCookSettingsStore((s) => s.addInstruction);
  const toggleInstructionInStore = useCookSettingsStore((s) => s.toggleInstruction);
  const removeInstructionFromStore = useCookSettingsStore((s) => s.removeInstruction);

  const primaryCook = household?.cooks?.[0];

  // Local-first absence add: writes the row to the Zustand store with
  // a `temp-*` id so the calendar updates immediately, then fires a
  // background POST and swaps in the backend UUID on success. Failure
  // keeps the local entry; the next 30s useLiveSync poll reconciles
  // if the row exists server-side.
  const addAbsenceWithSync = (input: {
    tempId: string;
    cookName: string;
    date: string;
    endDate?: string;
    reason?: string;
  }) => {
    addAbsence({
      id: input.tempId,
      cookName: input.cookName,
      date: input.date,
      endDate: input.endDate,
      reason: input.reason,
      replacementBooked: false,
    });
    if (!isRealAuth() || !familyId || !primaryCook?.id) return;
    postAbsence
      .mutateAsync({
        parentId: primaryCook.id,
        date: input.date,
        endDate: input.endDate,
        reason: input.reason,
      })
      .then((created) => swapAbsenceId(input.tempId, created.id))
      .catch(() => {});
  };

  const [editingCook, setEditingCook] = useState(false);
  const [editCookName, setEditCookName] = useState("");
  const [editCookPhone, setEditCookPhone] = useState("");
  const [editCookSchedule, setEditCookSchedule] = useState("");
  const [editCookPayDay, setEditCookPayDay] = useState("");
  const [editCookDietaryRestrictions, setEditCookDietaryRestrictions] = useState("");
  const [editBrandPrefs, setEditBrandPrefs] = useState<Array<{ category: string; brand: string }>>([]);

  const [showAddHoliday, setShowAddHoliday] = useState(false);
  const [newHolidayDate, setNewHolidayDate] = useState("");
  const [newHolidayReason, setNewHolidayReason] = useState("");

  const [showAddCook, setShowAddCook] = useState(false);
  const [newCookName, setNewCookName] = useState("");
  const [newCookPhone, setNewCookPhone] = useState("");
  const [newCookSchedule, setNewCookSchedule] = useState("");

  const [newDish, setNewDish] = useState("");
  const [editingRepertoire, setEditingRepertoire] = useState(false);

  const [showAddInstruction, setShowAddInstruction] = useState(false);
  const [newInstructionText, setNewInstructionText] = useState("");
  const [newInstructionRecurrence, setNewInstructionRecurrence] = useState<Recurrence>("daily");
  const [newInstructionDays, setNewInstructionDays] = useState<string[]>([]);

  const upcomingFestivals = useMemo(() => getUpcomingFestivals(30), []);

  const performanceMetrics = useMemo(() => {
    const now = new Date();
    const monthStart = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
    const thisMonthPlans = todaysPlans.filter((p) => p.rating);
    const historyThisMonth = mealHistory.filter((h) => h.date.startsWith(monthStart));
    const allRatings = [
      ...thisMonthPlans.map((p) => p.rating!),
      ...historyThisMonth.flatMap((h) => h.ratings.map((r) => r.rating)),
    ];
    const ratingCount = allRatings.length;
    const avgRating = ratingCount > 0
      ? Math.round((allRatings.reduce((a, b) => a + b, 0) / ratingCount) * 10) / 10
      : null;
    const mealsCookedThisMonth = historyThisMonth.length + thisMonthPlans.length;
    const absencesThisMonth = absences.filter((a) => a.date.startsWith(monthStart)).length;
    const totalDays = now.getDate();
    const attendanceDays = Math.max(totalDays - absencesThisMonth, 0);
    const hasData = ratingCount > 0 || mealsCookedThisMonth > 0;
    return { avgRating, mealsCookedThisMonth, attendanceDays, totalDays, ratingCount, hasData };
  }, [todaysPlans, mealHistory, absences]);

  // No cook? Honest empty state with CTA to add one.
  if (!primaryCook) {
    return (
      <SafeScreen edges={["top", "bottom"]} ambientBackdrop>
        <ScrollView contentContainerStyle={{ paddingHorizontal: spacing.lg, paddingBottom: 120 }}>
          <ScreenHeader back title="Cook" subtitle="No cook is set up yet." />
          <CalloutCard tone="info" leadingIcon="restaurant-outline" title="Add your cook">
            Set up cook details to plan meals, track attendance, and send WhatsApp reminders.
          </CalloutCard>
          <View style={{ marginTop: spacing.lg }}>
            <Button
              variant="primary"
              size="lg"
              fullWidth
              leadingIcon="add-circle"
              onPress={() => router.push("/cook-interview" as any)}
            >
              Set up cook profile
            </Button>
          </View>
        </ScrollView>
      </SafeScreen>
    );
  }

  const startEdit = () => {
    setEditCookName(primaryCook.name);
    setEditCookPhone(primaryCook.whatsappNumber);
    setEditCookSchedule(primaryCook.schedule);
    setEditCookPayDay(primaryCook.payDay?.toString() || "");
    setEditCookDietaryRestrictions((primaryCook.dietaryRestrictions || []).join(", "));
    setEditBrandPrefs(
      primaryCook.brandPreferences
        ? Object.entries(primaryCook.brandPreferences).map(([category, brand]) => ({ category, brand }))
        : [],
    );
    setEditingCook(true);
  };

  const saveEdit = () => {
    const payDay = parseInt(editCookPayDay);
    const restrictions = editCookDietaryRestrictions
      .split(",").map((s) => s.trim()).filter(Boolean);
    const brandPreferences: Record<string, string> = {};
    editBrandPrefs.forEach((bp) => {
      if (bp.category.trim() && bp.brand.trim()) {
        brandPreferences[bp.category.trim()] = bp.brand.trim();
      }
    });
    setCook({
      ...primaryCook,
      name: editCookName.trim() || primaryCook.name,
      whatsappNumber: editCookPhone.trim() || primaryCook.whatsappNumber,
      schedule: editCookSchedule.trim() || primaryCook.schedule,
      payDay: isNaN(payDay) ? primaryCook.payDay : payDay,
      dietaryRestrictions: restrictions,
      brandPreferences,
    });
    setEditingCook(false);
    haptic("success");
  };

  const handleRemoveCook = () => {
    showConfirm(
      "Remove cook",
      `Remove ${primaryCook.name} from your household? You can add a new cook later.`,
      {
        confirmText: "Remove",
        destructive: true,
        onConfirm: () => {
          removeCook();
          haptic("warning");
          safeBack();
        },
      },
    );
  };

  return (
    <SafeScreen edges={["top", "bottom"]} ambientBackdrop>
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ paddingHorizontal: spacing.lg, paddingBottom: 120 }}
        keyboardShouldPersistTaps="handled"
      >
        <ScreenHeader back title="Cook" subtitle={primaryCook.name} />

        {/* Cook profile card */}
        <View style={{ ...cardStyles, marginBottom: spacing.lg }}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md, marginBottom: spacing.lg }}>
            <IconBadge icon="restaurant" tone="primary" size="lg" circle />
            <View style={{ flex: 1 }}>
              {editingCook ? (
                <TextInput
                  value={editCookName}
                  onChangeText={setEditCookName}
                  placeholder="Cook's name"
                  placeholderTextColor={colors.text.muted}
                  accessibilityLabel="Cook's name"
                  autoCapitalize="words"
                  autoComplete="name"
                  textContentType="name"
                  returnKeyType="next"
                  style={{ ...inputStyles, marginBottom: spacing.xs, borderWidth: 1, borderColor: colors.border.subtle }}
                />
              ) : (
                <Text style={typography.h2}>{primaryCook.name}</Text>
              )}
              {editingCook ? (
                <TextInput
                  value={editCookSchedule}
                  onChangeText={setEditCookSchedule}
                  placeholder="Schedule (e.g. Mon–Sat, 8 AM)"
                  placeholderTextColor={colors.text.muted}
                  accessibilityLabel="Cook's schedule"
                  autoCapitalize="words"
                  returnKeyType="next"
                  style={{ ...inputStyles, borderWidth: 1, borderColor: colors.border.subtle }}
                />
              ) : (
                <Text style={typography.caption}>{primaryCook.schedule}</Text>
              )}
            </View>
            <RipplePressable
              onPress={() => (editingCook ? setEditingCook(false) : startEdit())}
              hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
              accessibilityRole="button"
              accessibilityLabel={editingCook ? "Cancel editing" : "Edit cook profile"}
              style={{ minWidth: 44, minHeight: 44, alignItems: "center", justifyContent: "center" }}
            >
              <Ionicons name={editingCook ? "close-outline" : "pencil-outline"} size={iconSize.md} color={colors.text.secondary} />
            </RipplePressable>
          </View>

          <View style={{ gap: spacing.sm }}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
              <Ionicons name="call-outline" size={iconSize.sm} color={colors.text.secondary} />
              {editingCook ? (
                <TextInput
                  value={editCookPhone}
                  onChangeText={setEditCookPhone}
                  placeholder="WhatsApp number"
                  placeholderTextColor={colors.text.muted}
                  keyboardType="phone-pad"
                  accessibilityLabel="Cook's WhatsApp number"
                  autoComplete="tel"
                  textContentType="telephoneNumber"
                  returnKeyType="done"
                  style={{ ...inputStyles, flex: 1, borderWidth: 1, borderColor: colors.border.subtle }}
                />
              ) : (
                <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, flex: 1 }}>
                  <Text style={typography.body}>{primaryCook.whatsappNumber}</Text>
                  <TextLink
                    size="sm"
                    tone="primary"
                    leadingIcon="logo-whatsapp"
                    onPress={() => {
                      Linking.openURL(
                        `whatsapp://send?phone=${primaryCook.whatsappNumber.replace(/[^0-9]/g, "")}&text=${encodeURIComponent("Namaste! This is a test from Bimi to confirm WhatsApp is set up correctly.")}`,
                      );
                    }}
                    accessibilityLabel="Send a test WhatsApp message to verify the number"
                  >
                    Ping
                  </TextLink>
                </View>
              )}
            </View>
            <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
              <Ionicons name="calendar-outline" size={iconSize.sm} color={colors.text.secondary} />
              {editingCook ? (
                <View style={{ flexDirection: "row", alignItems: "center", gap: 6, flex: 1 }}>
                  <Text style={typography.body}>Pay day:</Text>
                  <TextInput
                    value={editCookPayDay}
                    onChangeText={setEditCookPayDay}
                    placeholder="e.g. 1"
                    placeholderTextColor={colors.text.muted}
                    keyboardType="numeric"
                    maxLength={2}
                    accessibilityLabel="Day of the month to pay the cook"
                    returnKeyType="done"
                    style={{ ...inputStyles, width: 60, textAlign: "center", borderWidth: 1, borderColor: colors.border.subtle }}
                  />
                  <Text style={typography.caption}>of month</Text>
                </View>
              ) : primaryCook.payDay ? (
                <Text style={typography.body}>Pay day: {getOrdinalSuffix(primaryCook.payDay)} of month</Text>
              ) : (
                <Text style={{ ...typography.body, color: colors.text.muted }}>No pay day set</Text>
              )}
            </View>
          </View>

          {editingCook && (
            <View style={{ gap: spacing.md, marginTop: spacing.md }}>
              <View style={{ flexDirection: "row", alignItems: "flex-start", gap: spacing.sm }}>
                <Ionicons name="leaf-outline" size={iconSize.sm} color={colors.text.secondary} style={{ marginTop: 22 }} />
                <View style={{ flex: 1 }}>
                  <Text style={{ ...typography.tiny, marginBottom: 4 }}>Dietary restrictions (comma-separated)</Text>
                  <TextInput
                    value={editCookDietaryRestrictions}
                    onChangeText={setEditCookDietaryRestrictions}
                    placeholder="e.g., No beef, No pork"
                    placeholderTextColor={colors.text.muted}
                    accessibilityLabel="Cook's dietary restrictions (comma-separated)"
                    autoCapitalize="words"
                    returnKeyType="done"
                    style={{ ...inputStyles, borderWidth: 1, borderColor: colors.border.subtle }}
                  />
                </View>
              </View>

              {/* Brand preferences */}
              <View style={{ marginTop: spacing.sm }}>
                <SectionEyebrow tone="secondary">Preferred brands</SectionEyebrow>
                {editBrandPrefs.map((bp, idx) => (
                  <View key={idx} style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, marginBottom: spacing.xs }}>
                    <TextInput
                      value={bp.category}
                      onChangeText={(t) => {
                        const copy = [...editBrandPrefs];
                        copy[idx] = { ...copy[idx]!, category: t };
                        setEditBrandPrefs(copy);
                      }}
                      placeholder="Category"
                      placeholderTextColor={colors.text.muted}
                      accessibilityLabel={`Brand preference ${idx + 1}, category`}
                      autoCapitalize="words"
                      returnKeyType="next"
                      style={{ ...inputStyles, flex: 1, borderWidth: 1, borderColor: colors.border.subtle }}
                    />
                    <TextInput
                      value={bp.brand}
                      onChangeText={(t) => {
                        const copy = [...editBrandPrefs];
                        copy[idx] = { ...copy[idx]!, brand: t };
                        setEditBrandPrefs(copy);
                      }}
                      placeholder="Brand"
                      placeholderTextColor={colors.text.muted}
                      accessibilityLabel={`Brand preference ${idx + 1}, brand name`}
                      autoCapitalize="words"
                      returnKeyType="done"
                      style={{ ...inputStyles, flex: 1, borderWidth: 1, borderColor: colors.border.subtle }}
                    />
                    <RipplePressable
                      onPress={() => setEditBrandPrefs(editBrandPrefs.filter((_, i) => i !== idx))}
                      hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                      accessibilityLabel={`Remove brand preference ${idx + 1}`}
                      style={{ minWidth: 36, minHeight: 36, alignItems: "center", justifyContent: "center" }}
                    >
                      <Ionicons name="close-circle" size={iconSize.sm} color={colors.accent.danger} />
                    </RipplePressable>
                  </View>
                ))}
                <TextLink
                  onPress={() => setEditBrandPrefs([...editBrandPrefs, { category: "", brand: "" }])}
                  size="sm"
                  tone="primary"
                  leadingIcon="add-circle-outline"
                >
                  Add brand
                </TextLink>
              </View>

              <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.md }}>
                <View style={{ flex: 1 }}>
                  <Button variant="primary" size="md" fullWidth onPress={saveEdit}>Save</Button>
                </View>
                <View style={{ flex: 1 }}>
                  <Button variant="secondary" size="md" fullWidth onPress={() => setEditingCook(false)}>Cancel</Button>
                </View>
              </View>
            </View>
          )}
        </View>

        {/* WhatsApp introduction */}
        <View style={{ marginBottom: spacing.lg }}>
          <WhatsAppButton
            fullWidth
            onPress={() => {
              shareWithCook(
                primaryCook.whatsappNumber,
                `Hi ${primaryCook.name}! Main Bimi hoon, ${household?.name || "aapke ghar"} ka kitchen assistant. Aap mujhe yahan message kar sakte hain — Hindi mein, voice note mein, kuch bhi.`,
              );
            }}
          >
            Send introduction via WhatsApp
          </WhatsAppButton>
        </View>

        {/* Interview / Verify */}
        <View style={{ flexDirection: "row", gap: spacing.sm, marginBottom: spacing.lg }}>
          <View style={{ flex: 1 }}>
            <Button
              variant="secondary"
              size="md"
              fullWidth
              leadingIcon="clipboard-outline"
              onPress={() => router.push("/cook-interview" as any)}
            >
              Interview cook
            </Button>
          </View>
          <View style={{ flex: 1 }}>
            <Button
              variant="secondary"
              size="md"
              fullWidth
              leadingIcon="people-outline"
              onPress={() => router.push("/cook-verify" as any)}
            >
              Verify profile
            </Button>
          </View>
        </View>

        {/* Performance — honest empty state until real data exists */}
        <View style={{ ...cardStyles, marginBottom: spacing.lg }}>
          <SectionEyebrow>Performance</SectionEyebrow>
          {!performanceMetrics.hasData ? (
            <Text style={{ ...typography.caption, color: colors.text.secondary }}>
              Not enough data yet. Performance shows up once your household rates meals and the cook serves a few.
            </Text>
          ) : (
            <View style={{ gap: spacing.sm }}>
              {performanceMetrics.avgRating !== null && (
                <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
                  <Text style={{ ...typography.caption, flex: 1 }}>Avg meal rating</Text>
                  <View style={{ width: 80 }}>
                    <MeterBar
                      value={performanceMetrics.avgRating}
                      max={5}
                      tone={
                        performanceMetrics.avgRating > 4
                          ? "success"
                          : performanceMetrics.avgRating > 3
                            ? "warning"
                            : "danger"
                      }
                      size="md"
                    />
                  </View>
                  <Text style={{ ...typography.captionBold, minWidth: 32, textAlign: "right" }}>
                    {performanceMetrics.avgRating}/5
                  </Text>
                </View>
              )}
              {performanceMetrics.mealsCookedThisMonth > 0 && (
                <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                  <Text style={typography.caption}>Meals this month</Text>
                  <Text style={typography.captionBold}>{performanceMetrics.mealsCookedThisMonth}</Text>
                </View>
              )}
              <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                <Text style={typography.caption}>Attendance</Text>
                <Text style={typography.captionBold}>
                  {performanceMetrics.attendanceDays}/{performanceMetrics.totalDays} days
                </Text>
              </View>
            </View>
          )}
        </View>

        {/* Additional cooks */}
        {household && household.cooks.length > 1 && household.cooks.slice(1).map((cook) => (
          <View key={cook.id} style={{ ...cardStyles, marginBottom: spacing.sm }}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
              <IconBadge icon="restaurant" tone="neutral" size="md" circle />
              <View style={{ flex: 1 }}>
                <Text style={typography.bodyBold}>{cook.name}</Text>
                <Text style={typography.tiny}>{cook.schedule} · {cook.whatsappNumber}</Text>
              </View>
            </View>
            {cook.repertoire.length > 0 && (
              <Text style={{ ...typography.tiny, marginTop: spacing.xs }} numberOfLines={1}>
                {cook.repertoire.slice(0, 5).join(", ")}{cook.repertoire.length > 5 ? ` +${cook.repertoire.length - 5}` : ""}
              </Text>
            )}
          </View>
        ))}

        {/* Add another cook */}
        {!showAddCook ? (
          <View style={{ marginBottom: spacing.lg }}>
            <Button
              variant="secondary"
              size="md"
              fullWidth
              leadingIcon="add-circle-outline"
              onPress={() => setShowAddCook(true)}
            >
              Add another cook
            </Button>
          </View>
        ) : (
          <View style={{ ...cardStyles, marginBottom: spacing.lg, gap: spacing.sm }}>
            <SectionEyebrow>New cook</SectionEyebrow>
            <TextInput
              value={newCookName}
              onChangeText={setNewCookName}
              placeholder="Cook's name"
              placeholderTextColor={colors.text.muted}
              accessibilityLabel="New cook's name"
              autoCapitalize="words"
              autoComplete="name"
              textContentType="name"
              returnKeyType="next"
              style={{ ...inputStyles, borderWidth: 1, borderColor: colors.border.subtle }}
            />
            <TextInput
              value={newCookPhone}
              onChangeText={setNewCookPhone}
              placeholder="WhatsApp number"
              placeholderTextColor={colors.text.muted}
              keyboardType="phone-pad"
              accessibilityLabel="New cook's WhatsApp number"
              autoComplete="tel"
              textContentType="telephoneNumber"
              returnKeyType="next"
              style={{ ...inputStyles, borderWidth: 1, borderColor: colors.border.subtle }}
            />
            <TextInput
              value={newCookSchedule}
              onChangeText={setNewCookSchedule}
              placeholder="Schedule (e.g. Mon–Fri, 9 AM)"
              placeholderTextColor={colors.text.muted}
              accessibilityLabel="New cook's schedule"
              autoCapitalize="words"
              returnKeyType="done"
              style={{ ...inputStyles, borderWidth: 1, borderColor: colors.border.subtle }}
            />
            <View style={{ flexDirection: "row", gap: spacing.sm }}>
              <View style={{ flex: 1 }}>
                <Button
                  variant="primary"
                  size="md"
                  fullWidth
                  onPress={() => {
                    if (!newCookName.trim() || !newCookPhone.trim()) {
                      showAlert("Missing info", "Please enter at least name and phone.");
                      return;
                    }
                    addCook({
                      id: `cook-${Date.now()}`,
                      name: newCookName.trim(),
                      whatsappNumber: newCookPhone.trim(),
                      schedule: newCookSchedule.trim() || "Schedule not set",
                      repertoire: [],
                    });
                    setNewCookName("");
                    setNewCookPhone("");
                    setNewCookSchedule("");
                    setShowAddCook(false);
                    haptic("success");
                  }}
                >
                  Add
                </Button>
              </View>
              <View style={{ flex: 1 }}>
                <Button
                  variant="secondary"
                  size="md"
                  fullWidth
                  onPress={() => {
                    setShowAddCook(false);
                    setNewCookName("");
                    setNewCookPhone("");
                    setNewCookSchedule("");
                  }}
                >
                  Cancel
                </Button>
              </View>
            </View>
          </View>
        )}

        {/* Repertoire */}
        <View style={{ marginBottom: spacing.lg }}>
          <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.md }}>
            <Text style={typography.bodyBold}>Repertoire ({primaryCook.repertoire.length} dishes)</Text>
            <RipplePressable
              onPress={() => setEditingRepertoire(!editingRepertoire)}
              hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
              accessibilityLabel={editingRepertoire ? "Done editing repertoire" : "Edit repertoire"}
              style={{ minWidth: 44, minHeight: 44, alignItems: "center", justifyContent: "center" }}
            >
              <Ionicons name={editingRepertoire ? "checkmark-outline" : "pencil-outline"} size={iconSize.sm} color={colors.text.secondary} />
            </RipplePressable>
          </View>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.xs }}>
            {primaryCook.repertoire.map((dish) => (
              <Pill
                key={dish}
                tone="neutral"
                active={false}
                size="sm"
                onPress={editingRepertoire ? () => {
                  setCook({ ...primaryCook, repertoire: primaryCook.repertoire.filter((d) => d !== dish) });
                  haptic("selection");
                } : undefined}
                trailingIcon={editingRepertoire ? "close-circle" : undefined}
              >
                {dish}
              </Pill>
            ))}
          </View>
          {editingRepertoire && (
            <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.xs, marginTop: spacing.sm }}>
              <TextInput
                value={newDish}
                onChangeText={setNewDish}
                placeholder="Add dish…"
                placeholderTextColor={colors.text.muted}
                accessibilityLabel="Dish name to add to repertoire"
                autoCapitalize="words"
                returnKeyType="done"
                style={{ ...inputStyles, flex: 1, borderWidth: 1, borderColor: colors.border.subtle }}
                onSubmitEditing={() => {
                  if (newDish.trim() && !primaryCook.repertoire.includes(newDish.trim())) {
                    setCook({ ...primaryCook, repertoire: [...primaryCook.repertoire, newDish.trim()] });
                    setNewDish("");
                    haptic("success");
                  }
                }}
              />
              <Button
                variant="secondary"
                size="md"
                onPress={() => {
                  if (newDish.trim() && !primaryCook.repertoire.includes(newDish.trim())) {
                    setCook({ ...primaryCook, repertoire: [...primaryCook.repertoire, newDish.trim()] });
                    setNewDish("");
                    haptic("success");
                  }
                }}
              >
                Add
              </Button>
            </View>
          )}
        </View>

        {/* Read-only dietary restrictions */}
        {primaryCook.dietaryRestrictions && primaryCook.dietaryRestrictions.length > 0 && (
          <View style={{ marginBottom: spacing.lg }}>
            <SectionEyebrow>Dietary restrictions</SectionEyebrow>
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.xs }}>
              {primaryCook.dietaryRestrictions.map((r) => (
                <Pill key={r} tone="warning" active size="sm">{r}</Pill>
              ))}
            </View>
          </View>
        )}

        {/* Read-only brand preferences */}
        {!editingCook && primaryCook.brandPreferences && Object.keys(primaryCook.brandPreferences).length > 0 && (
          <View style={{ marginBottom: spacing.lg }}>
            <SectionEyebrow>Preferred brands</SectionEyebrow>
            <View style={{ gap: spacing.xs }}>
              {Object.entries(primaryCook.brandPreferences).map(([cat, brand]) => (
                <View key={cat} style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
                  <Text style={{ ...typography.caption, width: 80 }}>{cat}</Text>
                  <Text style={typography.captionBold}>{brand}</Text>
                </View>
              ))}
            </View>
          </View>
        )}

        {/* Planned holidays */}
        <View style={{ marginBottom: spacing.lg }}>
          <SectionEyebrow>Planned holidays</SectionEyebrow>
          {upcomingFestivals.map((f) => {
            const isOff = cookHolidays.some((h) => h.date === f.date);
            return (
              <View
                key={f.name}
                style={{
                  flexDirection: "row",
                  alignItems: "center",
                  justifyContent: "space-between",
                  paddingVertical: spacing.sm,
                  borderBottomWidth: 1,
                  borderBottomColor: colors.divider.default,
                }}
              >
                <View style={{ flex: 1, marginRight: spacing.sm }}>
                  <Text style={typography.captionBold}>{f.name}</Text>
                  <Text style={typography.tiny}>
                    {new Date(f.date).toLocaleDateString("en-IN", { month: "short", day: "numeric" })}
                  </Text>
                </View>
                <Switch
                  value={isOff}
                  onValueChange={(v) => {
                    if (v) {
                      addHolidayToStore({ date: f.date, reason: f.name });
                      addAbsenceWithSync({
                        tempId: `temp-hol-${Date.now()}-${f.date}`,
                        cookName: primaryCook.name,
                        date: f.date,
                        reason: f.name,
                      });
                    } else {
                      removeHolidayFromStore(f.date);
                    }
                  }}
                  trackColor={{ false: colors.surface.elevated, true: tintedBg(colors.accent.warning, 0.3) }}
                  thumbColor={isOff ? colors.accent.warning : colors.text.muted}
                  accessibilityLabel={`${f.name} holiday off toggle`}
                />
              </View>
            );
          })}
          {cookHolidays
            .filter((h) => !upcomingFestivals.some((f) => f.date === h.date))
            .map((h) => (
              <View
                key={h.date}
                style={{
                  flexDirection: "row",
                  alignItems: "center",
                  justifyContent: "space-between",
                  paddingVertical: spacing.sm,
                  borderBottomWidth: 1,
                  borderBottomColor: colors.divider.default,
                }}
              >
                <View style={{ flex: 1 }}>
                  <Text style={typography.captionBold}>{h.reason || "Custom Holiday"}</Text>
                  <Text style={typography.tiny}>{h.date}</Text>
                </View>
                <RipplePressable
                  onPress={() => removeHolidayFromStore(h.date)}
                  hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                  accessibilityLabel={`Remove holiday ${h.reason || h.date}`}
                  style={{ minWidth: 44, minHeight: 44, alignItems: "center", justifyContent: "center" }}
                >
                  <Ionicons name="close-circle" size={iconSize.sm} color={colors.accent.danger} />
                </RipplePressable>
              </View>
            ))}

          {!showAddHoliday ? (
            <View style={{ marginTop: spacing.sm }}>
              <TextLink
                onPress={() => setShowAddHoliday(true)}
                size="sm"
                tone="primary"
                leadingIcon="add-circle-outline"
              >
                Add custom holiday
              </TextLink>
            </View>
          ) : (
            <View style={{ gap: spacing.sm, paddingTop: spacing.md }}>
              <TextInput
                value={newHolidayDate}
                onChangeText={setNewHolidayDate}
                placeholder="Date (YYYY-MM-DD)"
                placeholderTextColor={colors.text.muted}
                accessibilityLabel="Cook holiday date in year-month-day format"
                autoCorrect={false}
                returnKeyType="next"
                style={{ ...inputStyles, borderWidth: 1, borderColor: colors.border.subtle }}
              />
              <TextInput
                value={newHolidayReason}
                onChangeText={setNewHolidayReason}
                placeholder="Reason"
                placeholderTextColor={colors.text.muted}
                accessibilityLabel="Cook holiday reason"
                autoCapitalize="sentences"
                returnKeyType="done"
                style={{ ...inputStyles, borderWidth: 1, borderColor: colors.border.subtle }}
              />
              <View style={{ flexDirection: "row", gap: spacing.sm }}>
                <View style={{ flex: 1 }}>
                  <Button
                    variant="primary"
                    size="md"
                    fullWidth
                    onPress={() => {
                      if (!newHolidayDate.trim()) {
                        showAlert("Missing date", "Enter a valid date.");
                        return;
                      }
                      addHolidayToStore({
                        date: newHolidayDate.trim(),
                        reason: newHolidayReason.trim() || "Custom holiday",
                      });
                      addAbsenceWithSync({
                        tempId: `temp-custom-${Date.now()}`,
                        cookName: primaryCook.name,
                        date: newHolidayDate.trim(),
                        reason: newHolidayReason.trim() || "Custom holiday",
                      });
                      setNewHolidayDate("");
                      setNewHolidayReason("");
                      setShowAddHoliday(false);
                      haptic("success");
                    }}
                  >
                    Add
                  </Button>
                </View>
                <View style={{ flex: 1 }}>
                  <Button
                    variant="secondary"
                    size="md"
                    fullWidth
                    onPress={() => { setShowAddHoliday(false); setNewHolidayDate(""); setNewHolidayReason(""); }}
                  >
                    Cancel
                  </Button>
                </View>
              </View>
            </View>
          )}
        </View>

        {/* Cook instructions — moved here from Dietary section per audit */}
        <View style={{ marginBottom: spacing.lg }}>
          <SectionEyebrow>Cook instructions</SectionEyebrow>
          <Text style={{ ...typography.caption, marginBottom: spacing.md }}>
            Standing reminders sent to your cook automatically.
          </Text>

          {cookInstructions.map((inst) => (
            <View
              key={inst.id}
              style={{
                ...cardStyles,
                marginBottom: spacing.sm,
                opacity: inst.status === "paused" ? 0.6 : 1,
              }}
            >
              <View style={{ flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between" }}>
                <View style={{ flex: 1, marginRight: spacing.sm }}>
                  <Text style={typography.bodyBold}>{inst.text}</Text>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.xs, marginTop: spacing.xs, flexWrap: "wrap" }}>
                    {inst.forPerson && (
                      <Text style={{ ...typography.tiny, color: colors.accent.primary }}>For {inst.forPerson}</Text>
                    )}
                    {inst.forPerson && <Text style={{ ...typography.tiny, color: colors.text.muted }}>·</Text>}
                    <Text style={{ ...typography.tiny, color: colors.text.muted }}>
                      {inst.recurrence === "daily" ? "Every day" : inst.recurrence === "weekdays" ? "Weekdays" : inst.recurrence}
                      {inst.time ? ` at ${inst.time}` : ""}
                    </Text>
                    <Text style={{ ...typography.tiny, color: colors.text.muted }}>·</Text>
                    <Text style={{
                      ...typography.tiny,
                      color: inst.status === "active" ? colors.accent.success : colors.text.muted,
                    }}>
                      {inst.status === "active" ? "Active" : "Paused"}
                    </Text>
                  </View>
                </View>
                <View style={{ flexDirection: "row" }}>
                  <RipplePressable
                    onPress={() => {
                      toggleInstructionInStore(inst.id);
                      haptic("selection");
                    }}
                    hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                    accessibilityLabel={inst.status === "active" ? `Pause instruction: ${inst.text}` : `Resume instruction: ${inst.text}`}
                    style={{ minWidth: 44, minHeight: 44, alignItems: "center", justifyContent: "center" }}
                  >
                    <Ionicons
                      name={inst.status === "active" ? "pause-circle-outline" : "play-circle-outline"}
                      size={iconSize.sm}
                      color={colors.text.secondary}
                    />
                  </RipplePressable>
                  <RipplePressable
                    onPress={() => {
                      removeInstructionFromStore(inst.id);
                      haptic("selection");
                    }}
                    hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                    accessibilityLabel={`Delete instruction: ${inst.text}`}
                    style={{ minWidth: 44, minHeight: 44, alignItems: "center", justifyContent: "center" }}
                  >
                    <Ionicons name="trash-outline" size={iconSize.sm} color={colors.accent.danger} />
                  </RipplePressable>
                </View>
              </View>
            </View>
          ))}

          {showAddInstruction ? (
            <View style={{ ...cardStyles, gap: spacing.md }}>
              <Text style={typography.bodyBold}>New instruction</Text>
              <TextInput
                value={newInstructionText}
                onChangeText={setNewInstructionText}
                placeholder='e.g. "Soak almonds at night for Mayank"'
                placeholderTextColor={colors.text.muted}
                accessibilityLabel="Standing instruction for the cook"
                autoCapitalize="sentences"
                style={{ ...inputStyles, borderWidth: 1, borderColor: colors.border.subtle, minHeight: 60 }}
                multiline
              />
              <View>
                <Text style={{ ...typography.tiny, marginBottom: spacing.sm }}>When?</Text>
                <View style={{ flexDirection: "row", gap: spacing.xs, flexWrap: "wrap" }}>
                  {(["daily", "weekdays", "specific_days", "one_time"] as const).map((key) => {
                    const label =
                      key === "daily" ? "Every day" :
                      key === "weekdays" ? "Weekdays" :
                      key === "specific_days" ? "Specific days" : "One time";
                    return (
                      <Pill
                        key={key}
                        tone="primary"
                        active={newInstructionRecurrence === key}
                        onPress={() => setNewInstructionRecurrence(key)}
                      >
                        {label}
                      </Pill>
                    );
                  })}
                </View>
              </View>
              {newInstructionRecurrence === "specific_days" && (
                <View style={{ flexDirection: "row", gap: spacing.xs, flexWrap: "wrap" }}>
                  {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((day) => (
                    <Pill
                      key={day}
                      tone="primary"
                      active={newInstructionDays.includes(day)}
                      onPress={() =>
                        setNewInstructionDays((prev) =>
                          prev.includes(day) ? prev.filter((d) => d !== day) : [...prev, day],
                        )
                      }
                    >
                      {day}
                    </Pill>
                  ))}
                </View>
              )}
              <View style={{ flexDirection: "row", gap: spacing.sm }}>
                <View style={{ flex: 1 }}>
                  <Button
                    variant="primary"
                    size="md"
                    fullWidth
                    onPress={() => {
                      if (!newInstructionText.trim()) return;
                      addInstructionToStore({
                        text: newInstructionText.trim(),
                        forPerson: null,
                        recurrence: newInstructionRecurrence,
                        days: newInstructionRecurrence === "specific_days" ? newInstructionDays : undefined,
                        time: null,
                      });
                      setNewInstructionText("");
                      setNewInstructionRecurrence("daily");
                      setNewInstructionDays([]);
                      setShowAddInstruction(false);
                      haptic("success");
                    }}
                  >
                    Add
                  </Button>
                </View>
                <View style={{ flex: 1 }}>
                  <Button
                    variant="secondary"
                    size="md"
                    fullWidth
                    onPress={() => { setShowAddInstruction(false); setNewInstructionText(""); }}
                  >
                    Cancel
                  </Button>
                </View>
              </View>
            </View>
          ) : (
            <Button
              variant="secondary"
              size="md"
              fullWidth
              leadingIcon="add-circle-outline"
              onPress={() => setShowAddInstruction(true)}
            >
              Add instruction
            </Button>
          )}
        </View>

        {/* Remove cook */}
        <View style={{ alignItems: "center", paddingVertical: spacing.md }}>
          <TextLink onPress={handleRemoveCook} size="md" tone="danger">
            Remove cook
          </TextLink>
        </View>
      </ScrollView>
    </SafeScreen>
  );
}
