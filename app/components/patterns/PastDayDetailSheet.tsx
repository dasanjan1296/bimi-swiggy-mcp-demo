/**
 * PastDayDetailSheet — bottom sheet for one historical day.
 *
 * The body (cook summary, per-meal sections, member rows, dish notes)
 * is exposed as `PastDayBody` so the home calendar's unified
 * `<DayDetailSheet>` can render it inside one BottomSheet alongside
 * other day-state branches.
 *
 * Per meal section shows:
 *   • Dish that was decided
 *   • Vote tally with proxy attribution ("Bimi voted Maggi for Saumya")
 *   • Per-member post-eat ratings
 *   • Notes left by household members on this dish on this day
 *
 * Cook attendance is summarised at the top: "Malti cooked all 3 meals"
 * vs "Malti was off — household self-cooked / ordered". Read-only
 * surface; the only interactive affordances are inline edit / delete
 * kebabs on notes the active member authored, plus the close button.
 */

import React, { useCallback, useMemo } from "react";
import { Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useHouseholdStore } from "@/lib/store";
import { useAuthStore } from "@/lib/auth-store";
import { showAlert } from "@/lib/dialogs";
import { toast } from "@/lib/toast";
import {
  useDeleteDishNote,
  useDishNotesForDate,
  type DishNote,
} from "@/lib/use-dish-notes";
import { Avatar } from "../ui/Avatar";
import { RipplePressable } from "../RipplePressable";
import { BottomSheet } from "../ui/BottomSheet";
import {
  colors,
  iconSize,
  radius,
  spacing,
  typography,
} from "@/lib/theme";
import type {
  CookAbsenceEvent,
  MealHistoryEntry,
  MealType,
} from "@/lib/types";

// Per-meal colour + icon — turns "Breakfast / Lunch / Dinner" from
// repeated grey eyebrows into a small visual time-of-day cue. Tints
// stay subtle (Dim variant + accent foreground) so they read as
// metadata, not decoration.
const MEAL_THEME: Record<
  MealType,
  {
    label: string;
    icon: keyof typeof Ionicons.glyphMap;
    bg: string;
    fg: string;
  }
> = {
  breakfast: {
    label: "Breakfast",
    icon: "cafe-outline",
    bg: colors.accent.warningDim,
    fg: colors.accent.warning,
  },
  lunch: {
    label: "Lunch",
    icon: "sunny-outline",
    bg: colors.accent.primaryDim,
    fg: colors.accent.primary,
  },
  dinner: {
    label: "Dinner",
    icon: "moon-outline",
    bg: colors.accent.aiDim,
    fg: colors.accent.ai,
  },
  snack: {
    label: "Snack",
    icon: "nutrition-outline",
    bg: colors.accent.successDim,
    fg: colors.accent.success,
  },
};

const MEAL_ORDER: MealType[] = ["breakfast", "lunch", "dinner", "snack"];

export interface PastDayDetailSheetProps {
  visible: boolean;
  onClose: () => void;
  /** ISO yyyy-mm-dd of the day being inspected. */
  date: string | null;
  /** All MealHistoryEntry rows for this day (zero-or-more). */
  entries: MealHistoryEntry[];
  /** Cook absence overlapping this date, if any. */
  cookAbsence: CookAbsenceEvent | null;
}

/**
 * Shell — wraps `<PastDayBody>` with a BottomSheet that carries the
 * date + cook-summary header. The home calendar uses `<PastDayBody>`
 * directly inside its unified detail sheet.
 */
export function PastDayDetailSheet({
  visible,
  onClose,
  date,
  entries,
  cookAbsence,
}: PastDayDetailSheetProps) {
  if (!date) return null;

  const dateLabel = formatDateLong(date);
  const cookSummary = composeCookSummary(cookAbsence);

  return (
    <BottomSheet
      visible={visible}
      onClose={onClose}
      title={dateLabel}
      subtitle={cookSummary}
      maxHeightFraction={0.9}
      scrollable
    >
      <PastDayBody date={date} entries={entries} />
    </BottomSheet>
  );
}

export interface PastDayBodyProps {
  /** ISO date — used to look up dish notes. */
  date: string;
  /** Per-meal entries for this day. */
  entries: MealHistoryEntry[];
}

/**
 * Read-only past-day body. Fetches dish notes via `useDishNotesForDate`
 * and renders one MealSection per meal type that has data.
 */
export function PastDayBody({ date, entries }: PastDayBodyProps) {
  const household = useHouseholdStore((s) => s.household);
  const childId = useAuthStore((s) => s.childId);
  const familyId = household?.id;

  const { data: notes } = useDishNotesForDate({ familyId, date });

  // Author identity for edit/delete affordances on the user's own
  // notes. Same fallback chain as the rate sheet.
  const activeAuthorName = useMemo(() => {
    if (!household) return undefined;
    const member =
      household.members.find((m) => m.id === childId) ??
      household.members.find((m) => m.isActive);
    return member?.name;
  }, [household, childId]);

  const memberNameById = useMemo(() => {
    const map = new Map<string, string>();
    for (const m of household?.members ?? []) map.set(m.id, m.name);
    return map;
  }, [household]);

  // Group entries by meal type so the section render is deterministic
  // regardless of the order they were stored.
  const entriesByMealType = useMemo(() => {
    const map = new Map<MealType, MealHistoryEntry>();
    for (const e of entries) map.set(e.mealType, e);
    return map;
  }, [entries]);

  const notesByDish = useMemo(() => {
    const map = new Map<string, DishNote[]>();
    for (const n of notes ?? []) {
      const key = n.dishName.toLowerCase();
      const arr = map.get(key) ?? [];
      arr.push(n);
      map.set(key, arr);
    }
    return map;
  }, [notes]);

  const deleteNote = useDeleteDishNote();

  const handleDeleteNote = useCallback(
    (note: DishNote) => {
      if (!familyId || !activeAuthorName) return;
      showAlert(
        "Delete this note?",
        `"${note.noteText}" — the cook won't see this in tomorrow's brief.`,
        [
          { text: "Cancel", style: "cancel" },
          {
            text: "Delete",
            style: "destructive",
            onPress: async () => {
              try {
                await deleteNote.mutateAsync({
                  id: note.id,
                  familyId,
                  authorName: activeAuthorName,
                });
                toast.success("Note removed");
              } catch {
                toast.error("Couldn't remove", "Try again.");
              }
            },
          },
        ],
      );
    },
    [familyId, activeAuthorName, deleteNote],
  );

  return (
    <View
      style={{
        paddingTop: spacing.md,
        paddingBottom: spacing.xl,
        gap: spacing.lg,
      }}
    >
      {entries.length === 0 ? (
        <View
          style={{
            alignItems: "center",
            paddingVertical: spacing.xxl,
            gap: spacing.sm,
          }}
        >
          <Ionicons
            name="calendar-outline"
            size={iconSize.xl}
            color={colors.text.muted}
          />
          <Text
            style={{
              ...typography.body,
              color: colors.text.secondary,
              textAlign: "center",
            }}
          >
            Nothing recorded for this day.
          </Text>
          <Text
            style={{
              ...typography.tiny,
              color: colors.text.muted,
              textAlign: "center",
            }}
          >
            Plans that don't reach finalize don't make it to the
            history archive.
          </Text>
        </View>
      ) : (
        MEAL_ORDER.filter((mt) => entriesByMealType.has(mt)).map((mt) => {
          const entry = entriesByMealType.get(mt)!;
          const dishKey = entry.selectedMeal.toLowerCase();
          const dishNotes = notesByDish.get(dishKey) ?? [];
          return (
            <MealSection
              key={mt}
              entry={entry}
              memberNameById={memberNameById}
              notes={dishNotes}
              activeAuthorName={activeAuthorName}
              onDeleteNote={handleDeleteNote}
            />
          );
        })
      )}
    </View>
  );
}

// ── Per-meal section ────────────────────────────────────────────────

interface MemberRow {
  memberId: string;
  memberName: string;
  votedDish: string | null;
  isProxyVote: boolean;
  rating: number | null;
}

/**
 * Combine votes + ratings + participants into a single member-row
 * shape. Member-centric rendering removes the duplication of the
 * old design (the same name appearing once under "Votes" and once
 * under "Ratings") and lets the row tell a complete story per
 * person on a single line.
 */
function buildMemberRows(
  entry: MealHistoryEntry,
  memberNameById: Map<string, string>,
): MemberRow[] {
  const rows = new Map<string, MemberRow>();
  const ensure = (memberId: string): MemberRow => {
    let row = rows.get(memberId);
    if (!row) {
      row = {
        memberId,
        memberName: memberNameById.get(memberId) ?? "Someone",
        votedDish: null,
        isProxyVote: false,
        rating: null,
      };
      rows.set(memberId, row);
    }
    return row;
  };

  for (const id of entry.participantIds) ensure(id);
  for (const v of entry.votes) {
    const row = ensure(v.memberId);
    row.votedDish = v.dishName;
    row.isProxyVote = !!v.isProxy;
  }
  for (const r of entry.ratings) {
    ensure(r.memberId).rating = r.rating;
  }

  // Stable order — original participant order, then any extras
  // (members who voted/rated but weren't in participantIds).
  const ordered: MemberRow[] = [];
  const seen = new Set<string>();
  for (const id of entry.participantIds) {
    const row = rows.get(id);
    if (row) {
      ordered.push(row);
      seen.add(id);
    }
  }
  for (const [id, row] of rows) {
    if (!seen.has(id)) ordered.push(row);
  }
  return ordered;
}

function MealSection({
  entry,
  memberNameById,
  notes,
  activeAuthorName,
  onDeleteNote,
}: {
  entry: MealHistoryEntry;
  memberNameById: Map<string, string>;
  notes: DishNote[];
  activeAuthorName?: string;
  onDeleteNote: (note: DishNote) => void;
}) {
  const theme = MEAL_THEME[entry.mealType];
  const memberRows = buildMemberRows(entry, memberNameById);

  // Average rating across only the members who actually rated. The
  // header surface treats this as the "scorecard" — a single number
  // tells the day's story faster than a list of stars.
  const ratedRatings = memberRows
    .map((r) => r.rating)
    .filter((r): r is number => r != null);
  const avgRating =
    ratedRatings.length > 0
      ? ratedRatings.reduce((a, b) => a + b, 0) / ratedRatings.length
      : null;

  return (
    <View
      style={{
        backgroundColor: colors.surface.elevated,
        borderRadius: radius.lg,
        borderWidth: 1,
        borderColor: colors.border.muted,
        overflow: "hidden",
      }}
    >
      {/* Header — meal-type chip + dish name + scorecard. */}
      <View
        style={{
          padding: spacing.lg,
          gap: spacing.sm,
          borderBottomWidth: memberRows.length > 0 ? 1 : 0,
          borderBottomColor: colors.border.muted,
        }}
      >
        <View
          style={{
            flexDirection: "row",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <View
            style={{
              flexDirection: "row",
              alignItems: "center",
              gap: spacing.xs,
              backgroundColor: theme.bg,
              paddingVertical: 4,
              paddingHorizontal: spacing.sm,
              borderRadius: radius.pill,
            }}
          >
            <Ionicons name={theme.icon} size={iconSize.xs} color={theme.fg} />
            <Text
              style={{
                ...typography.tinyBold,
                color: theme.fg,
                textTransform: "uppercase",
                letterSpacing: 0.6,
              }}
            >
              {theme.label}
            </Text>
          </View>

          {avgRating != null ? (
            <View
              style={{
                flexDirection: "row",
                alignItems: "center",
                gap: 4,
              }}
            >
              <Ionicons
                name="star"
                size={iconSize.xs}
                color={colors.accent.warning}
              />
              <Text
                style={{
                  ...typography.smallBold,
                  color: colors.text.primary,
                }}
              >
                {avgRating.toFixed(1)}
              </Text>
              <Text
                style={{ ...typography.tiny, color: colors.text.muted }}
              >
                · {ratedRatings.length}
              </Text>
            </View>
          ) : null}
        </View>

        <Text
          style={{
            ...typography.h2,
            color: colors.text.primary,
            marginTop: 2,
          }}
          numberOfLines={2}
        >
          {entry.selectedMeal}
        </Text>

        {entry.votes.length > 0 ? (
          <Text
            style={{ ...typography.caption, color: colors.text.secondary }}
          >
            Picked from {entry.votes.length}{" "}
            {entry.votes.length === 1 ? "vote" : "votes"}
          </Text>
        ) : (
          // Rare path — finalised today before vote shape was
          // captured. State it plainly so the empty space doesn't
          // read as broken UI.
          <Text
            style={{
              ...typography.caption,
              color: colors.text.muted,
              fontStyle: "italic",
            }}
          >
            Vote details weren't captured for this meal.
          </Text>
        )}
      </View>

      {/* Member-centric rows — one row per person, combining the
          vote and post-eat rating. */}
      {memberRows.length > 0 ? (
        <View style={{ paddingVertical: spacing.xs }}>
          {memberRows.map((row, i) => (
            <MemberRowView
              key={row.memberId}
              row={row}
              isLast={i === memberRows.length - 1}
            />
          ))}
        </View>
      ) : null}

      {/* Notes — quoted speech-bubble style with author chip. The
          user's own notes carry an inline trash affordance. */}
      {notes.length > 0 ? (
        <View
          style={{
            padding: spacing.lg,
            paddingTop: 0,
            gap: spacing.sm,
          }}
        >
          <View
            style={{
              flexDirection: "row",
              alignItems: "center",
              gap: spacing.xs,
            }}
          >
            <Ionicons
              name="chatbubble-ellipses-outline"
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
              Notes for the cook
            </Text>
          </View>
          {notes.map((n) => {
            const isOwn =
              activeAuthorName != null &&
              n.authorName.trim().toLowerCase() ===
                activeAuthorName.trim().toLowerCase();
            return (
              <NoteCard
                key={n.id}
                note={n}
                isOwn={isOwn}
                onDelete={() => onDeleteNote(n)}
              />
            );
          })}
        </View>
      ) : null}
    </View>
  );
}

/** Single-row visualisation of one household member's involvement
 *  with this meal: avatar + name + what they voted (or AI proxy)
 *  + post-eat rating stars on the right. */
function MemberRowView({ row, isLast }: { row: MemberRow; isLast: boolean }) {
  return (
    <View
      style={{
        flexDirection: "row",
        alignItems: "center",
        gap: spacing.md,
        paddingHorizontal: spacing.lg,
        paddingVertical: spacing.sm,
        borderBottomWidth: isLast ? 0 : 1,
        borderBottomColor: colors.border.muted,
      }}
    >
      <Avatar id={row.memberId} name={row.memberName} size="sm" />
      <View style={{ flex: 1, gap: 2 }}>
        <Text
          style={{ ...typography.bodyBold, color: colors.text.primary }}
          numberOfLines={1}
        >
          {row.memberName}
        </Text>
        {row.votedDish ? (
          <View
            style={{
              flexDirection: "row",
              alignItems: "center",
              gap: 4,
            }}
          >
            {row.isProxyVote ? (
              <Ionicons
                name="sparkles"
                size={iconSize.xs}
                color={colors.accent.ai}
              />
            ) : null}
            <Text
              style={{ ...typography.caption, color: colors.text.secondary }}
              numberOfLines={1}
            >
              {row.isProxyVote ? "AI voted " : "Voted "}
              <Text style={{ color: colors.text.primary, fontWeight: "600" }}>
                {row.votedDish}
              </Text>
            </Text>
          </View>
        ) : (
          <Text style={{ ...typography.caption, color: colors.text.muted }}>
            Didn't vote
          </Text>
        )}
      </View>
      <Stars rating={row.rating} />
    </View>
  );
}

function Stars({ rating }: { rating: number | null }) {
  if (rating == null) {
    return (
      <Text
        style={{
          ...typography.tiny,
          color: colors.text.muted,
          fontStyle: "italic",
        }}
      >
        not rated
      </Text>
    );
  }
  const full = Math.max(0, Math.min(5, Math.round(rating)));
  return (
    <View style={{ flexDirection: "row", gap: 1 }}>
      {Array.from({ length: 5 }).map((_, i) => (
        <Ionicons
          key={i}
          name={i < full ? "star" : "star-outline"}
          size={13}
          color={i < full ? colors.accent.warning : colors.border.subtle}
        />
      ))}
    </View>
  );
}

function NoteCard({
  note,
  isOwn,
  onDelete,
}: {
  note: DishNote;
  isOwn: boolean;
  onDelete: () => void;
}) {
  return (
    <View
      style={{
        flexDirection: "row",
        alignItems: "flex-start",
        gap: spacing.sm,
        backgroundColor: colors.surface.card,
        borderRadius: radius.md,
        padding: spacing.md,
      }}
    >
      <Avatar name={note.authorName} size="xs" />
      <View style={{ flex: 1, gap: 2 }}>
        <Text
          style={{ ...typography.smallBold, color: colors.text.primary }}
        >
          {note.authorName}
        </Text>
        <Text style={{ ...typography.body, color: colors.text.primary }}>
          {note.noteText}
        </Text>
      </View>
      {isOwn ? (
        <RipplePressable
          onPress={onDelete}
          haptic="warning"
          accessibilityRole="button"
          accessibilityLabel="Delete note"
          hitSlop={{ top: 6, bottom: 6, left: 6, right: 6 }}
          style={{ padding: 4 }}
        >
          <Ionicons
            name="trash-outline"
            size={iconSize.sm}
            color={colors.accent.danger}
          />
        </RipplePressable>
      ) : null}
    </View>
  );
}

export function formatDateLong(iso: string): string {
  // Parse as local-noon to dodge timezone-DST drift; the date string
  // is yyyy-mm-dd intended as a calendar date, not a moment in time.
  const [y, m, d] = iso.split("-").map((p) => parseInt(p, 10));
  if (!y || !m || !d) return iso;
  const local = new Date(y, m - 1, d, 12, 0, 0);
  return local.toLocaleDateString("en-IN", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

export function composeCookSummary(absence: CookAbsenceEvent | null): string {
  if (!absence) return "Cook came in as scheduled";
  const cookFirst = absence.cookName.split(" ")[0] || absence.cookName;
  if (absence.fallbackChosen === "self_cook") {
    return `${cookFirst} was off — household self-cooked`;
  }
  if (absence.fallbackChosen === "order_food") {
    return `${cookFirst} was off — household ordered food`;
  }
  if (absence.fallbackChosen === "instacook") {
    return `${cookFirst} was off — Insta Cook arranged`;
  }
  if (absence.fallbackChosen === "replacement_cook") {
    return `${cookFirst} was off — replacement cook arranged`;
  }
  if (absence.fallbackChosen === "skip") {
    return `${cookFirst} was off — meals skipped`;
  }
  return `${cookFirst} was off`;
}
