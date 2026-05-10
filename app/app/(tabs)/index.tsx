/**
 * Home (Today) — single-question hero + vertical agenda calendar.
 *
 * Layout (top → bottom):
 *   • Header — Bimi mark, editorial date, greeting, household name,
 *     cook-chat + notifications icons.
 *   • <NextBestAction> — the single hero card; one decision moment per
 *     session (priority tree handles cook actions, grocery approvals,
 *     festival overrides, vote prompts, rate prompts).
 *   • <HomeCalendar> — vertical agenda. Today anchored at the top of
 *     the list, tomorrow + 13 days below, past days opt-in via "Show
 *     earlier days". Tapping any day opens a unified day-detail sheet
 *     that branches on past / today / future.
 *   • Dev-only household switcher (compact, far from the hero).
 *
 * Why a calendar (was: spin wheel):
 *   The previous fridge-spinner centerpiece had no real-world gesture
 *   analog (users didn't know it span), only surfaced 7 days, and
 *   couldn't show the past. The agenda calendar uses a familiar
 *   top-to-bottom temporal model, surfaces past + future continuously,
 *   and makes "tap a day to vote / rate / inspect" the single
 *   interaction grammar. The standalone Meals History route at
 *   /settings/meals-history was retired in the same change since the
 *   home calendar covers the same surface (past days are one tap away
 *   via "Show earlier days"). The previous wheel implementation lives
 *   in git history (`git log --follow components/patterns/WheelOfMeals.tsx`).
 *
 * Hard rules preserved from the 2026-05-03 redesign:
 *   - One question per session — NextBestAction stays as the apex.
 *   - Density emerges from absence — past days are opt-in, far-future
 *     cards collapse to a quiet line.
 *
 * The previous home (~1400 lines pre-redesign) is preserved in git
 * history — `git log --follow app/app/(tabs)/index.tsx` to read it.
 */

import React, { useMemo, useState } from "react";
import {
  Modal,
  Pressable,
  RefreshControl,
  ScrollView,
  Text,
  View,
} from "react-native";
import * as Haptics from "expo-haptics";
import { useRouter } from "expo-router";
import { useHouseholdStore, useMealStore, useChatStore } from "@/lib/store";
import { useAuthStore } from "@/lib/auth-store";
import { useNotificationStore } from "@/lib/notifications";
import { NextBestAction } from "@/components/NextBestAction";
import { RipplePressable } from "@/components/RipplePressable";
import { IconButton } from "@/components/ui";
import { HomeCalendar } from "@/components/patterns";
import { GradientScreen } from "@/components/GradientScreen";
import { refreshToday } from "@/lib/today-store";
import { queryClient } from "@/lib/query-client";
import { useTabScrollToTop } from "@/lib/hooks/useTabScrollToTop";
import { useTabBarPadding } from "@/lib/hooks/useTabBarPadding";
import {
  colors,
  elevation,
  radius,
  spacing,
  typography,
} from "@/lib/theme";

export default function HomeScreen() {
  const router = useRouter();
  const household = useHouseholdStore((s) => s.household);
  const allHouseholds = useHouseholdStore((s) => s.allHouseholds);
  const switchHousehold = useHouseholdStore((s) => s.switchHousehold);
  const messages = useChatStore((s) => s.messages);
  const notifications = useNotificationStore((s) => s.notifications);
  const childId = useAuthStore((s) => s.childId);
  const authName = useAuthStore((s) => s.childName);

  const [showAbout, setShowAbout] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const tabScrollRef = useTabScrollToTop<ScrollView>();
  const tabBarPadding = useTabBarPadding();

  const notifUnread = useMemo(
    () => notifications.filter((n) => !n.read).length,
    [notifications],
  );

  const unresolvedCookActions = useMemo(
    () => messages.flatMap((m) => m.actionItems).filter((a) => !a.resolved),
    [messages],
  );

  const primaryCook = household?.cooks?.[0];
  const hasCook = household?.hasCook;

  // Cook-off context lives ON the calendar surface itself now — every
  // affected day card carries the OFF pill / "Malti off — self-cooking"
  // line inline, and the day-detail modal carries the actionable
  // banner. The home page used to duplicate this with a sticky
  // "Malti Didi is off tomorrow…" bar AND a calmer "Tomorrow: you'll
  // cook. I've got it." GuidanceTip at the bottom — both removed in
  // favour of the consistent calendar-cell surface.

  const activeMembers = useMemo(
    () => household?.members.filter((m) => m.isActive) || [],
    [household],
  );
  const currentMember = useMemo(() => {
    if (!household) return null;
    const byId = household.members.find((m) => m.id === childId);
    if (byId) return byId;
    return activeMembers[0] || null;
  }, [household, childId, activeMembers]);
  const firstName = (currentMember?.name || authName || "there").split(" ")[0];

  const onRefresh = () => {
    setRefreshing(true);
    // Recompute "today" against the device's wall clock so the
    // calendar rolls over if the user kept the app open across
    // midnight, and refetch every active query so meal plans,
    // history, and household state come back from the server.
    refreshToday();
    queryClient.invalidateQueries();
    setTimeout(() => {
      setRefreshing(false);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    }, 600);
  };

  return (
    <GradientScreen>
      <ScrollView
        ref={tabScrollRef}
        style={{ flex: 1 }}
        contentContainerStyle={{
          padding: spacing.lg,
          paddingBottom: tabBarPadding,
          paddingTop: 60,
        }}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={colors.accent.primary}
          />
        }
      >
        {/* ── Header ── compact greeting + ghost icon buttons. */}
        <View
          style={{
            flexDirection: "row",
            justifyContent: "space-between",
            alignItems: "flex-start",
            marginBottom: spacing.xl,
          }}
        >
          <View style={{ flex: 1, marginRight: spacing.sm }}>
            <RipplePressable
              onPress={() => setShowAbout(true)}
              haptic="light"
              style={{ alignSelf: "flex-start" }}
              accessibilityLabel="About Bimi"
              accessibilityRole="button"
            >
              <View
                style={{
                  width: 44,
                  height: 44,
                  borderRadius: radius.md,
                  backgroundColor: colors.surface.card,
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <Text
                  style={{
                    fontSize: 24,
                    fontWeight: "700",
                    color: colors.accent.primary,
                    fontFamily: typography.h1.fontFamily,
                  }}
                >
                  b
                </Text>
              </View>
            </RipplePressable>
            {/* Headline — just "Hi <FirstName>". The previous header
                stacked an EditorialDate eyebrow + a "Good evening,
                Anjan" time-of-day greeting, which truncated longer
                names on narrow screens. Calendar cards already carry
                the date context, so the dateline is redundant; and a
                single short greeting reads cleaner anyway. */}
            <Text
              style={{
                ...typography.hero,
                fontSize: 30,
                marginTop: spacing.md,
                lineHeight: 36,
              }}
              numberOfLines={1}
            >
              Hi {firstName}!
            </Text>
            <Text
              style={{ ...typography.caption, marginTop: 2 }}
              numberOfLines={1}
            >
              {household?.name || "Your Household"}
            </Text>
          </View>

          <View
            style={{
              flexDirection: "row",
              gap: spacing.sm,
              marginTop: spacing.xs,
            }}
          >
            {hasCook && primaryCook && (
              <IconButton
                icon="chatbubble-ellipses-outline"
                onPress={() => router.push("/cook-chat")}
                accessibilityLabel={`${primaryCook.name}${unresolvedCookActions.length > 0 ? ", needs attention" : ""}`}
                active={unresolvedCookActions.length > 0}
              />
            )}
            <IconButton
              icon="notifications-outline"
              onPress={() => router.push("/notifications")}
              accessibilityLabel={`Notifications${notifUnread > 0 ? `, ${notifUnread} unread` : ""}`}
              active={notifUnread > 0}
              badge={notifUnread > 0 ? notifUnread : undefined}
              badgeColor={colors.accent.primary}
            />
          </View>
        </View>

        {/* ── The single hero card. Driven by NextBestAction's priority
            tree. This is the one decision moment per session. */}
        <NextBestAction />

        {/* ── Home calendar ── vertical agenda below the hero. Today is
            the anchor at the top of the list; tomorrow + 13 days follow.
            Past days are opt-in via the "Show earlier days" affordance,
            so on every app open the user lands directly on today's card
            without a programmatic scroll. Replaced the 7-sector spin
            wheel; absorbed the standalone Meals History route. */}
        <HomeCalendar />

        {/* Cook-off / fallback narration that used to live here as a
            <GuidanceTip> ("Tomorrow: you'll cook. I've got it.") was
            removed — the calendar cells now show the same context
            inline ("Malti off — self-cooking" line on each day card),
            and a duplicate bottom narration was just noise. */}

        {/* ── Dev household switcher ── only in dev builds. Compact, far
            from the hero so it can't be confused with a feature. */}
        {__DEV__ && allHouseholds.length > 1 && (
          <View style={{ marginTop: spacing.xxxl, alignItems: "center" }}>
            <Text style={{ ...typography.tiny, marginBottom: spacing.sm }}>
              Demo: switch household
            </Text>
            <View style={{ flexDirection: "row", gap: spacing.sm }}>
              {allHouseholds.map((h) => (
                <Pressable
                  key={h.id}
                  onPress={() => switchHousehold(h.id)}
                  style={{
                    paddingHorizontal: spacing.md,
                    paddingVertical: spacing.xs + 1,
                    backgroundColor:
                      household?.id === h.id ? colors.accent.primary : colors.surface.card,
                    borderRadius: radius.sm,
                  }}
                >
                  <Text
                    style={{
                      ...typography.tiny,
                      color:
                        household?.id === h.id ? colors.text.inverse : colors.text.secondary,
                    }}
                  >
                    {h.type === "flatmates"
                      ? "Bachelor"
                      : h.type === "couple"
                      ? "Couple"
                      : "Family"}
                  </Text>
                </Pressable>
              ))}
            </View>
          </View>
        )}
      </ScrollView>

      {/* ── About Bimi modal ── centered card on a soft scrim. */}
      <Modal
        visible={showAbout}
        transparent
        animationType="fade"
        onRequestClose={() => setShowAbout(false)}
      >
        <Pressable
          style={{
            flex: 1,
            backgroundColor: colors.surface.scrim,
            justifyContent: "center",
            alignItems: "center",
            padding: spacing.xl,
          }}
          onPress={() => setShowAbout(false)}
        >
          <Pressable
            onPress={() => {}}
            style={{
              alignItems: "center",
              paddingVertical: spacing.xxl,
              paddingHorizontal: spacing.xl,
              backgroundColor: colors.surface.base,
              borderRadius: radius.xl,
              maxWidth: 360,
              width: "100%",
              ...elevation.high,
            }}
          >
            <Text
              style={{
                fontSize: 64,
                fontWeight: "700",
                color: colors.accent.primary,
                fontFamily: typography.h1.fontFamily,
              }}
            >
              b
            </Text>
            <Text
              style={{
                fontSize: 18,
                fontWeight: "700",
                letterSpacing: 2,
                marginTop: 4,
              }}
            >
              bimi
            </Text>
            <Text
              style={{
                ...typography.hero,
                fontSize: 24,
                lineHeight: 30,
                textAlign: "center",
                marginTop: spacing.lg,
              }}
            >
              The kitchen, off your mind.
            </Text>
            <Text
              style={{
                ...typography.body,
                color: colors.text.secondary,
                textAlign: "center",
                marginTop: spacing.sm,
              }}
            >
              Meals, cook, groceries — all of it, sorted.
            </Text>
          </Pressable>
        </Pressable>
      </Modal>
    </GradientScreen>
  );
}

