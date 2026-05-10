import React from "react";
import { View, Text, TouchableOpacity } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, cardStyles, elevation, radius, spacing, typography } from "@/lib/theme";
import { haptic } from "@/lib/haptics";
import type { Order } from "@/lib/types";

interface ApprovalCardProps {
  order: Order;
  /** Receives the order id so the handler can be a stable ref at the
   *  call site (no per-cell arrow lambda needed — preserves memo). */
  onApprove?: (orderId: string) => void;
  onReject?: (orderId: string) => void;
}

function formatTimeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

const STATUS_CONFIG = {
  pending: { accent: colors.accent.secondary, icon: "time" as const, label: "Pending Approval" },
  auto_approved: { accent: colors.accent.success, icon: "flash" as const, label: "Auto-Approved" },
  approved: { accent: colors.accent.success, icon: "checkmark-circle" as const, label: "Approved" },
  rejected: { accent: colors.accent.danger, icon: "close-circle" as const, label: "Rejected" },
  ordered: { accent: colors.accent.info, icon: "cube" as const, label: "Ordered" },
  delivered: { accent: colors.accent.success, icon: "checkmark-done-circle" as const, label: "Delivered" },
};

function ApprovalCardImpl({ order, onApprove, onReject }: ApprovalCardProps) {
  const config = STATUS_CONFIG[order.status];

  return (
    <View
      style={{
        ...cardStyles,
        ...elevation.low,
        marginBottom: spacing.md,
        borderLeftWidth: 4,
        borderLeftColor: config.accent,
      }}
    >
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.md, gap: spacing.sm }}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, flex: 1, minWidth: 0 }}>
          <Ionicons name={config.icon} size={18} color={config.accent} />
          <Text style={{ ...typography.captionBold, color: config.accent }} numberOfLines={1}>{config.label}</Text>
        </View>
        <Text style={{ ...typography.small, flexShrink: 0 }}>{formatTimeAgo(order.requestedAt)}</Text>
      </View>

      <View style={{ flexDirection: "row", alignItems: "center", gap: 6, marginBottom: spacing.sm }}>
        <Text style={typography.small}>Requested by</Text>
        <Text style={typography.bodyBold}>{order.requestedBy}</Text>
      </View>

      <View style={{ gap: 6, marginBottom: spacing.md }}>
        {order.items.map((item) => (
          <View key={item.id} style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
            <Text style={{ ...typography.body, flex: 1 }}>
              {item.name} <Text style={{ color: colors.text.secondary }}>×{item.quantity}</Text>
            </Text>
            <Text style={typography.bodyBold}>₹{item.estimatedPrice}</Text>
          </View>
        ))}
      </View>

      <View
        style={{
          flexDirection: "row",
          justifyContent: "space-between",
          alignItems: "center",
          paddingTop: spacing.sm,
          borderTopWidth: 1,
          borderTopColor: colors.border.subtle,
        }}
      >
        <Text style={{ fontSize: 18, fontWeight: "700", color: colors.accent.primary }}>₹{order.totalAmount}</Text>

        {order.status === "pending" && onApprove && onReject && (
          <View style={{ flexDirection: "row", gap: spacing.sm }}>
            <TouchableOpacity
              onPress={() => { haptic("warning"); onReject?.(order.id); }}
              accessibilityRole="button"
              accessibilityLabel={`Decline order for \u20b9${order.totalAmount}`}
              style={{ paddingHorizontal: 16, paddingVertical: 10, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border.subtle, minHeight: 44, justifyContent: "center" }}
            >
              <Text style={{ ...typography.bodyBold, color: colors.text.secondary }}>Decline</Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={() => { haptic("success"); onApprove?.(order.id); }}
              accessibilityRole="button"
              accessibilityLabel={`Approve order for \u20b9${order.totalAmount}`}
              style={{ flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 16, paddingVertical: 10, borderRadius: radius.sm, backgroundColor: colors.accent.success, minHeight: 44 }}
            >
              <Ionicons name="checkmark" size={18} color={colors.text.inverse} />
              <Text style={{ ...typography.bodyBold, color: colors.text.inverse }}>Approve</Text>
            </TouchableOpacity>
          </View>
        )}

        {order.status === "auto_approved" && order.autoApprovalReason && (
          <View style={{ flexDirection: "row", alignItems: "center", gap: 4, flex: 1, justifyContent: "flex-end" }}>
            <Ionicons name="flash" size={14} color={colors.accent.success} />
            <Text style={{ ...typography.tiny, color: colors.accent.success }} numberOfLines={2}>{order.autoApprovalReason}</Text>
          </View>
        )}

        {order.status === "approved" && order.approvedBy && (
          <Text style={{ ...typography.small, color: colors.accent.success }}>by {order.approvedBy}</Text>
        )}
      </View>
    </View>
  );
}

/**
 * Memoised so an order list doesn't re-render every cell when one card's
 * status flips. Order is a stable reference from the Zustand store, so
 * shallow prop comparison is the right default.
 */
export const ApprovalCard = React.memo(ApprovalCardImpl);
