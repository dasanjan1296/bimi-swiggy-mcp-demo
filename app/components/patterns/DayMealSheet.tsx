/**
 * DayMealSheet — bottom sheet that lets a user vote on a day's meals
 * (one tap per dish, expand-to-see-3-options inline picker).
 *
 * The voting body is exposed as a separate `DayVotingBody` export so
 * the home calendar's unified `<DayDetailSheet>` can compose it
 * alongside other branches (past-day notes, today-rate prompts, far-
 * future placeholders) inside a single BottomSheet — without nesting
 * sheets or duplicating the vote-row machinery.
 *
 * Per-meal row interaction model:
 *   • Cook present, NOT yet voted → tap row to expand the 3-dish picker.
 *   • Cook present, voted         → tap row to expand a "details"
 *     panel: plate components, vote tally with avatars, alternative
 *     options that lost, prep notes, plus a "Change vote" affordance
 *     that swaps in the picker.
 *   • Cook off (this meal or full day) → row is non-interactive (no
 *     chevron, no expand). The voted dish (if any) is shown as
 *     historical context with a "Self-cooking" / "Off" chip. Voting
 *     here would be misleading because the cook isn't cooking — the
 *     primary action is "Self cook ideas" via the banner.
 *
 * For D+0 (today) and D+1 (tomorrow) the existing voting flow persists
 * votes via the meal store's submitVote/finalizePlan; for D+2..D+6 we
 * route through voteFutureDay (which writes to futureWeekPlans).
 *
 * Implementation note: the bottom sheet is `@gorhom/bottom-sheet` which
 * suppresses raw <Pressable> taps inside its scrollable view. Tappable
 * elements use <RipplePressable> (gesture-handler-based) so taps fire
 * reliably inside the sheet.
 */

import React, { useCallback, useState } from "react";
import { Image, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { useMealStore, useCookAbsenceStore, useHouseholdStore } from "@/lib/store";
import { useAuthStore } from "@/lib/auth-store";
import { isRealAuth } from "@/lib/auth-flags";
import {
  useFinalizePlan,
  usePatchAbsenceFallback,
  usePostCookAbsence,
  useSubmitVote,
} from "@/lib/api";
import { getDishImageByName } from "@/lib/dish-images";
import { resolveDishComponents } from "@/lib/dish-components";
import {
  buildVoteTally,
  classifyMealState,
  explainDecision,
  formatLocalClock,
  minutesUntil,
  type MealLifecycleState,
} from "@/lib/meal-state";
import { Avatar } from "../ui/Avatar";
import { RipplePressable } from "../RipplePressable";
import { BottomSheet } from "../ui/BottomSheet";
import { SelfCookCta } from "../ui/SelfCookCta";
import { StatusChip } from "../ui/StatusChip";
import {
  colors,
  iconSize,
  radius,
  spacing,
  typography,
} from "@/lib/theme";
import type {
  CookAbsenceFallback,
  MealPlan,
  MealSuggestion,
  MealType,
  MealVote,
} from "@/lib/types";
import type { DayCookOff, WeekDay } from "@/lib/use-week-meal-plans";

const MEAL_LABEL: Record<MealType, string> = {
  breakfast: "Breakfast",
  lunch: "Lunch",
  dinner: "Dinner",
  snack: "Snack",
};

const MEAL_ICON: Record<MealType, keyof typeof Ionicons.glyphMap> = {
  breakfast: "sunny-outline",
  lunch: "restaurant-outline",
  dinner: "moon-outline",
  snack: "cafe-outline",
};

export interface DayMealSheetProps {
  visible: boolean;
  onClose: () => void;
  /** Day to render. Pass null when closed. */
  day: WeekDay | null;
  /**
   * Bubble-up callback for the cook-off banner's "Self cook ideas"
   * action. When supplied, the parent typically closes this sheet
   * and opens `<SelfCookSheet>` (the recipe browser) — matching the
   * centre card's behaviour. The banner ALSO commits the `self_cook`
   * fallback before calling this, so the day's absence is resolved
   * the moment the user expresses intent.
   */
  onOpenSelfCookIdeas?: (cookOff: DayCookOff) => void;
}

/**
 * Shell — wraps `<DayVotingBody>` in a BottomSheet with a computed
 * title + subtitle. Exists for any caller that wants the full sheet
 * UX in isolation; the home calendar uses `<DayVotingBody>` directly
 * inside its own unified detail sheet.
 */
export function DayMealSheet({
  visible,
  onClose,
  day,
  onOpenSelfCookIdeas,
}: DayMealSheetProps) {
  if (!day) return null;

  const subtitle = day.cookOff
    ? day.cookOff.isFullDay
      ? `${day.cookOff.absence.cookName} is off all day`
      : `${day.cookOff.absence.cookName} off for ${day.cookOff.affectedMeals
          .map((m) => MEAL_LABEL[m])
          .join(" & ")}`
    : day.voted === day.total
    ? "All set. Tap any meal to change."
    : `${day.voted} of ${day.total} sorted`;

  return (
    <BottomSheet
      visible={visible}
      onClose={onClose}
      title={day.dayLong}
      subtitle={subtitle}
      scrollable
    >
      <DayVotingBody day={day} onOpenSelfCookIdeas={onOpenSelfCookIdeas} />
    </BottomSheet>
  );
}

export interface DayVotingBodyProps {
  /** The week-window day to vote on. */
  day: WeekDay;
  /** Optional cook-off "Self cook ideas" CTA bubble-up. */
  onOpenSelfCookIdeas?: (cookOff: DayCookOff) => void;
  /** Hide the cook-off banner — the parent sheet may already render its own. */
  hideCookOffBanner?: boolean;
}

/**
 * The vote-rows body extracted from the original DayMealSheet so the
 * home calendar's unified DayDetailSheet can compose it inside one
 * BottomSheet alongside other day-state branches.
 */
export function DayVotingBody({
  day,
  onOpenSelfCookIdeas,
  hideCookOffBanner = false,
}: DayVotingBodyProps) {
  const voteFutureDay = useMealStore((s) => s.voteFutureDay);
  const finalizePlan = useMealStore((s) => s.finalizePlan);
  const setActiveMealType = useMealStore((s) => s.setActiveMealType);

  // Backend mutations — called fire-and-forget AFTER the local optimistic
  // update so the UI never blocks on the network round-trip. The next
  // useLiveSync poll reconciles whatever the server returns.
  const familyId = useAuthStore((s) => s.familyId) ?? "";
  const childId = useAuthStore((s) => s.childId);
  const childName = useAuthStore((s) => s.childName);
  const household = useHouseholdStore((s) => s.household);
  const submitVote = useSubmitVote(familyId);
  const finalizeRemote = useFinalizePlan(familyId);

  // Two independent expansion modes per row:
  //   - "details" (default for finalised rows on tap): show plate
  //     components, vote tally, losers, prep notes, "Change vote" CTA.
  //   - "picker" (default for unvoted rows on tap; entered explicitly
  //     from "Change vote" on a voted row): show the 3-dish picker.
  // Tracking the mode per meal type lets a user open the picker on
  // breakfast while inspecting details on lunch.
  type ExpandedMode = "details" | "picker";
  const [expanded, setExpanded] = useState<
    { mealType: MealType; mode: ExpandedMode } | null
  >(null);

  const handleVote = useCallback(
    (mealType: MealType, dishName: string) => {
      // D+0/D+1 still go through the canonical finalize flow because
      // those plans drive the cook-brief and the home hero. D+2..D+6
      // route through voteFutureDay (local optimistic update) but
      // ALSO POST a vote to the backend so the entry shows up in the
      // server-backed meal-history feed on every household device.
      if (day.offset <= 1) {
        setActiveMealType(mealType);
        finalizePlan(dishName, [dishName]);
      } else {
        voteFutureDay(day.date, mealType, dishName);
      }
      // After casting, swap the picker for the freshly-voted details
      // panel so the user immediately sees what they picked.
      setExpanded({ mealType, mode: "details" });

      // Backend persistence — only fires for real auth (skip demo to
      // keep the demo session pure-local and avoid spurious server
      // writes during onboarding).
      if (!isRealAuth() || !familyId) return;

      const memberId = childId ?? "";
      const memberName =
        childName ??
        household?.members.find((m) => m.id === memberId)?.name ??
        "Voter";

      submitVote.mutate({
        member_id: memberId,
        member_name: memberName,
        meal_type: mealType,
        dish_name: dishName,
        rating: 5, // tap-to-pick is a high-signal preference
        meal_date: day.date,
        is_proxy: false,
      });

      if (day.offset <= 1) {
        finalizeRemote.mutate({
          meal_type: mealType,
          dish_name: dishName,
          dishes: [dishName],
          meal_date: day.date,
        });
      }
    },
    [
      day, voteFutureDay, finalizePlan, setActiveMealType,
      familyId, childId, childName, household,
      submitVote, finalizeRemote,
    ],
  );

  return (
    <>
      {!hideCookOffBanner && day.cookOff ? (
        <CookOffBanner
          cookOff={day.cookOff}
          onOpenSelfCookIdeas={onOpenSelfCookIdeas}
        />
      ) : null}

      <View style={{ gap: spacing.md }}>
        {day.plans.map((plan) => {
          const offForThis =
            day.cookOff?.affectedMeals.includes(plan.mealType) ?? false;
          const isExpanded = expanded?.mealType === plan.mealType;
          const mode: ExpandedMode = isExpanded
            ? expanded!.mode
            : plan.selectedMeal
            ? "details"
            : "picker";
          return (
            <MealRow
              key={plan.id}
              plan={plan}
              expanded={isExpanded}
              mode={mode}
              cookOffForThisMeal={offForThis}
              fallbackChosen={day.cookOff?.fallbackChosen ?? null}
              cookOffContext={offForThis ? day.cookOff : null}
              onToggle={() => {
                setExpanded((cur) =>
                  cur?.mealType === plan.mealType
                    ? null
                    : {
                        mealType: plan.mealType,
                        mode: plan.selectedMeal ? "details" : "picker",
                      },
                );
              }}
              onSwitchToPicker={() =>
                setExpanded({ mealType: plan.mealType, mode: "picker" })
              }
              onSwitchToDetails={() =>
                setExpanded({ mealType: plan.mealType, mode: "details" })
              }
              onOpenSelfCookIdeas={
                day.cookOff && onOpenSelfCookIdeas
                  ? () => onOpenSelfCookIdeas(day.cookOff!)
                  : undefined
              }
              onVote={(dish) => handleVote(plan.mealType, dish)}
              householdMembers={household?.members}
            />
          );
        })}
      </View>
    </>
  );
}

// ── Cook-off banner ────────────────────────────────────────────────
// Inline banner for any day with a cook absence. ONE quick-action
// CTA — "Self cook ideas" — that both commits the self_cook fallback
// (so the wheel sector relaxes its amber and the centre card's action
// variant retires) AND opens the `<SelfCookSheet>` recipe browser via
// the parent-supplied callback.
//
// FALLBACK_LABEL maps every `CookAbsenceFallback` value because legacy
// absences in the store may carry the now-retired fallbacks (instacook
// / order_food / replacement_cook / skip from older app versions or
// natural-language parser outputs); we still need to render their
// resolved-state copy correctly.

const FALLBACK_LABEL: Record<CookAbsenceFallback, string> = {
  self_cook: "Self cook",
  order_food: "Ordering food",
  instacook: "Insta Cook booked",
  replacement_cook: "Replacement cook",
  skip: "Skipping",
};

export function CookOffBanner({
  cookOff,
  onOpenSelfCookIdeas,
}: {
  cookOff: DayCookOff;
  onOpenSelfCookIdeas?: (cookOff: DayCookOff) => void;
}) {
  const chooseFallback = useCookAbsenceStore((s) => s.chooseFallback);
  const addAbsence = useCookAbsenceStore((s) => s.addAbsence);
  const swapAbsenceId = useCookAbsenceStore((s) => s.swapAbsenceId);
  const familyId = useAuthStore((s) => s.familyId) ?? "";
  const cook = useHouseholdStore((s) => s.household?.cooks?.[0]) ?? null;
  const postAbsence = usePostCookAbsence(familyId);
  const patchFallback = usePatchAbsenceFallback(familyId);

  // Resolve the local sentinel id (`weekly:cookId:date`) to a real
  // backend UUID by POSTing the materialised absence. Returns the new
  // id so the caller can route a follow-up PATCH at the right row.
  // No-op (returns the existing id) for non-synthetic absences.
  const persistMaterialised = useCallback(async (): Promise<string> => {
    const localId = cookOff.absence.id;
    if (!localId.startsWith("weekly:")) return localId;
    if (!isRealAuth() || !familyId || !cook) return localId;
    try {
      const created = await postAbsence.mutateAsync({
        parentId: cook.id,
        date: cookOff.absence.date,
        endDate: cookOff.absence.endDate,
        affectedMeals: cookOff.absence.affectedMeals,
        reason: cookOff.absence.reason,
      });
      swapAbsenceId(localId, created.id);
      return created.id;
    } catch {
      // Network failure — keep the local sentinel; next 30s
      // useLiveSync poll will reconcile if the backend has the row.
      return localId;
    }
  }, [cookOff.absence, cook, familyId, postAbsence, swapAbsenceId]);

  // Weekly-off absences (e.g. "Sunday") are synthesised on the fly by
  // `buildCookOff` from the cook's `slots[].workingDays` schedule —
  // they aren't yet in the store. The first time the user resolves one
  // (Self cook / Change), we materialise it via `addAbsence` so
  // `chooseFallback` has a real row to update. Subsequent actions on
  // the same date find the now-real absence and behave normally.
  const ensureMaterialised = useCallback(() => {
    const id = cookOff.absence.id;
    if (!id.startsWith("weekly:")) return;
    const inStore = useCookAbsenceStore
      .getState()
      .absences.some((a) => a.id === id);
    if (!inStore) addAbsence(cookOff.absence);
  }, [cookOff.absence, addAbsence]);

  const handleSelfCook = useCallback(async () => {
    Haptics.selectionAsync();
    ensureMaterialised();
    // Optimistic local update so the banner re-renders before the
    // network round-trip. The UI navigates to the recipe browser
    // immediately; the backend POST + PATCH happens in the
    // background and the next sync poll reconciles for other devices.
    chooseFallback(cookOff.absence.id, "self_cook");
    onOpenSelfCookIdeas?.(cookOff);

    if (!isRealAuth() || !familyId) return;
    const realId = await persistMaterialised();
    if (realId !== cookOff.absence.id) {
      // Reflect the swap locally so subsequent renders reference
      // the real id (the chooseFallback above already targeted the
      // local id; the next chooseFallback / change will use the
      // updated one via store reads).
      chooseFallback(realId, "self_cook");
    }
    patchFallback.mutate({ absenceId: realId, fallback: "self_cook" });
  }, [
    chooseFallback,
    cookOff,
    ensureMaterialised,
    familyId,
    onOpenSelfCookIdeas,
    patchFallback,
    persistMaterialised,
  ]);

  // Self-cook recipe browser CTA on the resolved-self-cook variant. Lets
  // the user re-open the browser (and pick another recipe) without
  // having to "Change" first, which would reset the absence to amber.
  const handleBrowseSelfCook = useCallback(() => {
    Haptics.selectionAsync();
    onOpenSelfCookIdeas?.(cookOff);
  }, [cookOff, onOpenSelfCookIdeas]);

  const handleChange = useCallback(async () => {
    // "Change" un-resolves the absence so the banner returns to its
    // amber, action-needed state. Mirrors how the previous three-CTA
    // banner worked: hitting Change put the user back at the picker.
    Haptics.selectionAsync();
    ensureMaterialised();
    chooseFallback(cookOff.absence.id, null);

    if (!isRealAuth() || !familyId) return;
    const realId = await persistMaterialised();
    if (realId !== cookOff.absence.id) {
      chooseFallback(realId, null);
    }
    patchFallback.mutate({ absenceId: realId, fallback: null });
  }, [
    chooseFallback,
    cookOff.absence.id,
    ensureMaterialised,
    familyId,
    patchFallback,
    persistMaterialised,
  ]);

  const isResolved = !!cookOff.fallbackChosen;
  const isSelfCook = cookOff.fallbackChosen === "self_cook";

  return (
    <View
      style={{
        backgroundColor: isResolved
          ? colors.accent.successDim
          : colors.accent.warningDim,
        borderRadius: radius.md,
        borderWidth: 1,
        borderColor: isResolved
          ? colors.accent.success
          : colors.accent.warning,
        padding: spacing.md,
        gap: spacing.sm,
        marginBottom: spacing.lg,
      }}
    >
      <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
        <Ionicons
          name={isResolved ? "checkmark-circle" : "alert-circle-outline"}
          size={iconSize.sm}
          color={isResolved ? colors.accent.success : colors.accent.warning}
        />
        <Text
          style={{
            ...typography.captionBold,
            color: isResolved ? colors.accent.success : colors.accent.warning,
            flex: 1,
          }}
        >
          {isResolved && cookOff.fallbackChosen
            ? FALLBACK_LABEL[cookOff.fallbackChosen]
            : cookOff.isFullDay
            ? "Cook off all day."
            : "Cook off for some meals."}
        </Text>
        {isResolved && (
          <RipplePressable
            onPress={handleChange}
            haptic="selection"
            accessibilityRole="button"
            accessibilityLabel="Change plan"
            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          >
            <Text
              style={{
                ...typography.tinyBold,
                color: colors.accent.success,
                textDecorationLine: "underline",
                letterSpacing: 0.4,
                textTransform: "uppercase",
              }}
            >
              Change
            </Text>
          </RipplePressable>
        )}
      </View>

      {!isResolved && <SelfCookCta onPress={handleSelfCook} />}

      {/* Resolved + self-cook → keep the recipe browser one tap away.
          Without this, the user has to press Change (which un-resolves
          the absence and re-shows the amber state) just to flip through
          ideas, which is jarring. */}
      {isSelfCook && onOpenSelfCookIdeas ? (
        <SelfCookCta onPress={handleBrowseSelfCook} />
      ) : null}
    </View>
  );
}

// ── Per-meal row ────────────────────────────────────────────────────

interface MealRowProps {
  plan: MealPlan;
  expanded: boolean;
  mode: "details" | "picker";
  cookOffForThisMeal: boolean;
  fallbackChosen: CookAbsenceFallback | null;
  cookOffContext: DayCookOff | null;
  onToggle: () => void;
  onSwitchToPicker: () => void;
  onSwitchToDetails: () => void;
  onOpenSelfCookIdeas?: () => void;
  onVote: (dishName: string) => void;
  householdMembers?: { id: string; name: string }[];
}

function MealRow({
  plan,
  expanded,
  mode,
  cookOffForThisMeal,
  fallbackChosen,
  cookOffContext,
  onToggle,
  onSwitchToPicker,
  onSwitchToDetails,
  onOpenSelfCookIdeas,
  onVote,
  householdMembers,
}: MealRowProps) {
  const finalised = !!plan.selectedMeal;
  const top3 = (plan.suggestions ?? []).slice(0, 3);

  // When this meal is off, the row is non-interactive. The voted dish
  // (if any) still renders as historical context — useful so the user
  // can see "we had Rajma Chawal in mind, but the cook is off" — but
  // there's no chevron, no expand, no picker. Action lives in the
  // banner above + the per-row "Recipe ideas" link below.
  const isOff = cookOffForThisMeal;

  // Status chip on the right of the header row.
  //   - Off, fallback=self_cook, voted     → "Self-cooking" amber chip
  //   - Off, fallback=null,       voted    → "OFF" pill
  //   - Off,                      no vote  → "OFF" pill
  //   - Cook on, plan classifier decides   → Locked in / Tentative /
  //                                          "X voted" / null
  const trailingChip = renderTrailingChip({
    plan,
    isOff,
    fallbackChosen,
  });

  const headerInner = (
    <View
      style={{
        flexDirection: "row",
        alignItems: "center",
        paddingVertical: spacing.md,
        paddingHorizontal: spacing.md,
        gap: spacing.md,
      }}
    >
      <View
        style={{
          width: 36,
          height: 36,
          borderRadius: 18,
          backgroundColor: colors.surface.base,
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <Ionicons
          name={MEAL_ICON[plan.mealType]}
          size={iconSize.md}
          color={isOff ? colors.text.muted : colors.text.secondary}
        />
      </View>
      <View style={{ flex: 1 }}>
        <Text
          style={{
            ...typography.smallBold,
            color: colors.text.muted,
            textTransform: "uppercase",
            letterSpacing: 0.6,
          }}
        >
          {MEAL_LABEL[plan.mealType]}
        </Text>
        <Text
          style={{
            ...typography.bodyBold,
            // Off + voted reads as historical, so we mute the dish
            // name; that signals "it WAS the plan, but now context
            // has changed" without erasing the choice entirely.
            color:
              isOff && finalised
                ? colors.text.secondary
                : finalised
                ? colors.text.primary
                : colors.text.secondary,
            marginTop: 1,
          }}
          numberOfLines={1}
        >
          {plan.selectedMeal ?? "Pick a meal"}
        </Text>
      </View>
      {trailingChip}
      {/* Chevron is hidden when the row is non-interactive (off). */}
      {!isOff ? (
        <Ionicons
          name={expanded ? "chevron-up" : "chevron-down"}
          size={iconSize.sm}
          color={colors.text.muted}
        />
      ) : null}
    </View>
  );

  return (
    <View
      style={{
        backgroundColor: colors.surface.card,
        borderRadius: radius.lg,
        overflow: "hidden",
        // Off rows fade slightly so the visual hierarchy reads "this
        // isn't the active decision today".
        opacity: isOff ? 0.85 : 1,
      }}
    >
      {isOff ? (
        // Static header — no ripple, no haptic, no a11y "button" role.
        <View>{headerInner}</View>
      ) : (
        <RipplePressable
          onPress={onToggle}
          haptic="selection"
          accessibilityRole="button"
          accessibilityLabel={`${MEAL_LABEL[plan.mealType]}: ${plan.selectedMeal ?? "Pick a meal"}`}
          accessibilityState={{ expanded }}
          style={{ borderRadius: radius.lg }}
        >
          {headerInner}
        </RipplePressable>
      )}

      {/* Off + voted → quiet "Recipe ideas" inline link so the user
          can act per-meal without scrolling back to the banner. */}
      {isOff && onOpenSelfCookIdeas ? (
        <View style={{ paddingHorizontal: spacing.md, paddingBottom: spacing.md }}>
          <RipplePressable
            onPress={onOpenSelfCookIdeas}
            haptic="selection"
            accessibilityRole="button"
            accessibilityLabel={`Recipe ideas for ${MEAL_LABEL[plan.mealType].toLowerCase()}`}
            hitSlop={{ top: 6, bottom: 6, left: 8, right: 8 }}
            style={{
              flexDirection: "row",
              alignItems: "center",
              gap: 4,
              alignSelf: "flex-start",
            }}
          >
            <Ionicons
              name="bulb-outline"
              size={iconSize.xs}
              color={colors.accent.primary}
            />
            <Text
              style={{
                ...typography.tinyBold,
                color: colors.accent.primary,
                letterSpacing: 0.4,
              }}
            >
              Self-cook ideas for {MEAL_LABEL[plan.mealType].toLowerCase()}
            </Text>
          </RipplePressable>
        </View>
      ) : null}

      {/* Expanded body — only when the row is interactive (i.e. cook is on).
          Branches by mode: "details" for voted rows, "picker" for unvoted. */}
      {expanded && !isOff ? (
        mode === "details" && finalised ? (
          <MealDetailsPanel
            plan={plan}
            top3={top3}
            householdMembers={householdMembers}
            onChangeVote={onSwitchToPicker}
          />
        ) : (
          <MealPickerPanel
            plan={plan}
            top3={top3}
            onVote={onVote}
            onCancelToDetails={finalised ? onSwitchToDetails : undefined}
          />
        )
      ) : null}
    </View>
  );
}

// ── Trailing chip ───────────────────────────────────────────────────

function renderTrailingChip({
  plan,
  isOff,
  fallbackChosen,
}: {
  plan: MealPlan;
  isOff: boolean;
  fallbackChosen: CookAbsenceFallback | null;
}): React.ReactElement | null {
  // Cook-off branch overrides lifecycle — if the cook isn't cooking,
  // the chip shouldn't say "Locked in" no matter how many votes
  // landed.
  if (isOff && plan.selectedMeal && fallbackChosen === "self_cook") {
    return (
      <View
        style={{
          flexDirection: "row",
          alignItems: "center",
          gap: 4,
          paddingHorizontal: spacing.sm,
          paddingVertical: 3,
          borderRadius: radius.pill,
          backgroundColor: colors.accent.warningDim,
          borderWidth: 1,
          borderColor: colors.accent.warning,
        }}
      >
        <Ionicons
          name="flame-outline"
          size={iconSize.xs}
          color={colors.accent.warning}
        />
        <Text
          style={{
            ...typography.tinyBold,
            color: colors.accent.warning,
            letterSpacing: 0.3,
          }}
        >
          Self-cooking
        </Text>
      </View>
    );
  }

  if (isOff) {
    return <MealRowOffPill />;
  }

  // Lifecycle-driven chip — labels match `<DayCardRow>`'s legend so
  // the user reads the same vocabulary on the cell and in the modal.
  const state = classifyMealState(plan);
  if (state === "locked") {
    return <StatusChip status="approved" size="xs" label="Locked in" />;
  }
  if (state === "tentative") {
    return (
      <View
        style={{
          flexDirection: "row",
          alignItems: "center",
          gap: 4,
          paddingHorizontal: spacing.sm,
          paddingVertical: 3,
          borderRadius: radius.pill,
          backgroundColor: colors.accent.warningDim,
          borderWidth: 1,
          borderColor: colors.accent.warning,
        }}
      >
        <Ionicons
          name="hourglass-outline"
          size={iconSize.xs}
          color={colors.accent.warning}
        />
        <Text
          style={{
            ...typography.tinyBold,
            color: colors.accent.warning,
            letterSpacing: 0.3,
          }}
        >
          Tentative
        </Text>
      </View>
    );
  }
  if (state === "voting") {
    const cast = plan.votes.filter((v) => !v.skipped).length;
    return (
      <View
        style={{
          flexDirection: "row",
          alignItems: "center",
          gap: 4,
          paddingHorizontal: spacing.sm,
          paddingVertical: 3,
          borderRadius: radius.pill,
          backgroundColor: colors.surface.base,
          borderWidth: 1,
          borderColor: colors.border.subtle,
        }}
      >
        <Ionicons
          name="people-outline"
          size={iconSize.xs}
          color={colors.text.secondary}
        />
        <Text
          style={{
            ...typography.tinyBold,
            color: colors.text.secondary,
            letterSpacing: 0.3,
          }}
        >
          {cast} voted
        </Text>
      </View>
    );
  }

  return null;
}

// ── Picker panel (unvoted, or "Change vote" branch) ─────────────────

function MealPickerPanel({
  plan,
  top3,
  onVote,
  onCancelToDetails,
}: {
  plan: MealPlan;
  top3: MealSuggestion[];
  onVote: (dishName: string) => void;
  onCancelToDetails?: () => void;
}) {
  if (top3.length === 0) {
    return (
      <View style={{ paddingHorizontal: spacing.md, paddingBottom: spacing.md }}>
        <Text style={{ ...typography.caption, color: colors.text.muted }}>
          No suggestions yet — Bimi will fill these in soon.
        </Text>
      </View>
    );
  }

  return (
    <View
      style={{
        paddingHorizontal: spacing.md,
        paddingBottom: spacing.md,
        gap: spacing.sm,
      }}
    >
      <View
        style={{
          flexDirection: "row",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <Text style={{ ...typography.tiny, color: colors.text.muted }}>
          Tap a dish to vote
        </Text>
        {onCancelToDetails ? (
          <RipplePressable
            onPress={onCancelToDetails}
            haptic="selection"
            accessibilityRole="button"
            accessibilityLabel={`Keep ${plan.selectedMeal}`}
            hitSlop={{ top: 6, bottom: 6, left: 8, right: 8 }}
          >
            <Text
              style={{
                ...typography.tinyBold,
                color: colors.text.secondary,
                letterSpacing: 0.4,
              }}
            >
              Cancel
            </Text>
          </RipplePressable>
        ) : null}
      </View>
      <View
        style={{
          flexDirection: "row",
          gap: spacing.sm,
        }}
      >
        {top3.map((suggestion) => (
          <DishMiniCard
            key={suggestion.id}
            dishName={suggestion.dishName}
            isSelected={
              plan.selectedMeal?.toLowerCase() ===
              suggestion.dishName.toLowerCase()
            }
            onPress={() => onVote(suggestion.dishName)}
          />
        ))}
      </View>
    </View>
  );
}

// ── Details panel (voted row inspection) ────────────────────────────

function MealDetailsPanel({
  plan,
  top3,
  householdMembers: _householdMembers,
  onChangeVote,
}: {
  plan: MealPlan;
  top3: MealSuggestion[];
  householdMembers?: { id: string; name: string }[];
  onChangeVote: () => void;
}) {
  // Read the full household directly so we have `role` (needed for
  // hierarchical-mode decision attribution) and `votingMode` without
  // having to thread them down from the calendar.
  const household = useHouseholdStore((s) => s.household);
  const activeMembers = (household?.members ?? []).filter((m) => m.isActive);
  const votingMode = household?.config?.votingMode;

  const selectedSuggestion =
    top3.find(
      (s) => s.dishName.toLowerCase() === plan.selectedMeal!.toLowerCase(),
    ) ?? null;

  // Plate components — hand-curated lookup for popular dishes, with
  // graceful fallback to the raw ingredient list. Empty array → hide
  // the section entirely.
  const components = resolveDishComponents(
    plan.selectedMeal,
    selectedSuggestion?.ingredients,
  );

  // Vote tally (used in two places: the "How it was decided" headline
  // copy below, and the per-dish "Household votes" section further
  // down).
  const realVotes = plan.votes.filter((v) => !v.skipped);
  const votesByDish = new Map<string, MealVote[]>();
  for (const v of realVotes) {
    const arr = votesByDish.get(v.dishName) ?? [];
    arr.push(v);
    votesByDish.set(v.dishName, arr);
  }

  // Lifecycle classification drives both the headline ("Locked in" /
  // "Tentative · 4 min") and the muted explainer ("Majority pick — 2
  // of 3 voted Dal Tadka"). The combination tells the user WHAT the
  // system decided and HOW it got there.
  const lifecycle: MealLifecycleState = classifyMealState(plan);
  const decisionExplanation = explainDecision(plan, votingMode, activeMembers);
  const lockTimeLabel = formatLocalClock(plan.lockInAt);
  const minutesLeft = minutesUntil(plan.lockInAt);

  // Other suggestions that didn't win — useful context for "we
  // considered Khichdi too" rather than a void.
  const losers = top3.filter(
    (s) => s.dishName.toLowerCase() !== plan.selectedMeal!.toLowerCase(),
  );

  // Prep notes — surface advance-prep notes (overnight soaks, etc) so
  // the household isn't surprised at 6 PM.
  const advancePrep = selectedSuggestion?.advancePrepNote;
  const noteForCook = selectedSuggestion?.noteForCook;
  const prepTime = selectedSuggestion?.prepTime;

  return (
    <View
      style={{
        paddingHorizontal: spacing.md,
        paddingBottom: spacing.md,
        gap: spacing.md,
      }}
    >
      {/* Section 1 (anchor): how the system arrived at this dish.
          Renders FIRST because the user's question on opening a voted
          meal is "is this really what we're eating?" — the lifecycle
          headline + decision explanation answers that before the
          deeper details (plate, votes, prep) load below. */}
      <DecisionHeadline
        lifecycle={lifecycle}
        explanation={decisionExplanation}
        lockTimeLabel={lockTimeLabel}
        minutesLeft={minutesLeft}
        winnerVoteCount={
          votesByDish.get(plan.selectedMeal!.toLowerCase())?.length ??
          (plan.votes.find(
            (v) => v.dishName.toLowerCase() === plan.selectedMeal!.toLowerCase(),
          )
            ? 1
            : 0)
        }
        totalActiveMembers={activeMembers.length}
      />

      {/* Section: what's on the plate. Always-on when components > 0. */}
      {components.length > 0 ? (
        <DetailSection
          icon="restaurant-outline"
          label="On the plate"
        >
          <View
            style={{
              flexDirection: "row",
              flexWrap: "wrap",
              gap: spacing.xs,
            }}
          >
            {components.map((c) => (
              <View
                key={c}
                style={{
                  paddingHorizontal: spacing.sm,
                  paddingVertical: 4,
                  borderRadius: radius.pill,
                  backgroundColor: colors.surface.base,
                  borderWidth: 1,
                  borderColor: colors.border.subtle,
                }}
              >
                <Text
                  style={{
                    ...typography.small,
                    color: colors.text.primary,
                  }}
                >
                  {c}
                </Text>
              </View>
            ))}
          </View>
        </DetailSection>
      ) : null}

      {/* Section: who voted what. */}
      {realVotes.length > 0 ? (
        <DetailSection icon="people-outline" label="Household votes">
          <View style={{ gap: spacing.xs }}>
            {Array.from(votesByDish.entries()).map(([dish, votes]) => (
              <View
                key={dish}
                style={{
                  flexDirection: "row",
                  alignItems: "center",
                  gap: spacing.sm,
                }}
              >
                <View style={{ flexDirection: "row", marginRight: 4 }}>
                  {votes.slice(0, 3).map((v, i) => (
                    <View
                      key={v.memberId + i}
                      style={{ marginLeft: i === 0 ? 0 : -6 }}
                    >
                      <Avatar
                        id={v.memberId}
                        name={v.memberName}
                        size="xs"
                      />
                    </View>
                  ))}
                </View>
                <Text
                  style={{
                    ...typography.small,
                    color: colors.text.primary,
                    flex: 1,
                  }}
                  numberOfLines={1}
                >
                  <Text style={{ fontWeight: "600" }}>
                    {votes.map((v) => v.memberName.split(" ")[0]).join(", ")}
                  </Text>
                  {" · "}
                  <Text style={{ color: colors.text.secondary }}>{dish}</Text>
                </Text>
              </View>
            ))}
          </View>
        </DetailSection>
      ) : null}

      {/* Section: alternatives that were on the table. */}
      {losers.length > 0 ? (
        <DetailSection icon="swap-horizontal-outline" label="Other options">
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.xs }}>
            {losers.map((s) => (
              <View
                key={s.id}
                style={{
                  paddingHorizontal: spacing.sm,
                  paddingVertical: 4,
                  borderRadius: radius.pill,
                  backgroundColor: colors.surface.base,
                  borderWidth: 1,
                  borderColor: colors.border.subtle,
                }}
              >
                <Text
                  style={{
                    ...typography.small,
                    color: colors.text.secondary,
                  }}
                >
                  {s.dishName}
                </Text>
              </View>
            ))}
          </View>
        </DetailSection>
      ) : null}

      {/* Section: prep notes — advance prep + cook note + total time. */}
      {advancePrep || noteForCook || prepTime ? (
        <DetailSection icon="time-outline" label="Prep">
          <View style={{ gap: 4 }}>
            {prepTime ? (
              <DetailLine icon="hourglass-outline" text={`${prepTime} hands-on time`} />
            ) : null}
            {advancePrep ? (
              <DetailLine icon="moon-outline" text={advancePrep} tone="warning" />
            ) : null}
            {noteForCook ? (
              <DetailLine icon="chatbubble-outline" text={noteForCook} />
            ) : null}
          </View>
        </DetailSection>
      ) : null}

      {/* Change vote — single secondary CTA at the bottom of the panel. */}
      <RipplePressable
        onPress={onChangeVote}
        haptic="selection"
        accessibilityRole="button"
        accessibilityLabel={`Change vote for ${plan.selectedMeal}`}
        style={{
          marginTop: spacing.xs,
          flexDirection: "row",
          alignItems: "center",
          justifyContent: "center",
          gap: spacing.xs,
          paddingVertical: spacing.sm,
          borderRadius: radius.sm,
          borderWidth: 1,
          borderColor: colors.border.subtle,
          backgroundColor: colors.surface.base,
        }}
      >
        <Ionicons
          name="swap-horizontal"
          size={iconSize.sm}
          color={colors.text.primary}
        />
        <Text
          style={{ ...typography.smallBold, color: colors.text.primary }}
        >
          Change vote
        </Text>
      </RipplePressable>
    </View>
  );
}

// ── Decision headline ───────────────────────────────────────────────
// Sits at the top of `MealDetailsPanel`. Two lines:
//   1. Lifecycle headline — "Locked in" / "Tentative · 4 min left" /
//      "Picked tentatively" — uses bold tone.
//   2. Quiet explainer — "Majority pick — 2 of 3 voted Dal Tadka" /
//      "Cook briefed at 7:30 PM" — secondary text.
// Renders with a soft accent-tinted background so it reads as the
// "anchor" of the panel — answering the user's first question
// ("is this really the system's choice?") before the details.

function DecisionHeadline({
  lifecycle,
  explanation,
  lockTimeLabel,
  minutesLeft,
  winnerVoteCount,
  totalActiveMembers,
}: {
  lifecycle: MealLifecycleState;
  explanation: string;
  lockTimeLabel: string | null;
  minutesLeft: number | null;
  winnerVoteCount: number;
  totalActiveMembers: number;
}) {
  const isLocked = lifecycle === "locked";
  const isTentative = lifecycle === "tentative";

  // Color story:
  //   - locked    → success (cool green)
  //   - tentative → warning (amber)
  //   - voting    → neutral surface
  //   - open      → don't render this headline at all (caller hides)
  const tone = isLocked
    ? {
        bg: colors.accent.successDim,
        fg: colors.accent.success,
        border: colors.accent.success,
        icon: "lock-closed" as const,
      }
    : isTentative
    ? {
        bg: colors.accent.warningDim,
        fg: colors.accent.warning,
        border: colors.accent.warning,
        icon: "hourglass-outline" as const,
      }
    : {
        bg: colors.surface.card,
        fg: colors.text.secondary,
        border: colors.border.subtle,
        icon: "people-outline" as const,
      };

  // Headline copy mirrors the cell legend so the user reads the same
  // vocabulary on both surfaces.
  const headline = (() => {
    if (isLocked) return "Locked in";
    if (isTentative) {
      if (minutesLeft != null && minutesLeft > 0) {
        return `Tentative · ${minutesLeft} min to switch`;
      }
      if (lockTimeLabel) return `Tentative · locks at ${lockTimeLabel}`;
      return "Tentative";
    }
    if (lifecycle === "voting") {
      if (totalActiveMembers > 0) {
        return `Voting · ${winnerVoteCount} of ${totalActiveMembers} voted`;
      }
      return "Voting open";
    }
    return "Picked";
  })();

  // Sub-line. Locked + lockInAt → "Cook briefed at 7:30 PM". For
  // future days (no lockInAt), drop the time and just show the
  // explanation.
  const subline = (() => {
    if (isLocked && lockTimeLabel) {
      return explanation
        ? `${explanation} · cook briefed at ${lockTimeLabel}`
        : `Cook briefed at ${lockTimeLabel}`;
    }
    return explanation || "Picked by household";
  })();

  return (
    <View
      style={{
        backgroundColor: tone.bg,
        borderRadius: radius.md,
        borderWidth: 1,
        borderColor: tone.border,
        paddingHorizontal: spacing.md,
        paddingVertical: spacing.sm,
        gap: 2,
      }}
    >
      <View
        style={{
          flexDirection: "row",
          alignItems: "center",
          gap: spacing.xs,
        }}
      >
        <Ionicons name={tone.icon} size={iconSize.sm} color={tone.fg} />
        <Text
          style={{
            ...typography.bodyBold,
            color: tone.fg,
            flex: 1,
          }}
        >
          {headline}
        </Text>
      </View>
      {subline ? (
        <Text
          style={{
            ...typography.tiny,
            color: isLocked || isTentative ? tone.fg : colors.text.secondary,
            marginLeft: iconSize.sm + spacing.xs,
            opacity: 0.85,
          }}
        >
          {subline}
        </Text>
      ) : null}
    </View>
  );
}

function DetailSection({
  icon,
  label,
  children,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <View style={{ gap: spacing.xs }}>
      <View
        style={{
          flexDirection: "row",
          alignItems: "center",
          gap: 4,
        }}
      >
        <Ionicons
          name={icon}
          size={iconSize.xs}
          color={colors.text.muted}
        />
        <Text
          style={{
            ...typography.tinyBold,
            color: colors.text.muted,
            textTransform: "uppercase",
            letterSpacing: 0.6,
          }}
        >
          {label}
        </Text>
      </View>
      {children}
    </View>
  );
}

function DetailLine({
  icon,
  text,
  tone,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  text: string;
  tone?: "warning";
}) {
  return (
    <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
      <Ionicons
        name={icon}
        size={iconSize.xs}
        color={tone === "warning" ? colors.accent.warning : colors.text.muted}
      />
      <Text
        style={{
          ...typography.small,
          color: tone === "warning" ? colors.accent.warning : colors.text.secondary,
          flex: 1,
        }}
      >
        {text}
      </Text>
    </View>
  );
}

// ── Initials fallback ─────────────────────────────────────────────────
// Common dishes (Chole Bhature, Khichdi, Dal Tadka, etc.) aren't yet in
// `lib/dish-images.ts`. Render a designed avatar in their place so the
// picker doesn't look like missing-asset slots.

function hashStr(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}

function MealRowOffPill() {
  return (
    <View
      style={{
        paddingHorizontal: spacing.sm,
        paddingVertical: 2,
        borderRadius: 999,
        backgroundColor: colors.accent.warningDim,
        borderWidth: 1,
        borderColor: colors.accent.warning,
      }}
    >
      <Text
        style={{
          ...typography.tinyBold,
          color: colors.accent.warning,
          letterSpacing: 0.5,
          textTransform: "uppercase",
        }}
      >
        Off
      </Text>
    </View>
  );
}

function dishInitials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

function tintForDish(name: string): { bg: string; fg: string } {
  const palette = colors.persons;
  const fg = palette[hashStr(name) % palette.length];
  // Convert the foreground hex to a low-opacity background — same hue,
  // softer surface — using inline rgba math so we don't rely on a util.
  const hex = fg.replace("#", "");
  const r = parseInt(hex.substring(0, 2), 16);
  const g = parseInt(hex.substring(2, 4), 16);
  const b = parseInt(hex.substring(4, 6), 16);
  return { bg: `rgba(${r},${g},${b},0.16)`, fg };
}

function DishMiniCard({
  dishName,
  isSelected,
  onPress,
}: {
  dishName: string;
  isSelected?: boolean;
  onPress: () => void;
}) {
  const image = getDishImageByName(dishName);
  return (
    <RipplePressable
      onPress={onPress}
      haptic="selection"
      accessibilityRole="button"
      accessibilityLabel={`Vote for ${dishName}`}
      accessibilityState={{ selected: isSelected }}
      style={{
        flex: 1,
        borderRadius: radius.md,
        overflow: "hidden",
        backgroundColor: colors.surface.base,
        // Selected card gets a subtle Rausch outline so the user knows
        // which dish they're currently voted for during the "Change
        // vote" branch.
        borderWidth: isSelected ? 1.5 : 0,
        borderColor: isSelected ? colors.accent.primary : "transparent",
      }}
    >
      <View style={{ aspectRatio: 1 }}>
        {image ? (
          <Image
            source={image}
            style={{ width: "100%", height: "100%" }}
            resizeMode="cover"
          />
        ) : (
          <DishInitialsBlock name={dishName} />
        )}
      </View>
      <View style={{ padding: spacing.sm }}>
        <Text
          style={{ ...typography.smallBold, color: colors.text.primary }}
          numberOfLines={2}
        >
          {dishName}
        </Text>
      </View>
    </RipplePressable>
  );
}

function DishInitialsBlock({ name }: { name: string }) {
  const tint = tintForDish(name);
  return (
    <View
      style={{
        flex: 1,
        backgroundColor: tint.bg,
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <Text
        style={{
          ...typography.h2,
          color: tint.fg,
          fontWeight: "700",
        }}
      >
        {dishInitials(name)}
      </Text>
    </View>
  );
}
