/**
 * CookActionsSheet — Swiggy MCP cart sheet. Single grocery list with a
 * three-phase commit (review → submitting → success → auto-dismiss),
 * the moment of confirmation that proves the integration is real.
 *
 *   review     → cart-as-cards + "Place order via Swiggy" CTA
 *   submitting → spinner + "Placing order on Swiggy…", side effects fire
 *   success    → green "Order placed on Swiggy ✓", then auto-dismiss
 *
 * Copy is intentionally agentic — Bimi places the order via Swiggy MCP
 * (one tap, no app switch) rather than pointing the user at the Swiggy
 * app. The DemoSimulationBanner above the cart makes the "this is
 * illustrative until MCP access lands" framing unmissable; without
 * that banner this copy would misrepresent today's wired-up state.
 *
 * On success, kicks off `useSwiggyDeliveryStore.placeOrder(items)` so
 * the lifecycle continues into the active-delivery hero (Phase 2 of
 * the demo). Notes from cook (`prep_note`) are filtered upstream by
 * `useUnresolvedCookActions`. Non-grocery decisions (meal_query etc.)
 * still render in a fallback section below the cart for completeness.
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ActivityIndicator, Text, View } from "react-native";
import * as Haptics from "expo-haptics";
import { Ionicons } from "@expo/vector-icons";
import { BottomSheet } from "../ui/BottomSheet";
import { Button } from "../ui/Button";
import { ActionListRow } from "./ActionListRow";
import { GroceryActionRow } from "./GroceryActionRow";
import { SwiggyBadge, SWIGGY_ORANGE } from "./SwiggyBadge";
import { DemoSimulationBanner } from "./DemoSimulationBanner";
import { RipplePressable } from "../RipplePressable";
import { router } from "expo-router";
import {
  useChatStore,
  useHouseholdStore,
  useMealStore,
  useWishlistStore,
} from "@/lib/store";
import { useSwiggyDeliveryStore } from "@/lib/swiggy-delivery-store";
import {
  colors,
  iconSize,
  radius,
  spacing,
  typography,
} from "@/lib/theme";
import type { ActionItem, CookMessage } from "@/lib/types";

type LinkedAction = {
  idx: number;
  message: CookMessage;
  action: ActionItem;
};

type Phase = "review" | "submitting" | "success";

interface CookActionsSheetProps {
  visible: boolean;
  onClose: () => void;
}

const GROCERY_TYPES: ActionItem["type"][] = ["supply_request", "low_stock"];

const SUBMITTING_MS = 600;
const SUCCESS_MS = 1200;

export function CookActionsSheet({ visible, onClose }: CookActionsSheetProps) {
  const messages = useChatStore((s) => s.messages);
  const resolveAction = useChatStore((s) => s.resolveAction);
  const addWishlistItem = useWishlistStore((s) => s.addItem);
  const failPrepAndSwitch = useMealStore((s) => s.failPrepAndSwitch);
  const cookName = useHouseholdStore((s) => s.household?.cooks?.[0]?.name);
  const placeOrder = useSwiggyDeliveryStore((s) => s.placeOrder);

  const [phase, setPhase] = useState<Phase>("review");
  const submitTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const successTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const items: LinkedAction[] = useMemo(() => {
    const out: LinkedAction[] = [];
    for (const m of messages) {
      if (!m.isFromCook) continue;
      m.actionItems.forEach((action, idx) => {
        if (action.resolved) return;
        // `prep_note` items are cook-side concerns — handled during
        // previous-meal prep, not surfaced to the household. Mirrors
        // the upstream filter in `useUnresolvedCookActions`.
        if (action.type === "prep_note") return;
        out.push({ idx, message: m, action });
      });
    }
    return out;
  }, [messages]);

  const groceries = useMemo(
    () => items.filter((it) => GROCERY_TYPES.includes(it.action.type)),
    [items],
  );
  const decisions = useMemo(
    () => items.filter((it) => !GROCERY_TYPES.includes(it.action.type)),
    [items],
  );

  // Note: we do NOT compute / surface a ₹ aggregate here. The Swiggy
  // Builders Club rules forbid surfacing prices we haven't fetched
  // from the real MCP — see DemoSimulationBanner for the disclaimer.
  const cookFirstName = (cookName ?? "Malti").split(" ")[0];

  // Reset to "review" each time the sheet (re-)opens. Without this,
  // closing during success then reopening leaves the user stuck on the
  // green-button screen.
  useEffect(() => {
    if (visible) setPhase("review");
    return () => {
      if (submitTimerRef.current) clearTimeout(submitTimerRef.current);
      if (successTimerRef.current) clearTimeout(successTimerRef.current);
    };
  }, [visible]);

  const resolveOne = useCallback(
    (item: LinkedAction) => {
      const { message, idx, action } = item;
      switch (action.type) {
        case "supply_request":
        case "low_stock": {
          const fallbackName = action.description
            .replace(/^(Order |order |Restock |restock )/i, "")
            .replace(/ — .*$/, "")
            .trim();
          addWishlistItem({
            id: `w-${Date.now()}-${idx}`,
            name: action.itemName ?? fallbackName ?? action.description,
            quantity: action.quantity ?? 1,
            unit: action.unit ?? "pack",
            source: "cook",
            addedBy: action.requestedBy ?? cookName ?? "Cook",
            addedAt: new Date().toISOString(),
            priority: action.type === "low_stock" ? "urgent" : "normal",
            status: "pending",
            category: "Other",
          });
          resolveAction(message.id, idx);
          break;
        }
        case "prep_failed":
          failPrepAndSwitch();
          resolveAction(message.id, idx);
          break;
        case "meal_query":
        case "absence":
        case "prep_note":
        default:
          resolveAction(message.id, idx);
          break;
      }
    },
    [addWishlistItem, cookName, failPrepAndSwitch, resolveAction],
  );

  const onAddCart = useCallback(() => {
    if (phase !== "review" || groceries.length === 0) return;
    setPhase("submitting");
    Haptics.selectionAsync().catch(() => {});

    // Resolve cart items + place the Swiggy order at the START of
    // submitting so the data settles before the success state. This
    // also kicks off the lifecycle's active-delivery hero behind us.
    const cartActions = groceries.map((g) => g.action);
    groceries.forEach(resolveOne);
    placeOrder(cartActions);

    submitTimerRef.current = setTimeout(() => {
      setPhase("success");
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(
        () => {},
      );
      successTimerRef.current = setTimeout(() => {
        onClose();
      }, SUCCESS_MS);
    }, SUBMITTING_MS);
  }, [phase, groceries, resolveOne, placeOrder, onClose]);

  const handleSeeAll = useCallback(() => {
    onClose();
    router.push("/cook-chat" as never);
  }, [onClose]);

  return (
    <BottomSheet
      visible={visible}
      onClose={onClose}
      title="Cook's grocery list"
      subtitle={`${groceries.length} items in your cook's basket`}
      titleAccessory={<SwiggyBadge size="inline" />}
      scrollable
    >
      {/* Cook attribution — small line above the cards */}
      {groceries.length > 0 ? (
        <Text
          style={{
            ...typography.tiny,
            color: colors.text.muted,
            marginBottom: spacing.sm,
          }}
        >
          Curated by {cookFirstName} this morning
        </Text>
      ) : null}

      {/* Compliance disclaimer — surfaced before the cart so reviewers
          (and users) see it before any Swiggy-attributed UI. */}
      {groceries.length > 0 ? (
        <View style={{ marginBottom: spacing.md }}>
          <DemoSimulationBanner variant="inline" />
        </View>
      ) : null}

      {/* Grocery cart */}
      {groceries.length > 0 ? (
        <View style={{ gap: spacing.md }}>
          {groceries.map((item) => (
            <GroceryActionRow
              key={`${item.message.id}-${item.idx}`}
              action={item.action}
            />
          ))}
        </View>
      ) : (
        <View style={{ paddingVertical: spacing.lg, alignItems: "center" }}>
          <Text style={{ ...typography.caption, color: colors.text.muted }}>
            No grocery items pending.
          </Text>
        </View>
      )}

      {/* Decisions (non-grocery) — kept as the legacy per-row pattern
          so meal_query / absence / prep_failed paths still work. Only
          renders when those types appear (rare in the demo seed). */}
      {decisions.length > 0 ? (
        <View style={{ marginTop: spacing.lg, gap: spacing.xs }}>
          <Text
            style={{
              ...typography.smallBold,
              color: colors.text.muted,
              textTransform: "uppercase",
              letterSpacing: 0.8,
              marginBottom: spacing.xs,
            }}
          >
            Decisions needed · {decisions.length}
          </Text>
          {decisions.map((item) => (
            <ActionListRow
              key={`${item.message.id}-${item.idx}`}
              icon={iconFor(item.action.type)}
              iconTone={toneFor(item.action.type)}
              title={item.action.description}
              action={{
                label: ctaLabelFor(item.action.type),
                onPress: () => resolveOne(item),
              }}
              secondaryAction={
                item.action.type === "meal_query" || item.action.type === "absence"
                  ? { label: "Discuss in chat", onPress: handleSeeAll }
                  : undefined
              }
            />
          ))}
        </View>
      ) : null}

      {/* Footer — summary line + unified Swiggy CTA + escape hatch */}
      <View style={{ marginTop: spacing.xl }}>
        <View
          style={{
            height: 1,
            backgroundColor: colors.border.muted,
            marginBottom: spacing.md,
          }}
        />
        {groceries.length > 0 ? (
          <>
            <Text
              style={{
                ...typography.caption,
                color: colors.text.secondary,
                textAlign: "center",
                marginBottom: spacing.sm,
              }}
            >
              Bimi places this on Swiggy and tracks it for you
            </Text>
            <SwiggyCartButton
              phase={phase}
              label="Place order via Swiggy"
              onPress={onAddCart}
            />
          </>
        ) : null}
        <View style={{ marginTop: spacing.sm }}>
          <Button variant="ghost" fullWidth onPress={handleSeeAll}>
            See in chat
          </Button>
        </View>
      </View>
    </BottomSheet>
  );
}

/**
 * The cart CTA. Morphs through three visual states driven by `phase`:
 *
 *   review     → orange "Place order via Swiggy"
 *   submitting → orange + spinner + "Placing order on Swiggy…"
 *   success    → green + check + "Order placed on Swiggy ✓"
 *
 * Disabled (non-pressable) outside `review` so the user can't double-tap.
 */
function SwiggyCartButton({
  phase,
  label,
  onPress,
}: {
  phase: Phase;
  label: string;
  onPress: () => void;
}) {
  const isReview = phase === "review";
  const isSubmitting = phase === "submitting";
  const isSuccess = phase === "success";

  const bg = isSuccess ? colors.accent.success : SWIGGY_ORANGE;
  const labelText = isSuccess
    ? "Order placed on Swiggy ✓"
    : isSubmitting
      ? "Placing order on Swiggy…"
      : label;

  const content = (
    <View
      style={{
        backgroundColor: bg,
        borderRadius: radius.md,
        height: 56,
        paddingHorizontal: spacing.lg,
        flexDirection: "row",
        alignItems: "center",
        justifyContent: "center",
        gap: spacing.sm,
      }}
    >
      {isSuccess ? (
        <Ionicons
          name="checkmark-circle"
          size={iconSize.md}
          color={colors.text.inverse}
        />
      ) : isSubmitting ? (
        <ActivityIndicator color={colors.text.inverse} />
      ) : (
        <SwiggyBadge size="cta" />
      )}
      <Text
        style={{ ...typography.bodyBold, color: colors.text.inverse }}
        numberOfLines={1}
      >
        {labelText}
      </Text>
    </View>
  );

  if (!isReview) {
    return content;
  }

  return (
    <RipplePressable
      onPress={onPress}
      haptic="medium"
      accessibilityRole="button"
      accessibilityLabel={label}
      testID="cta-add-to-swiggy-cart"
    >
      {content}
    </RipplePressable>
  );
}

function ctaLabelFor(type: ActionItem["type"]): string {
  switch (type) {
    case "supply_request":
    case "low_stock":      return "Add";
    case "meal_query":     return "Yes, go ahead";
    case "absence":        return "Acknowledge";
    case "prep_failed":    return "Switch meal";
    case "prep_note":
    default:               return "Got it";
  }
}

function iconFor(type: ActionItem["type"]) {
  switch (type) {
    case "supply_request": return "cart-outline" as const;
    case "low_stock":      return "warning-outline" as const;
    case "meal_query":     return "restaurant-outline" as const;
    case "absence":        return "calendar-outline" as const;
    case "prep_failed":    return "alert-circle-outline" as const;
    case "prep_note":
    default:               return "bulb-outline" as const;
  }
}

function toneFor(type: ActionItem["type"]) {
  switch (type) {
    case "supply_request":
    case "low_stock":      return "warning" as const;
    case "meal_query":     return "primary" as const;
    case "absence":        return "info" as const;
    case "prep_failed":    return "danger" as const;
    case "prep_note":
    default:               return "neutral" as const;
  }
}
