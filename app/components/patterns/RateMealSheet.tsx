/**
 * RateMealSheet — multi-meal star-rating sheet for a single day, with
 * an optional pencil-icon notes flow per row.
 *
 * Opens when the home centre card's status reads "Rate meals" and the
 * user taps it. Surfaces ALL of the day's meals as separate rows so a
 * user with two unrated meals (e.g., breakfast + lunch at 4 PM) can
 * close them out in one trip rather than rating, watching the centre
 * card cycle, and rating again.
 *
 * Per-row state machine:
 *   • Past + selectedMeal + unrated → live 5-star input, default 0.
 *   • Past + selectedMeal + already rated → live, default to current
 *     rating (so the user can adjust).
 *   • Future + selectedMeal → grayed/disabled stars, "Coming up at
 *     HH:MM" subtitle so the user knows the meal hasn't happened yet.
 *   • Past + no selectedMeal → grayed, "Skipped" subtitle.
 *   • Future + no selectedMeal → grayed, "Yet to plan · HH:MM".
 *
 * Iterates `day.plans` directly so households configured for 2 / 3 /
 * 4 meals all render correctly without a hardcoded breakfast/lunch/
 * dinner list.
 *
 * Notes flow (rateable rows only):
 *   • Pencil icon next to the stars toggles an inline expand.
 *   • Expanded row shows a multi-line TextInput placeholder
 *     "Tip for the cook? (optional)".
 *   • Save persists the rating AND any non-empty note to the
 *     dish_notes table via `useCreateDishNote`. Notes get bundled
 *     into the cook's next morning WhatsApp brief by the backend
 *     `_send_cook_morning_briefing` task.
 *
 * Save semantics: collects every row whose rating differs from the
 * initial value AND is non-zero, calls `useMealStore.rateMeal()` for
 * each. Notes are persisted via the dish-notes mutation in parallel.
 * Disabled iff nothing dirty (no rating change AND no new note).
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Text, TextInput, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { useMealStore, useHouseholdStore } from "@/lib/store";
import { useAuthStore } from "@/lib/auth-store";
import { defaultMealTime } from "@/lib/meal-times";
import { RipplePressable } from "../RipplePressable";
import { BottomSheet } from "../ui/BottomSheet";
import { Button } from "../ui/Button";
import { toast } from "@/lib/toast";
import { useCreateDishNote } from "@/lib/use-dish-notes";
import { useRateMeal } from "@/lib/use-meal-history";
import { isRealAuth } from "@/lib/auth-flags";
import {
  colors,
  iconSize,
  inputStyles,
  radius,
  spacing,
  typography,
} from "@/lib/theme";
import type { MealPlan, MealType } from "@/lib/types";
import type { WeekDay } from "@/lib/use-week-meal-plans";

const MEAL_LABEL: Record<MealType, string> = {
  breakfast: "Breakfast",
  lunch: "Lunch",
  dinner: "Dinner",
  snack: "Snack",
};

// Meal-time windows (mirrors WheelOfMeals.tsx). Used to classify each
// plan as past / now / future relative to the wall-clock hour. Lifted
// inline rather than imported because the wheel keeps these locally
// scoped; if a third surface ever needs them, promote to a shared
// `lib/meal-time-windows.ts` module.
const MEAL_BOUNDARIES: Record<MealType, [number, number]> = {
  breakfast: [5, 11],
  lunch: [10, 16],
  dinner: [15, 23],
  snack: [0, 24],
};

function classifyMealTime(mealType: MealType, hour: number): "past" | "now" | "future" {
  const [start, end] = MEAL_BOUNDARIES[mealType];
  if (hour >= end) return "past";
  if (hour < start) return "future";
  return "now";
}

type RatingsMap = Record<string, number>;
type NotesMap = Record<string, string>;
type ExpandedMap = Record<string, boolean>;

export interface RateMealSheetProps {
  visible: boolean;
  onClose: () => void;
  /** Day whose plans to render. Pass null when closed. */
  day: WeekDay | null;
}

export function RateMealSheet({ visible, onClose, day }: RateMealSheetProps) {
  const rateMeal = useMealStore((s) => s.rateMeal);
  const createDishNote = useCreateDishNote();
  // Server-keyed rating mutation. Replaces the legacy local-id POST
  // /meals/{plan_id}/feedback that always 404'd because the FE only
  // had local mock ids; this one keys on (family, date, meal_type,
  // dish, member) so the server can find or create the right row.
  const rateMealRemote = useRateMeal();

  // Author identity for the dish-note byline. Mirrors the SelfCookSheet
  // "Saved by …" attribution: prefer the explicit auth-store child id,
  // fall back to the first active household member, fall back to a
  // safe placeholder.
  const household = useHouseholdStore((s) => s.household);
  const childId = useAuthStore((s) => s.childId);
  const authName = useAuthStore((s) => s.childName);
  const familyId = household?.id;
  const authorName = (() => {
    if (!household) return authName || undefined;
    const member =
      household.members.find((m) => m.id === childId) ??
      household.members.find((m) => m.isActive);
    return member?.name || authName || undefined;
  })();

  // Local rating drafts and the initial snapshot we diff against. Two
  // maps so we can compute "is row dirty" cheaply and only persist
  // values the user actually changed.
  const [ratings, setRatings] = useState<RatingsMap>({});
  const [initialRatings, setInitialRatings] = useState<RatingsMap>({});
  // Note draft per planId. Empty string means "no note" (we only
  // persist non-empty notes). Initialised empty on every open — the
  // user explicitly types into the box if they want to leave a note.
  const [notes, setNotes] = useState<NotesMap>({});
  // Which rows have their note text-box expanded.
  const [expandedNotes, setExpandedNotes] = useState<ExpandedMap>({});

  // Reset every time the sheet opens for a different day, so a half-
  // edited draft from a previous open doesn't leak through.
  useEffect(() => {
    if (!visible || !day) return;
    const seed: RatingsMap = {};
    for (const p of day.plans) seed[p.id] = p.rating ?? 0;
    setRatings(seed);
    setInitialRatings(seed);
    setNotes({});
    setExpandedNotes({});
  }, [visible, day?.date, day?.plans]);

  const dirtyRatingCount = useMemo(() => {
    let n = 0;
    for (const id of Object.keys(ratings)) {
      const v = ratings[id];
      const init = initialRatings[id] ?? 0;
      if (v !== init && v > 0) n++;
    }
    return n;
  }, [ratings, initialRatings]);

  const newNoteCount = useMemo(
    () => Object.values(notes).filter((t) => t.trim().length > 0).length,
    [notes],
  );

  const isDirty = dirtyRatingCount > 0 || newNoteCount > 0;

  const handleRate = useCallback((planId: string, value: number) => {
    setRatings((prev) => ({ ...prev, [planId]: value }));
    Haptics.selectionAsync();
  }, []);

  const handleNoteChange = useCallback((planId: string, text: string) => {
    setNotes((prev) => ({ ...prev, [planId]: text }));
  }, []);

  const handleToggleNote = useCallback((planId: string) => {
    Haptics.selectionAsync();
    setExpandedNotes((prev) => ({ ...prev, [planId]: !prev[planId] }));
  }, []);

  const handleSave = useCallback(async () => {
    if (!day || !isDirty) return;

    // Resolve member identity for the backend rating call. Falls
    // back through the same chain as the dish-note byline so a
    // rating without a clean auth context still attributes to a
    // sensible member id.
    const memberId =
      childId ??
      household?.members.find((m) => m.isActive)?.id ??
      "";
    const memberName = authorName ?? "Voter";

    let savedRatings = 0;
    for (const p of day.plans) {
      const next = ratings[p.id] ?? 0;
      const init = initialRatings[p.id] ?? 0;
      if (next !== init && next > 0) {
        // Local optimistic update — keeps the wheel/home indicators in
        // sync without waiting on the network round-trip.
        rateMeal(p.id, next);
        savedRatings++;

        // Server-keyed mutation. Fire-and-forget; on success it
        // invalidates ["meal-history", familyId] which causes the
        // calendar + past-day modal to pick up the new rating on the
        // next render. Skipped for the demo session.
        if (isRealAuth() && familyId && p.selectedMeal) {
          rateMealRemote.mutate({
            familyId,
            memberId,
            memberName,
            mealDate: day.date,
            mealType: p.mealType,
            dishName: p.selectedMeal,
            rating: next,
          });
        }
      }
    }

    // Persist notes in parallel. Notes are best-effort: if a single
    // note POST fails (network blip, validation), we still succeed
    // overall and surface a softer toast. The cook-brief integration
    // reads via the same family_id so any note that DID land will
    // show up tomorrow morning regardless.
    let savedNotes = 0;
    if (familyId && authorName) {
      const notePromises: Promise<unknown>[] = [];
      for (const p of day.plans) {
        const text = (notes[p.id] ?? "").trim();
        if (!text || !p.selectedMeal) continue;
        notePromises.push(
          createDishNote
            .mutateAsync({
              familyId,
              authorName,
              dishName: p.selectedMeal,
              mealType: p.mealType,
              sourceDate: day.date,
              noteText: text,
            })
            .then(() => {
              savedNotes++;
            })
            .catch(() => {
              // Swallowed — see comment above.
            }),
        );
      }
      await Promise.all(notePromises);
    }

    if (savedRatings > 0 || savedNotes > 0) {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      toast.success(
        composeToastTitle(savedRatings, savedNotes),
        savedNotes > 0
          ? "We'll pass your notes to the cook in tomorrow's brief."
          : "Thanks for the feedback.",
      );
    }
    onClose();
  }, [
    day,
    isDirty,
    ratings,
    initialRatings,
    notes,
    rateMeal,
    createDishNote,
    familyId,
    authorName,
    onClose,
  ]);

  if (!day) return null;

  const hour = new Date().getHours();
  const unratedCount = day.plans.filter(
    (p) =>
      classifyMealTime(p.mealType, hour) === "past" &&
      !!p.selectedMeal &&
      !p.rating,
  ).length;

  // Subtitle adapts. With unrated meals, lead with the count so the
  // user knows what they're being asked. Once everything past is
  // already rated (re-opening to adjust), drop to a calmer prompt.
  const subtitle =
    unratedCount > 0
      ? unratedCount === 1
        ? "1 unrated meal · tap stars to rate"
        : `${unratedCount} unrated meals · tap stars to rate`
      : "Tap a row to adjust.";

  const dayLabel =
    day.offset === 0
      ? "Today's meals"
      : day.offset === 1
      ? "Tomorrow's meals"
      : `${day.dayLong}'s meals`;

  return (
    <BottomSheet
      visible={visible}
      onClose={onClose}
      title={dayLabel}
      subtitle={subtitle}
      maxHeightFraction={0.9}
      scrollable
    >
      {/* Body padding is explicit paddingTop so the BottomSheet's
          `paddingTop: 0`-when-title-set behaviour doesn't crowd the
          first row up against the header. */}
      <View style={{ paddingTop: spacing.lg, paddingBottom: spacing.lg, gap: spacing.lg }}>
        {day.plans.map((plan) => (
          <MealRatingRow
            key={plan.id}
            plan={plan}
            hour={hour}
            rating={ratings[plan.id] ?? 0}
            onRate={(value) => handleRate(plan.id, value)}
            note={notes[plan.id] ?? ""}
            onNoteChange={(text) => handleNoteChange(plan.id, text)}
            isNoteExpanded={!!expandedNotes[plan.id]}
            onToggleNote={() => handleToggleNote(plan.id)}
            canTakeNotes={!!familyId}
          />
        ))}

        <View style={{ paddingHorizontal: spacing.md, marginTop: spacing.sm }}>
          <Button
            variant="primary"
            size="md"
            onPress={handleSave}
            disabled={!isDirty || createDishNote.isPending}
            loading={createDishNote.isPending}
            fullWidth
          >
            {composeSaveLabel(dirtyRatingCount, newNoteCount)}
          </Button>
        </View>
      </View>
    </BottomSheet>
  );
}

function composeSaveLabel(ratings: number, notes: number): string {
  if (ratings === 0 && notes === 0) return "Save";
  if (ratings > 0 && notes === 0) {
    return ratings === 1 ? "Save 1 rating" : `Save ${ratings} ratings`;
  }
  if (ratings === 0 && notes > 0) {
    return notes === 1 ? "Save 1 note" : `Save ${notes} notes`;
  }
  return `Save ${ratings} rating${ratings === 1 ? "" : "s"} + ${notes} note${notes === 1 ? "" : "s"}`;
}

function composeToastTitle(ratings: number, notes: number): string {
  if (ratings > 0 && notes === 0) return ratings === 1 ? "Rating saved" : `${ratings} ratings saved`;
  if (ratings === 0 && notes > 0) return notes === 1 ? "Note saved" : `${notes} notes saved`;
  return "Saved";
}

// ── Per-meal row ─────────────────────────────────────────────────────

function MealRatingRow({
  plan,
  hour,
  rating,
  onRate,
  note,
  onNoteChange,
  isNoteExpanded,
  onToggleNote,
  canTakeNotes,
}: {
  plan: MealPlan;
  hour: number;
  rating: number;
  onRate: (value: number) => void;
  note: string;
  onNoteChange: (text: string) => void;
  isNoteExpanded: boolean;
  onToggleNote: () => void;
  canTakeNotes: boolean;
}) {
  const when = classifyMealTime(plan.mealType, hour);
  const hasMeal = !!plan.selectedMeal;
  const isRateable = when === "past" && hasMeal;

  // Row-state subtitle. Past + meal = the dish name (rateable). Future
  // = "<dish> · Coming up at HH:MM" (or "Yet to plan · HH:MM" without
  // a dish). Past + no meal = "Skipped". The grayed state is a single
  // visual signal: subtitle in muted text + stars rendered disabled.
  let subtitle: string;
  if (when === "past" && hasMeal) {
    subtitle = plan.selectedMeal!;
  } else if (when === "future" && hasMeal) {
    subtitle = `${plan.selectedMeal} · Coming up at ${defaultMealTime(plan.mealType)}`;
  } else if (when === "future" && !hasMeal) {
    subtitle = `Yet to plan · ${defaultMealTime(plan.mealType)}`;
  } else if (when === "past" && !hasMeal) {
    subtitle = "Skipped";
  } else {
    // when === "now"
    subtitle = hasMeal
      ? `${plan.selectedMeal} · In progress`
      : "Yet to plan";
  }

  // Pencil-affordance is only meaningful on rateable rows AND when we
  // have a household to attribute the note to. Hidden otherwise so the
  // row stays calm.
  const showPencil = isRateable && canTakeNotes;

  return (
    <View
      style={{
        paddingHorizontal: spacing.md,
        gap: spacing.xs,
        opacity: isRateable ? 1 : 0.55,
      }}
    >
      <Text
        style={{
          ...typography.tinyBold,
          color: colors.text.muted,
          textTransform: "uppercase",
          letterSpacing: 0.6,
        }}
      >
        {MEAL_LABEL[plan.mealType]}
      </Text>
      <Text
        style={{
          ...typography.body,
          color: isRateable ? colors.text.primary : colors.text.secondary,
        }}
        numberOfLines={1}
      >
        {subtitle}
      </Text>

      <View
        style={{
          flexDirection: "row",
          alignItems: "center",
          justifyContent: "space-between",
          marginTop: 2,
        }}
      >
        <StarRow
          value={rating}
          disabled={!isRateable}
          onRate={onRate}
          accessibilityLabel={`Rate ${MEAL_LABEL[plan.mealType].toLowerCase()}${
            plan.selectedMeal ? ` (${plan.selectedMeal})` : ""
          }`}
        />

        {showPencil ? (
          <RipplePressable
            onPress={onToggleNote}
            haptic="selection"
            accessibilityRole="button"
            accessibilityLabel={
              isNoteExpanded
                ? "Hide note input"
                : "Add a note for the cook"
            }
            accessibilityState={{ expanded: isNoteExpanded }}
            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
            style={{
              flexDirection: "row",
              alignItems: "center",
              gap: 4,
              paddingVertical: spacing.xs,
              paddingHorizontal: spacing.sm,
              borderRadius: radius.sm,
              backgroundColor: isNoteExpanded
                ? colors.accent.primaryDim
                : "transparent",
            }}
          >
            <Ionicons
              name={isNoteExpanded ? "create" : "create-outline"}
              size={iconSize.sm}
              color={
                isNoteExpanded ? colors.accent.primary : colors.text.muted
              }
            />
            {note.trim().length > 0 ? (
              <Text
                style={{
                  ...typography.tinyBold,
                  color: colors.accent.primary,
                  letterSpacing: 0.3,
                }}
              >
                Note
              </Text>
            ) : null}
          </RipplePressable>
        ) : null}
      </View>

      {showPencil && isNoteExpanded ? (
        <View style={{ marginTop: spacing.xs, gap: spacing.xs }}>
          <TextInput
            style={[
              inputStyles,
              {
                minHeight: 64,
                textAlignVertical: "top",
                fontSize: 14,
              },
            ]}
            value={note}
            onChangeText={onNoteChange}
            placeholder="Tip for the cook? (optional)"
            placeholderTextColor={colors.text.muted}
            multiline
            maxLength={240}
          />
          <Text
            style={{
              ...typography.tiny,
              color: colors.text.muted,
              textAlign: "right",
            }}
          >
            {note.length}/240
          </Text>
        </View>
      ) : null}
    </View>
  );
}

// ── Star row ─────────────────────────────────────────────────────────

const STAR_SIZE = iconSize.lg;

function StarRow({
  value,
  disabled,
  onRate,
  accessibilityLabel,
}: {
  value: number;
  disabled: boolean;
  onRate: (value: number) => void;
  accessibilityLabel: string;
}) {
  return (
    <View
      accessibilityRole="adjustable"
      accessibilityLabel={accessibilityLabel}
      accessibilityValue={{ min: 0, max: 5, now: value }}
      accessibilityState={{ disabled }}
      style={{ flexDirection: "row", gap: spacing.xs }}
    >
      {[1, 2, 3, 4, 5].map((v) => {
        const filled = value >= v;
        const tint = disabled
          ? filled
            ? colors.text.muted
            : colors.border.muted
          : filled
          ? colors.accent.primary
          : colors.text.muted;

        if (disabled) {
          // Non-pressable when disabled — visually present but inert.
          return (
            <View
              key={v}
              style={{ padding: spacing.xs, borderRadius: radius.sm }}
            >
              <Ionicons
                name={filled ? "star" : "star-outline"}
                size={STAR_SIZE}
                color={tint}
              />
            </View>
          );
        }

        return (
          <RipplePressable
            key={v}
            onPress={() => onRate(v)}
            accessibilityRole="button"
            accessibilityLabel={`${v} star${v === 1 ? "" : "s"}`}
            accessibilityState={{ selected: value === v }}
            hitSlop={{ top: 8, bottom: 8, left: 4, right: 4 }}
            style={{ padding: spacing.xs, borderRadius: radius.sm }}
          >
            <Ionicons
              name={filled ? "star" : "star-outline"}
              size={STAR_SIZE}
              color={tint}
            />
          </RipplePressable>
        );
      })}
    </View>
  );
}
