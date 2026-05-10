/**
 * Dashboard showcase. Reference layout for any "home / overview" screen
 * — the actual home tab, kitchen overview, household dashboard, savings.
 * Demonstrates:
 *
 *   - HeaderWithActions (greeting + chat/bell)
 *   - HeroCard above the fold (single CTA)
 *   - BandHeader section divider ("TODAY")
 *   - Horizontal PhotoCard scroller
 *   - BandHeader ("TOMORROW")
 *   - ListRowGroup with 3 rows
 *   - EmptyState as fallback when a section is empty
 *
 * The actual home tab uses these patterns directly. If the home tab
 * starts to drift, this is the visual reference to bring it back to.
 */

import React from "react";
import { ScrollView, Text, View } from "react-native";
import { safeBack } from "@/lib/safe-back";
import {
  HeaderWithActions,
  HeroCard,
  BandHeader,
  PhotoCard,
  ListRow,
  ListRowGroup,
  EmptyState,
} from "@/components/patterns";
import { SafeScreen, StatusChip } from "@/components/ui";
import { colors, spacing, typography } from "@/lib/theme";

export default function DashboardShowcase() {
  return (
    <SafeScreen>
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{
          padding: spacing.lg,
          paddingBottom: spacing.xxl,
          gap: spacing.xl,
        }}
      >
        <HeaderWithActions
          title="Hey Anjan"
          subtitle="Sunday · Flat 114, Tower 6"
          actions={[
            {
              icon: "chatbubble-ellipses-outline",
              onPress: () => {},
              accessibilityLabel: "Open cook chat",
            },
            {
              icon: "notifications-outline",
              onPress: () => {},
              accessibilityLabel: "Open notifications",
              active: true,
              badge: 3,
            },
          ]}
        />

        <HeroCard
          tone="warning"
          icon="chatbubble-ellipses"
          title="3 things from your cook"
          subtitle="Order atta — only 2kg left · +2 more"
          ctaLabel="Review & approve"
          onPress={() => safeBack()}
        />

        <View>
          <BandHeader label="Today" style={{ marginBottom: spacing.md }} />
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={{ gap: spacing.md, paddingRight: spacing.lg }}
          >
            <View style={{ width: 280 }}>
              <PhotoCard
                title="Chole Bhature"
                subtitle="Lunch · 45 min"
                ribbon={{ label: "Cooking now", tone: "primary" }}
                badge={{ kind: "veg" }}
                onPress={() => {}}
              />
            </View>
            <View style={{ width: 280 }}>
              <PhotoCard
                title="Dal Makhani"
                subtitle="Dinner · 50 min"
                badge={{ kind: "veg" }}
                onPress={() => {}}
              />
            </View>
          </ScrollView>
        </View>

        <View>
          <BandHeader label="Tomorrow" style={{ marginBottom: spacing.md }} />
          <ListRowGroup>
            <ListRow
              leading="sunny-outline"
              leadingTone="warning"
              iconBubble
              title="Breakfast"
              subtitle="Idli sambar"
              trailing={<StatusChip status="approved" size="xs" />}
              onPress={() => {}}
            />
            <ListRow
              leading="restaurant-outline"
              leadingTone="primary"
              iconBubble
              title="Lunch"
              subtitle="Pick a meal"
              onPress={() => {}}
            />
            <ListRow
              leading="moon-outline"
              leadingTone="info"
              iconBubble
              title="Dinner"
              subtitle="Rajma chawal"
              trailing={<StatusChip status="approved" size="xs" />}
              onPress={() => {}}
            />
          </ListRowGroup>
        </View>

        <View>
          <Text
            style={{
              ...typography.h2,
              marginBottom: spacing.md,
            }}
          >
            Pantry
          </Text>
          <EmptyState
            icon="cart-outline"
            title="All quiet on the home front"
            message="When something's running low, your cook will flag it here for a quick approval."
            hint="Set up auto-rules in Settings"
          />
        </View>
      </ScrollView>
    </SafeScreen>
  );
}
