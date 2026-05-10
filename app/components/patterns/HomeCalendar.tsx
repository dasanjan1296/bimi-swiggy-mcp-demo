/**
 * HomeCalendar — bounded-viewport vertical agenda, modeled on Google
 * Calendar's day view: a fixed-height scroll region sits below the
 * `<NextBestAction>` hero card so that hero is ALWAYS visible. The
 * user scrolls vertically inside the region (with normal touch
 * gestures) to move through past, today, and future days.
 *
 * Two behaviours that matter:
 *
 *   1. Bounded viewport — the calendar reserves a fixed slice of
 *      the home screen (~half the device height, with sane min/max).
 *      No matter how far back the user scrolls into history, the
 *      home screen's chrome (greeting, NextBestAction, cook-off
 *      narration, etc.) stays where it is.
 *
 *   2. Today-anchored — on first paint the FlatList is scrolled so
 *      today's card sits at the TOP of the viewport. Past days are
 *      one swipe up; future days are one swipe down. A "Today" pill
 *      appears in the header whenever the visible top day is not
 *      today, so the user can always hop back.
 *
 * Past-window strategy:
 *   • Initial: 14 past days loaded.
 *   • A "Show earlier days" pill renders as the FlatList header
 *     (i.e., it's the first thing the user sees when they swipe to
 *     the very top). Tapping it grows the past window by 30 days,
 *     up to a 90-day cap (matches the backend `meal-history` cap).
 *   • `maintainVisibleContentPosition` keeps the user's currently-
 *     visible cards in place when the array gains entries on the
 *     left — so loading older days doesn't snap-shift the viewport.
 *
 * Three sources of truth (unchanged from earlier revisions):
 *   1. `useWeekMealPlans()`     — D+0..D+6 (live + future-store)
 *   2. `useMealHistory()`       — server-backed past window
 *   3. `useCookAbsenceStore()`  — overlapping cook-off banners
 *
 * Sheet handoff (unchanged): tapping a card opens `<DayDetailSheet>`;
 * the "Rate today's meals" CTA opens `<RateMealSheet>`; cook-off
 * "Self cook ideas" opens `<SelfCookSheet>`. We orchestrate the
 * handoff here because @gorhom/bottom-sheet doesn't compose nested
 * sheets cleanly.
 */

import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  type NativeScrollEvent,
  type NativeSyntheticEvent,
  ScrollView,
  Text,
  View,
  useWindowDimensions,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { useMealStore, useCookAbsenceStore, useHouseholdStore } from "@/lib/store";
import { useAuthStore } from "@/lib/auth-store";
import { useMealHistory } from "@/lib/use-meal-history";
import { useWeekMealPlans, type WeekDay } from "@/lib/use-week-meal-plans";
import { localIsoDate, localIsoDatePlus, useToday } from "@/lib/local-day";
import { useReducedMotion } from "@/lib/useReducedMotion";
import { track } from "@/lib/analytics";
import { RipplePressable } from "../RipplePressable";
import { EmptyStateGuide } from "../GuidanceTip";
import {
  colors,
  iconSize,
  radius,
  spacing,
  typography,
} from "@/lib/theme";
import type {
  Cook,
  CookAbsenceEvent,
  MealHistoryEntry,
  MealType,
} from "@/lib/types";
import type { DayCookOff } from "@/lib/use-week-meal-plans";
import { DayCardRow } from "./DayCardRow";
import { DayDetailSheet } from "./DayDetailSheet";
import { RateMealSheet } from "./RateMealSheet";
import { SelfCookSheet } from "./SelfCookSheet";
import { type CalendarDay, buildDayCookOff } from "./home-calendar-types";

// ── Window constants ────────────────────────────────────────────────
const FUTURE_DAYS = 14;
const INITIAL_PAST_DAYS = 14;
const PAST_INCREMENT = 30;
const MAX_PAST_DAYS = 90;
const ITEM_GAP = spacing.sm;

// Best-effort rendered heights per state — only used as a fallback
// when an item hasn't been measured yet via `onLayout`. Once cards
// render they record their actual heights into `measuredHeights`,
// and the scroll math uses real measurements (see `computeOffsetForIndex`).
//
// These numbers are intentionally on the lower side: an undershoot
// during initial paint puts today slightly above the viewport top
// (visible at offset > 0, scroll-aware), whereas an overshoot pushes
// today above the viewport entirely (off-screen — what the previous
// 220 / 180 estimates were doing, and the cause of the broken Today
// jump button).
function estimateDayHeight(day: CalendarDay): number {
  if (day.state === "today") return 180;
  if (day.state === "tomorrow") return 150;
  if (day.state === "near-future") return 130;
  if (day.state === "past") return day.hasData ? 130 : 56;
  if (day.state === "far-future") return 56;
  return 130;
}

// Approximate height of the "Show earlier days" pill header. Replaced
// by an onLayout measurement once the header renders.
const LOAD_EARLIER_HEIGHT_FALLBACK = 56;

export interface HomeCalendarProps {
  /** Optional outer style passthrough (e.g., marginTop). */
  style?: any;
}

export function HomeCalendar({ style }: HomeCalendarProps) {
  const today = useToday();
  const todayIso = localIsoDate(today);
  const reducedMotion = useReducedMotion();

  // ── Viewport sizing ─────────────────────────────────────────────
  // Adapts to screen height so small devices don't get a pager that
  // eats the whole screen, and large devices don't get a tiny strip.
  // Roughly the height of 3 day cards + a peek of the 4th.
  const { height: screenHeight } = useWindowDimensions();
  const viewportHeight = Math.min(
    520,
    Math.max(360, Math.round(screenHeight * 0.5)),
  );

  // ── State ───────────────────────────────────────────────────────
  const [pastDaysLoaded, setPastDaysLoaded] = useState(INITIAL_PAST_DAYS);
  const [topVisibleDate, setTopVisibleDate] = useState<string | null>(null);
  const scrollRef = useRef<ScrollView>(null);
  // Tracks whether we've completed the initial today-anchor scroll.
  // Until then the list is hidden so the user never sees the past-day
  // flicker before the programmatic scroll lands.
  const [didInitialScroll, setDidInitialScroll] = useState(false);

  // Per-item measured y-position + height, captured via onLayout. We
  // use a plain ScrollView (not FlatList) because nesting a vertical
  // FlatList inside the home tab's vertical ScrollView triggers RN's
  // "VirtualizedLists should never be nested inside plain ScrollViews
  // with the same orientation" warning. With ~30-50 day cards in the
  // agenda, the virtualization win is negligible — but the layout
  // primitives we get from ScrollView (each child reports its `y`
  // relative to the content container directly) actually simplify the
  // Today-jump math compared to FlatList's `getItemLayout` estimates
  // that previously broke the jump button.
  const itemPositions = useRef<Map<string, number>>(new Map());
  const measuredHeights = useRef<Map<string, number>>(new Map());
  const headerHeightRef = useRef<number>(LOAD_EARLIER_HEIGHT_FALLBACK);

  // ── Data sources ────────────────────────────────────────────────
  const weekDays = useWeekMealPlans();
  const localHistory = useMealStore((s) => s.mealHistory);
  const absences = useCookAbsenceStore((s) => s.absences);
  const household = useHouseholdStore((s) => s.household);
  const familyId = useAuthStore((s) => s.familyId) ?? undefined;
  const childId = useAuthStore((s) => s.childId);
  const authName = useAuthStore((s) => s.childName);

  const fromIso = useMemo(
    () => localIsoDatePlus(-pastDaysLoaded, today),
    [pastDaysLoaded, today],
  );
  const toIso = useMemo(() => localIsoDatePlus(-1, today), [today]);

  const { data: serverHistory } = useMealHistory({
    familyId,
    from: fromIso,
    to: toIso,
  });
  const history = useMemo<MealHistoryEntry[]>(() => {
    if (serverHistory && serverHistory.length > 0) return serverHistory;
    return localHistory;
  }, [serverHistory, localHistory]);

  // ── Active member context (for synthesised today entries) ───────
  const activeMemberIds = useMemo(
    () =>
      (household?.members ?? [])
        .filter((m) => m.isActive)
        .map((m) => m.id),
    [household],
  );
  const activeMemberId = useMemo(() => {
    if (!household) return null;
    const byId = household.members.find((m) => m.id === childId);
    if (byId) return byId.id;
    return household.members.find((m) => m.isActive)?.id ?? null;
  }, [household, childId]);

  // Primary cook for weekly day-off detection (e.g. Sunday off). Past
  // days don't apply weekly-off — see `buildCookOff` in
  // lib/use-week-meal-plans.ts for the rationale.
  const cook = household?.cooks?.[0] ?? null;

  // ── Build flat agenda (past oldest first → today → future) ──────
  const agenda = useMemo(
    () =>
      buildAgenda({
        today,
        todayIso,
        pastDaysLoaded,
        futureDays: FUTURE_DAYS,
        weekDays,
        history,
        absences,
        cook,
        activeMemberIds,
        activeMemberId,
      }),
    [
      today,
      todayIso,
      pastDaysLoaded,
      weekDays,
      history,
      absences,
      cook,
      activeMemberIds,
      activeMemberId,
    ],
  );

  // Today's index in the array — the anchor for initial scroll and
  // for the "Today" pill jump action.
  const todayArrayIndex = useMemo(
    () => agenda.findIndex((d) => d.date === todayIso),
    [agenda, todayIso],
  );

  // ── Sheet orchestration ─────────────────────────────────────────
  const [openDate, setOpenDate] = useState<string | null>(null);
  const [rateDate, setRateDate] = useState<string | null>(null);
  const [selfCookCtx, setSelfCookCtx] = useState<{
    cookOff: DayCookOff;
    cookName?: string;
    mealType?: MealType;
  } | null>(null);

  const openDayFor = useCallback((day: CalendarDay) => {
    setOpenDate(day.date);
    track("calendar.day_opened", {
      meal_date: day.date,
      day_state: day.state,
      voted_count: day.weekDay?.voted ?? null,
      has_cook_off: !!day.cookOff,
    });
  }, []);

  const handleOpenRate = useCallback((date: string) => {
    setRateDate(date);
  }, []);

  const handleOpenSelfCookIdeas = useCallback((cookOff: DayCookOff) => {
    setSelfCookCtx({
      cookOff,
      cookName: cookOff.absence.cookName,
      mealType:
        cookOff.affectedMeals.length === 1
          ? cookOff.affectedMeals[0]
          : undefined,
    });
  }, []);

  const selectedDay = useMemo(
    () => (openDate ? agenda.find((d) => d.date === openDate) ?? null : null),
    [openDate, agenda],
  );

  const rateWeekDay = useMemo(
    () =>
      rateDate
        ? agenda.find((d) => d.date === rateDate)?.weekDay ?? null
        : null,
    [rateDate, agenda],
  );

  const activeMemberName =
    household?.members.find((m) => m.id === activeMemberId)?.name ??
    authName ??
    undefined;

  // ── Compute exact offset to a row ───────────────────────────────
  // ScrollView's children report their `y` (relative to the content
  // container) via onLayout, so the offset to scroll a row to the top
  // of the viewport is JUST that recorded `y` value. Falls back to a
  // summed estimate when the target hasn't been measured yet (e.g.
  // first paint before today's card has rendered).
  const computeOffsetForIndex = useCallback(
    (targetIdx: number): number => {
      const day = agenda[targetIdx];
      if (!day) return 0;
      const measuredY = itemPositions.current.get(day.date);
      if (measuredY !== undefined) return Math.max(0, measuredY);
      // Fallback estimate — matches the layout the ScrollView will
      // produce: paddingTop + (header? + gap) + sum(item heights + gaps).
      let offset = spacing.sm;
      if (pastDaysLoaded < MAX_PAST_DAYS) {
        offset += headerHeightRef.current + ITEM_GAP;
      }
      for (let i = 0; i < targetIdx; i++) {
        const d = agenda[i];
        offset +=
          measuredHeights.current.get(d.date) ?? estimateDayHeight(d);
        if (i < targetIdx) offset += ITEM_GAP;
      }
      return Math.max(0, offset);
    },
    [agenda, pastDaysLoaded],
  );

  // ── Initial scroll: today at top of viewport ────────────────────
  // Two passes: first scroll uses whatever measurements have landed by
  // the next frame; the second pass re-scrolls once today's neighbours
  // have measured. The list is hidden via opacity until the scroll
  // completes so the user never sees the past-day flash.
  useEffect(() => {
    if (didInitialScroll) return;
    if (todayArrayIndex < 0) return;
    const handle = requestAnimationFrame(() => {
      scrollRef.current?.scrollTo({
        y: computeOffsetForIndex(todayArrayIndex),
        animated: false,
      });
      requestAnimationFrame(() => {
        scrollRef.current?.scrollTo({
          y: computeOffsetForIndex(todayArrayIndex),
          animated: false,
        });
        setDidInitialScroll(true);
      });
    });
    return () => cancelAnimationFrame(handle);
  }, [didInitialScroll, todayArrayIndex, computeOffsetForIndex]);

  // ── Track topmost visible day (drives the "Today" pill) ─────────
  // ScrollView doesn't have FlatList's onViewableItemsChanged, so we
  // compute the topmost item from the scroll offset + each item's
  // recorded y position. Throttled to 100 ms via scrollEventThrottle
  // to keep the work under control during fast swipes.
  const handleScroll = useCallback(
    (e: NativeSyntheticEvent<NativeScrollEvent>) => {
      const scrollY = e.nativeEvent.contentOffset.y;
      let topDate: string | null = null;
      let bestY = -Infinity;
      // Largest item.y that is still <= scrollY = topmost visible.
      for (const day of agenda) {
        const y = itemPositions.current.get(day.date);
        if (y === undefined) continue;
        if (y <= scrollY + 4 && y > bestY) {
          bestY = y;
          topDate = day.date;
        }
      }
      // Fallback if nothing measured — leave state unchanged.
      if (topDate && topDate !== topVisibleDate) {
        setTopVisibleDate(topDate);
      }
    },
    [agenda, topVisibleDate],
  );

  // ── Lazy-load earlier days (pill at top of list) ────────────────
  const canLoadMorePast = pastDaysLoaded < MAX_PAST_DAYS;
  const handleLoadEarlier = useCallback(() => {
    setPastDaysLoaded((cur) => {
      const next = Math.min(MAX_PAST_DAYS, cur + PAST_INCREMENT);
      if (next > cur) {
        track("calendar.scroll_loaded_past", {
          days_added: next - cur,
          total_days_loaded: next,
        });
      }
      return next;
    });
  }, []);

  // ── Jump-to-today ───────────────────────────────────────────────
  const handleJumpToToday = useCallback(() => {
    if (todayArrayIndex < 0) return;
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    scrollRef.current?.scrollTo({
      y: computeOffsetForIndex(todayArrayIndex),
      animated: !reducedMotion,
    });
    setTopVisibleDate(todayIso);
    track("calendar.jump_to_today_tapped", {});
  }, [todayArrayIndex, reducedMotion, todayIso, computeOffsetForIndex]);

  // ── Empty-household fallback ────────────────────────────────────
  const isEmptyHousehold =
    weekDays.every((w) => w.voted === 0 && !w.cookOff) &&
    history.length === 0;

  const showTodayPill =
    !!topVisibleDate && topVisibleDate !== todayIso && todayArrayIndex >= 0;

  return (
    <View style={[{ marginTop: spacing.lg }, style]}>
      <ScrollHeader showTodayPill={showTodayPill} onJumpToToday={handleJumpToToday} />

      {isEmptyHousehold ? (
        <View style={{ marginTop: spacing.md }}>
          <EmptyStateGuide
            icon="calendar-outline"
            title="Your meal plans live here"
            message="Once Bimi suggests meals for your household, they'll show up in this calendar — today first, with past days one swipe up and future days one swipe down."
          />
        </View>
      ) : (
        <View
          style={{
            height: viewportHeight,
            // Faint top + bottom hairline so the bounded scroll region
            // reads as a self-contained surface, not just floating
            // content. The hairline is below cards so they "peek out"
            // visually from a defined card-deck.
            borderTopWidth: 1,
            borderTopColor: colors.border.muted,
            borderBottomWidth: 1,
            borderBottomColor: colors.border.muted,
            // Hide first paint until programmatic scroll-to-today
            // completes (avoids a flash of the topmost past day).
            opacity: didInitialScroll ? 1 : 0,
          }}
        >
          <ScrollView
            ref={scrollRef}
            // Each row's onLayout records its y-position into
            // `itemPositions`, which `computeOffsetForIndex` reads to
            // jump exactly to today's card (no estimate drift). The
            // contentContainer's `gap` makes the y-positions already
            // include between-card spacing, so no separator math.
            contentContainerStyle={{
              paddingVertical: spacing.sm,
              gap: ITEM_GAP,
            }}
            onScroll={handleScroll}
            scrollEventThrottle={100}
            // `maintainVisibleContentPosition` keeps the user's
            // visible cards in place when items are inserted at the
            // top (Show earlier days grows the past window).
            maintainVisibleContentPosition={{
              minIndexForVisible: 0,
              autoscrollToTopThreshold: 10,
            }}
            nestedScrollEnabled
            showsVerticalScrollIndicator={false}
          >
            {canLoadMorePast ? (
              <View
                onLayout={(e) => {
                  const h = e.nativeEvent.layout.height;
                  if (h > 0) headerHeightRef.current = h;
                }}
              >
                <LoadEarlierPill onPress={handleLoadEarlier} />
              </View>
            ) : null}

            {agenda.map((day) => (
              <View
                key={day.date}
                onLayout={(e) => {
                  const { y, height } = e.nativeEvent.layout;
                  if (height > 0) measuredHeights.current.set(day.date, height);
                  // y is relative to the contentContainer — exactly
                  // the offset we'd pass to scrollTo to put this card
                  // at the viewport top.
                  itemPositions.current.set(day.date, y);
                }}
              >
                <DayCardRow day={day} onPress={() => openDayFor(day)} />
              </View>
            ))}
          </ScrollView>
        </View>
      )}

      {/* ── Sheets — orchestrated handoff to avoid nesting. */}
      <DayDetailSheet
        visible={!!openDate}
        onClose={() => setOpenDate(null)}
        day={selectedDay}
        onOpenRate={handleOpenRate}
        onOpenSelfCookIdeas={handleOpenSelfCookIdeas}
      />

      <RateMealSheet
        visible={!!rateWeekDay}
        onClose={() => setRateDate(null)}
        day={rateWeekDay}
      />

      <SelfCookSheet
        visible={!!selfCookCtx}
        onClose={() => setSelfCookCtx(null)}
        cookName={selfCookCtx?.cookName}
        mealType={selfCookCtx?.mealType}
        familyId={household?.id}
        createdByName={activeMemberName}
      />
    </View>
  );
}

// ── Scroll header ──────────────────────────────────────────────────
// Single-row header that sits above the bounded scroll region. The
// section eyebrow names the surface; the Today pill (only visible
// when the user has scrolled away from today's card) snaps back.

function ScrollHeader({
  showTodayPill,
  onJumpToToday,
}: {
  showTodayPill: boolean;
  onJumpToToday: () => void;
}) {
  return (
    <View
      style={{
        flexDirection: "row",
        alignItems: "center",
        justifyContent: "space-between",
        marginBottom: spacing.sm,
        gap: spacing.sm,
      }}
    >
      <Text
        style={{
          ...typography.tinyBold,
          color: colors.text.muted,
          textTransform: "uppercase",
          letterSpacing: 1.2,
        }}
      >
        Your meals
      </Text>

      {showTodayPill ? (
        <RipplePressable
          onPress={onJumpToToday}
          haptic="success"
          accessibilityRole="button"
          accessibilityLabel="Jump to today"
          style={{
            paddingHorizontal: spacing.sm,
            paddingVertical: 4,
            borderRadius: radius.pill,
            backgroundColor: colors.accent.primaryDim,
            borderWidth: 1,
            borderColor: colors.accent.primary,
            flexDirection: "row",
            alignItems: "center",
            gap: 3,
          }}
        >
          <Ionicons
            name="locate"
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
            Today
          </Text>
        </RipplePressable>
      ) : null}
    </View>
  );
}

// ── List header pill: "Show earlier days" ──────────────────────────

function LoadEarlierPill({ onPress }: { onPress: () => void }) {
  return (
    <View
      style={{
        alignItems: "center",
        paddingVertical: spacing.sm,
        marginBottom: spacing.sm,
      }}
    >
      <RipplePressable
        onPress={onPress}
        haptic="selection"
        accessibilityRole="button"
        accessibilityLabel="Show earlier days"
        style={{
          paddingVertical: spacing.xs + 2,
          paddingHorizontal: spacing.md,
          borderRadius: radius.pill,
          flexDirection: "row",
          alignItems: "center",
          gap: spacing.xs,
          backgroundColor: colors.surface.card,
          borderWidth: 1,
          borderColor: colors.border.subtle,
        }}
      >
        <Ionicons
          name="chevron-up"
          size={iconSize.xs}
          color={colors.text.secondary}
        />
        <Text
          style={{
            ...typography.smallBold,
            color: colors.text.secondary,
          }}
        >
          Show earlier days
        </Text>
      </RipplePressable>
    </View>
  );
}

// ── Agenda builder ──────────────────────────────────────────────────

interface BuildAgendaOpts {
  today: Date;
  todayIso: string;
  pastDaysLoaded: number;
  futureDays: number;
  weekDays: WeekDay[];
  history: MealHistoryEntry[];
  absences: CookAbsenceEvent[];
  /** Primary cook (for weekly day-off detection on today + future). */
  cook: Cook | null;
  activeMemberIds: string[];
  activeMemberId: string | null;
}

function buildAgenda(opts: BuildAgendaOpts): CalendarDay[] {
  const {
    today,
    todayIso,
    pastDaysLoaded,
    futureDays,
    weekDays,
    history,
    absences,
    cook,
    activeMemberIds,
    activeMemberId,
  } = opts;

  const historyByDate = new Map<string, MealHistoryEntry[]>();
  for (const e of history) {
    const arr = historyByDate.get(e.date) ?? [];
    arr.push(e);
    historyByDate.set(e.date, arr);
  }

  // Synthesise today's history rows from live plans so today's card
  // surfaces votes/ratings before finalizePlan mirrors them into
  // mealHistory at end-of-day.
  const todayWeekDay = weekDays.find((w) => w.offset === 0);
  if (todayWeekDay && (historyByDate.get(todayIso) ?? []).length === 0) {
    const synth = synthesizeTodayEntries(
      todayWeekDay,
      activeMemberIds,
      activeMemberId,
    );
    if (synth.length > 0) historyByDate.set(todayIso, synth);
  }

  const days: CalendarDay[] = [];

  // ── Past (oldest first, so chronological order) ────────────────
  for (let offset = -pastDaysLoaded; offset <= -1; offset++) {
    const d = new Date(today);
    d.setDate(today.getDate() + offset);
    const date = localIsoDate(d);
    const entries = historyByDate.get(date) ?? [];
    const cookOff = buildDayCookOff(date, absences, cook, todayIso);
    days.push({
      date,
      state: "past",
      dayLong: longLabel(d),
      dayOfMonth: d.getDate(),
      weekdayShort: shortLabel(d),
      relativeLabel: relativePastLabel(offset),
      pastEntries: entries,
      cookOff,
      hasData: entries.length > 0 || !!cookOff,
    });
  }

  // ── Today + near-future (D+0..D+6) ─────────────────────────────
  for (const w of weekDays) {
    days.push({
      date: w.date,
      state:
        w.offset === 0
          ? "today"
          : w.offset === 1
          ? "tomorrow"
          : "near-future",
      dayLong: w.dayLong,
      dayOfMonth: parseInt(w.date.slice(8, 10), 10),
      weekdayShort: w.dayShort,
      relativeLabel:
        w.offset === 0
          ? "Today"
          : w.offset === 1
          ? "Tomorrow"
          : `In ${w.offset} days`,
      weekDay: w,
      cookOff: w.cookOff,
      hasData: w.voted > 0 || !!w.cookOff,
    });
  }

  // ── Far-future (D+7 .. D+(futureDays - 1)) ─────────────────────
  for (let offset = 7; offset < futureDays; offset++) {
    const d = new Date(today);
    d.setDate(today.getDate() + offset);
    const date = localIsoDate(d);
    const cookOff = buildDayCookOff(date, absences, cook, todayIso);
    days.push({
      date,
      state: "far-future",
      dayLong: longLabel(d),
      dayOfMonth: d.getDate(),
      weekdayShort: shortLabel(d),
      relativeLabel: `In ${offset} days`,
      cookOff,
      hasData: !!cookOff,
    });
  }

  return days;
}

function synthesizeTodayEntries(
  weekDay: WeekDay,
  activeMemberIds: string[],
  activeMemberId: string | null,
): MealHistoryEntry[] {
  return weekDay.plans
    .filter((p) => !!p.selectedMeal)
    .map((p) => {
      const skippedIds = new Set(
        p.votes.filter((v) => v.skipped).map((v) => v.memberId),
      );
      const participantIds = activeMemberIds.filter(
        (id) => !skippedIds.has(id),
      );
      const votes = p.votes
        .filter((v) => !v.skipped)
        .map((v) => ({
          memberId: v.memberId,
          dishName: v.dishName,
          rating: v.rating,
          isProxy: v.isProxy ?? false,
        }));
      const ratings =
        p.rating != null && activeMemberId
          ? [{ memberId: activeMemberId, rating: p.rating }]
          : [];
      return {
        date: p.date,
        mealType: p.mealType,
        selectedMeal: p.selectedMeal!,
        participantIds,
        votes,
        ratings,
      };
    });
}

// ── Date label helpers ─────────────────────────────────────────────

function shortLabel(d: Date): string {
  return d.toLocaleDateString("en-IN", { weekday: "short" });
}

function longLabel(d: Date): string {
  return d.toLocaleDateString("en-IN", {
    weekday: "long",
    month: "short",
    day: "numeric",
  });
}

function relativePastLabel(offsetDays: number): string {
  const n = Math.abs(offsetDays);
  if (n === 1) return "Yesterday";
  if (n < 7) return `${n} days ago`;
  if (n < 14) return "Last week";
  if (n < 30) return `${Math.round(n / 7)} weeks ago`;
  return "Earlier";
}
