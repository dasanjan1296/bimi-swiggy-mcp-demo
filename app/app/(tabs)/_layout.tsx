/**
 * Tab bar — 2026-05-03 redesign reset.
 *
 * Three tabs only: Today / Settle / You. The previous five-tab shell
 * (Home / Plan / Orders / Expenses / Settings) violated principle #1
 * ("one question per session") by inviting users to wander between
 * five surfaces every time they opened the app. The retired tabs still
 * have their files in `(tabs)/` and resolve as routes — but they're
 * hidden from the tab bar via `href: null`. Direct links and stack
 * pushes from inline heroes (e.g., grocery approval hero pushing into
 * /(tabs)/approvals) keep working.
 *
 * See bimi/docs/UX-REDESIGN-2026-05-03.md §7 and design-system.md §11
 * for the rule. Adding a fourth tab requires updating both docs.
 */

import { Tabs } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { View, StyleSheet } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useHouseholdStore } from "@/lib/store";
import { colors, typography, spacing } from "@/lib/theme";

function TabBarBackground() {
  return <View style={[StyleSheet.absoluteFill, { backgroundColor: colors.surface.tabBar }]} />;
}

export default function TabLayout() {
  const household = useHouseholdStore((s) => s.household);
  const householdType = household?.type || "flatmates";
  // Settle is hidden in solo households — there's no money to settle.
  const showSettle = householdType === "flatmates" || householdType === "couple";
  const insets = useSafeAreaInsets();

  return (
    <View style={{ flex: 1 }}>
      <Tabs
        screenOptions={{
          headerShown: false,
          tabBarActiveTintColor: colors.tab.active,
          tabBarInactiveTintColor: colors.tab.inactive,
          tabBarStyle: {
            position: "absolute",
            backgroundColor: "transparent",
            borderTopColor: colors.tab.border,
            borderTopWidth: StyleSheet.hairlineWidth,
            height: 56 + insets.bottom,
            paddingBottom: insets.bottom,
            paddingTop: spacing.sm,
            elevation: 0,
          },
          tabBarBackground: () => <TabBarBackground />,
          tabBarLabelStyle: {
            fontSize: typography.tabLabel.fontSize,
            fontWeight: typography.tabLabel.fontWeight,
            fontFamily: typography.tabLabel.fontFamily,
          },
        }}
      >
        <Tabs.Screen
          name="index"
          options={{
            title: "Today",
            tabBarIcon: ({ color, size, focused }) => (
              <Ionicons name={focused ? "home" : "home-outline"} size={size} color={color} />
            ),
          }}
        />
        <Tabs.Screen
          name="expenses"
          options={{
            title: "Settle",
            tabBarIcon: ({ color, size, focused }) => (
              <Ionicons name={focused ? "wallet" : "wallet-outline"} size={size} color={color} />
            ),
            href: showSettle ? undefined : null,
          }}
        />
        <Tabs.Screen
          name="settings"
          options={{
            // 2026-05-03 audit: tab rebranded to "My Household" — it's
            // the household-management surface (members, cook profile,
            // saved recipes, meals history, dietary, auto-rules), not
            // a personal-settings page. Internal route stays at
            // /settings to avoid churning the dozen `router.push`
            // call-sites; only the user-facing label and chrome
            // change.
            //
            // Icon: `people-outline` (not `home` — that belongs to the
            // Today tab, and using both made the bar read as two home
            // tabs; not `settings` either — the rename was explicitly
            // away from a "personal settings" framing). `people-*` is
            // the canonical icon vocabulary for "household / members"
            // across this app: see (tabs)/settings.tsx (the No-household
            // callout), household-setup, cook-verify, cook-interview,
            // and settings/cook.
            title: "My Household",
            tabBarIcon: ({ color, size, focused }) => (
              <Ionicons
                name={focused ? "people" : "people-outline"}
                size={size}
                color={color}
              />
            ),
          }}
        />

        {/* 2026-05-03 audit (FRONTEND-BACKEND-COORDINATION.md): the
            previously-hidden voting, approvals, and kitchen tabs were
            DELETED — voting got folded into Today per redesign §7,
            approvals folded into Today as inline heroes, and the
            Kitchen tab was retired in favor of cook-message-driven
            inventory inference. The Insta Cook flow that the Undo
            toast watched is also gone. */}
      </Tabs>
    </View>
  );
}
