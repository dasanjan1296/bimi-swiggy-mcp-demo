import React, { useCallback, useMemo } from "react";
import { View, Text, SectionList, TouchableOpacity } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useNotificationStore, type NotificationType } from "@/lib/notifications";
import { GradientScreen } from "@/components/GradientScreen";
import { EmptyStateGuide } from "@/components/GuidanceTip";
import { colors, spacing, radius, typography } from "@/lib/theme";
import { haptic } from "@/lib/haptics";

const NOTIF_CONFIG: Record<string, { icon: keyof typeof Ionicons.glyphMap; color: string }> = {
  order_pending: { icon: "cart", color: colors.accent.danger },
  order_approved: { icon: "checkmark-circle", color: colors.accent.success },
  order_auto_approved: { icon: "flash", color: colors.accent.success },
  cook_message: { icon: "chatbubble-ellipses", color: colors.text.secondary },
  prep_reminder: { icon: "bulb", color: colors.accent.warning },
  low_stock: { icon: "warning", color: colors.accent.danger },
  vote_reminder: { icon: "thumbs-up", color: colors.accent.success },
  meal_finalized: { icon: "restaurant", color: colors.accent.info },
  member_joined: { icon: "person-add", color: colors.accent.success },
  member_left: { icon: "person-remove", color: colors.text.muted },
  member_removed: { icon: "person-remove", color: colors.accent.danger },
  vote_cast: { icon: "hand-left", color: colors.accent.danger },
  all_voted: { icon: "people", color: colors.accent.success },
  approval_needed: { icon: "alert-circle", color: colors.accent.danger },
  partner_approved: { icon: "checkmark", color: colors.accent.success },
  expense_settled: { icon: "cash", color: colors.accent.info },
  you_owe: { icon: "wallet", color: colors.accent.danger },
  you_are_owed: { icon: "wallet", color: colors.accent.success },
  cook_changed: { icon: "swap-horizontal", color: colors.text.muted },
  proxy_vote_cast: { icon: "hardware-chip", color: colors.text.muted },
  voting_deadline_reminder: { icon: "time", color: colors.accent.danger },
  ingredients_missing: { icon: "alert", color: colors.accent.danger },
  ingredients_ordered: { icon: "cube", color: colors.accent.success },
  morning_readiness: { icon: "sunny", color: colors.accent.info },
  prep_user_needed: { icon: "warning", color: colors.accent.warning },
  prep_check: { icon: "help-circle", color: colors.accent.primary },
  prep_failed_auto_switch: { icon: "swap-horizontal", color: colors.accent.info },
};

function formatTimeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(dateStr).toLocaleDateString("en-IN", { month: "short", day: "numeric" });
}

type Notification = ReturnType<typeof useNotificationStore.getState>["notifications"][number];

interface NotificationRowProps {
  notif: Notification;
  onPress: (id: string) => void;
}

/**
 * Memoised row so SectionList's virtualized recycling actually wins.
 * Without memo, the cell prop diff is "everything changed" and React
 * re-renders even cells that scrolled off-screen-and-back unchanged.
 */
const NotificationRow = React.memo(function NotificationRow({
  notif,
  onPress,
}: NotificationRowProps) {
  const config = NOTIF_CONFIG[notif.type] || { icon: "ellipse" as const, color: colors.text.muted };
  // Bind id once per cell render — cheaper than a fresh closure at the
  // call site, and recreating the wrapper inside the memoised cell
  // doesn't bust upstream memo on the SectionList itself.
  const handlePress = () => onPress(notif.id);
  return (
    <TouchableOpacity
      onPress={handlePress}
      activeOpacity={0.7}
      accessibilityRole="button"
      accessibilityState={{ selected: !notif.read }}
      accessibilityLabel={`${notif.read ? "Read" : "Unread"} notification: ${notif.title}. ${notif.body}`}
      style={{
        flexDirection: "row",
        gap: spacing.md,
        backgroundColor: notif.read ? colors.surface.card : colors.surface.elevated,
        borderRadius: radius.md,
        padding: spacing.md,
        marginBottom: spacing.sm,
        borderWidth: 1,
        borderColor: notif.read ? colors.border.subtle : `${config.color}30`,
        opacity: notif.read ? 0.7 : 1,
      }}
    >
      <View
        style={{
          width: 36,
          height: 36,
          borderRadius: 18,
          backgroundColor: `${config.color}18`,
          justifyContent: "center",
          alignItems: "center",
          marginTop: 2,
        }}
      >
        <Ionicons name={config.icon} size={18} color={config.color} />
      </View>
      <View style={{ flex: 1 }}>
        <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start" }}>
          <Text style={{ ...typography.bodyBold, flex: 1, marginRight: spacing.sm }}>{notif.title}</Text>
          <Text style={typography.tiny}>{formatTimeAgo(notif.timestamp)}</Text>
        </View>
        <Text style={{ ...typography.caption, marginTop: 3 }}>{notif.body}</Text>
        {notif.actionLabel && !notif.read && (
          <View style={{ flexDirection: "row", alignItems: "center", gap: 4, marginTop: 6 }}>
            <Text style={{ ...typography.captionBold, color: config.color }}>{notif.actionLabel}</Text>
            <Ionicons name="arrow-forward" size={12} color={config.color} />
          </View>
        )}
      </View>
    </TouchableOpacity>
  );
});

export default function NotificationsScreen() {
  const router = useRouter();
  const notifications = useNotificationStore((s) => s.notifications);
  const markRead = useNotificationStore((s) => s.markRead);
  const markAllRead = useNotificationStore((s) => s.markAllRead);
  const unreadCount = useMemo(
    () => notifications.filter((n) => !n.read).length,
    [notifications],
  );

  // Stable handler so the memoised NotificationRow isn't busted on every
  // render. Receives id (not the whole notif object) to keep the prop
  // surface narrow.
  const handleTap = useCallback(
    (id: string) => {
      const notif = notifications.find((n) => n.id === id);
      if (!notif) return;
      haptic("light");
      markRead(notif.id);
      if (notif.actionRoute) {
        router.push(notif.actionRoute as any);
      }
    },
    [notifications, markRead, router],
  );

  const sections = useMemo(() => {
    if (notifications.length === 0) return [];
    const sorted = [...notifications].sort(
      (a, b) => new Date(b.timestamp || 0).getTime() - new Date(a.timestamp || 0).getTime(),
    );
    const today = new Date();
    const todayStr = today.toDateString();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);
    const yesterdayStr = yesterday.toDateString();
    const out: { title: string; data: typeof sorted }[] = [];
    const todayItems = sorted.filter((n) => new Date(n.timestamp).toDateString() === todayStr);
    const yesterdayItems = sorted.filter((n) => new Date(n.timestamp).toDateString() === yesterdayStr);
    const earlierItems = sorted.filter((n) => {
      const d = new Date(n.timestamp).toDateString();
      return d !== todayStr && d !== yesterdayStr;
    });
    if (todayItems.length > 0) out.push({ title: "Today", data: todayItems });
    if (yesterdayItems.length > 0) out.push({ title: "Yesterday", data: yesterdayItems });
    if (earlierItems.length > 0) out.push({ title: "Earlier", data: earlierItems });
    return out;
  }, [notifications]);

  const Header = (
    <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.xl }}>
      <View>
        <Text style={typography.h1}>Notifications</Text>
        {unreadCount > 0 && (
          <Text style={{ ...typography.caption, color: colors.accent.primary, marginTop: 2 }}>
            {unreadCount} unread
          </Text>
        )}
      </View>
      {unreadCount > 0 && (
        <TouchableOpacity
          onPress={() => {
            haptic("selection");
            markAllRead();
          }}
          accessibilityRole="button"
          accessibilityLabel="Mark all notifications as read"
          style={{
            paddingHorizontal: 12,
            paddingVertical: 6,
            backgroundColor: colors.surface.card,
            borderRadius: radius.sm,
            borderWidth: 1,
            borderColor: colors.border.subtle,
          }}
        >
          <Text style={{ ...typography.captionBold, color: colors.text.secondary }}>Mark all read</Text>
        </TouchableOpacity>
      )}
    </View>
  );

  const renderItem = useCallback(
    ({ item }: { item: Notification }) => <NotificationRow notif={item} onPress={handleTap} />,
    [handleTap],
  );

  const renderSectionHeader = useCallback(
    ({ section }: { section: { title: string } }) => (
      <Text
        style={{
          ...typography.smallBold,
          color: colors.text.secondary,
          textTransform: "uppercase",
          letterSpacing: 1,
          marginBottom: spacing.sm,
          marginTop: spacing.md,
        }}
      >
        {section.title}
      </Text>
    ),
    [],
  );

  return (
    <GradientScreen>
      <SectionList
        sections={sections}
        keyExtractor={(item) => item.id}
        renderItem={renderItem}
        renderSectionHeader={renderSectionHeader}
        ListHeaderComponent={Header}
        ListEmptyComponent={
          <EmptyStateGuide
            icon="notifications-off-outline"
            title="All caught up!"
            message="No notifications yet. You'll see meal updates, cook messages, and order alerts here."
            hint="Notifications appear as your household uses Bimi"
          />
        }
        stickySectionHeadersEnabled={false}
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: 120 }}
        // Virtualization tuning — most users have <50 notifications so
        // the defaults are fine, but bumping initialNumToRender keeps
        // the first paint flicker-free for fresh installs that have a
        // backlog from push-history.
        initialNumToRender={12}
        windowSize={5}
        removeClippedSubviews
      />
    </GradientScreen>
  );
}
