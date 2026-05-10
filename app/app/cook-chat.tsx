import { View, Text, ScrollView, TouchableOpacity, KeyboardAvoidingView, Platform, TextInput } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRef, useState, useEffect } from "react";
import { useChatStore, useHouseholdStore, useWishlistStore, useMealStore, useInventoryStore } from "@/lib/store";
import { useNotificationStore } from "@/lib/notifications";
import { CookMessageBubble } from "@/components/CookMessage";
import { GuidanceTip, EmptyStateGuide } from "@/components/GuidanceTip";
import { colors, radius, spacing } from "@/lib/theme";
import { RipplePressable } from "@/components/RipplePressable";
import { shareWithCook } from "@/lib/whatsapp-share";

export default function CookChatScreen() {
  const messages = useChatStore((s) => s.messages);
  const simulateCookMessage = useChatStore((s) => s.simulateCookMessage);
  const resolveAction = useChatStore((s) => s.resolveAction);
  const addMessage = useChatStore((s) => s.addMessage);
  const household = useHouseholdStore((s) => s.household);
  const addWishlistItem = useWishlistStore((s) => s.addItem);
  const addNotification = useNotificationStore((s) => s.addNotification);
  const scrollRef = useRef<ScrollView>(null);
  const [replyText, setReplyText] = useState("");

  const handleSuggestMeal = (description: string) => {
    const dishName = description.replace(/^(What to cook|what should I make|What to make)/i, "").replace(/\?/g, "").replace(/for (lunch|dinner|breakfast)/i, "").trim() || description;
    const activeMealType = useMealStore.getState().activeMealType;
    useMealStore.getState().addSuggestion(activeMealType, {
      id: `cook-suggest-${Date.now()}`,
      dishName: dishName.length > 3 ? dishName : "Cook's Pick",
      confidence: 0.8,
      fairnessScore: 0.5,
      noveltyBonus: 0.2,
      constraints: [],
      prepTime: "30 min",
      needsAdvancePrep: false,
      ingredients: [],
      missingIngredients: [],
    });
    addNotification({ type: "meal_finalized", title: "Cook Suggestion", body: `Cook suggested a dish — check the Vote tab.` });
  };

  const handleAddToWishlist = (description: string) => {
    const itemName = description.replace(/^(Order |order |Restock |restock )/i, "").replace(/ — .*$/, "").trim();
    const inventoryItems = useInventoryStore.getState().items;
    const matchingItem = inventoryItems.find(
      (inv) => inv.isLowStock && inv.estimatedDaysLeft <= 1 && itemName.toLowerCase().includes(inv.name.toLowerCase()),
    );
    const priority = matchingItem ? "urgent" : "normal";
    addWishlistItem({
      id: `w-${Date.now()}`, name: itemName || description, quantity: 1, unit: "pack",
      source: "cook", addedBy: household?.cooks?.[0]?.name || "Cook",
      addedAt: new Date().toISOString(), priority, status: "pending", category: "Other",
    });
    addNotification({ type: "low_stock", title: "Added to Wishlist", body: `${itemName} added from cook's message.${matchingItem ? " (Urgent — low stock)" : ""}` });
  };

  useEffect(() => {
    const timer = setTimeout(() => scrollRef.current?.scrollToEnd({ animated: false }), 100);
    return () => clearTimeout(timer);
  }, [messages.length]);

  const primaryCook = household?.cooks?.[0];

  const handleSendReply = () => {
    if (!replyText.trim()) return;
    const text = replyText.trim();
    addMessage({
      id: `msg-reply-${Date.now()}`,
      type: "text",
      content: text,
      timestamp: new Date().toISOString(),
      actionItems: [],
      isFromCook: false,
    });
    shareWithCook(primaryCook?.whatsappNumber, text);
    setReplyText("");
  };

  const unresolvedCount = messages
    .flatMap((m) => m.actionItems)
    .filter((a) => !a.resolved).length;

  return (
    <KeyboardAvoidingView
      // Warm-cream screen canvas; the sticky header + composer below
      // intentionally stay surface.base (white) to read as elevated
      // chrome over the message area.
      style={{ flex: 1, backgroundColor: colors.surface.warm }}
      behavior={Platform.OS === "ios" ? "padding" : "height"}
      keyboardVerticalOffset={90}
    >
      {/* Header Info */}
      <View
        style={{
          backgroundColor: colors.surface.base,
          paddingHorizontal: spacing.lg,
          paddingVertical: 12,
          paddingTop: 56,
          borderBottomWidth: 1,
          borderBottomColor: colors.border.subtle,
          flexDirection: "row",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <View style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
          <View
            style={{
              width: 40,
              height: 40,
              borderRadius: 20,
              backgroundColor: colors.accent.primaryDim,
              justifyContent: "center",
              alignItems: "center",
            }}
          >
            <Ionicons name="restaurant" size={20} color={colors.accent.primary} />
          </View>
          <View>
            <Text style={{ fontSize: 15, fontWeight: "700", color: colors.text.primary }}>
              {household?.cooks?.[0]?.name || "Cook"}
            </Text>
            <Text style={{ fontSize: 12, color: colors.text.muted }}>via WhatsApp</Text>
          </View>
        </View>

        {unresolvedCount > 0 && (
          <View
            style={{
              flexDirection: "row",
              alignItems: "center",
              gap: 4,
              backgroundColor: colors.accent.primaryDim,
              borderRadius: radius.sm,
              paddingHorizontal: 8,
              paddingVertical: 4,
              borderWidth: 1,
              borderColor: colors.border.active,
            }}
          >
            <Ionicons name="alert-circle" size={14} color={colors.accent.primary} />
            <Text style={{ fontSize: 12, fontWeight: "600", color: colors.accent.primary }}>
              {unresolvedCount} action{unresolvedCount > 1 ? "s" : ""}
            </Text>
          </View>
        )}
      </View>

      {/* Messages */}
      <ScrollView
        ref={scrollRef}
        style={{ flex: 1 }}
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: 8 }}
        onContentSizeChange={() => scrollRef.current?.scrollToEnd({ animated: true })}
      >
        {/* Date Separator */}
        <View style={{ alignItems: "center", marginBottom: spacing.lg }}>
          <View style={{ backgroundColor: colors.surface.elevated, borderRadius: radius.sm, paddingHorizontal: 12, paddingVertical: 4 }}>
            <Text style={{ fontSize: 11, fontWeight: "600", color: colors.text.secondary }}>Today</Text>
          </View>
        </View>

        {messages.length === 0 ? (
          <View>
            <EmptyStateGuide
              icon="chatbubble-ellipses-outline"
            title="No messages yet"
            message="When your cook sends a WhatsApp message — voice note, text, Hindi or English — I'll translate it and show it here with anything that needs your attention."
              hint={'Tap "Simulate Cook Message" below to see how it works'}
            />
            <View style={{ marginTop: 16, marginHorizontal: 8 }}>
              <GuidanceTip
                variant="info"
                icon="language"
              title="I handle the translation"
              message="Voice notes get transcribed and translated from Hindi. I pull out what matters — grocery requests, questions, things that need your attention."
                compact
              />
            </View>
          </View>
        ) : (
          messages.map((msg) => (
            <CookMessageBubble
              key={msg.id}
              message={msg}
              onResolveAction={(idx) => resolveAction(msg.id, idx)}
              onAddToWishlist={handleAddToWishlist}
              onSuggestMeal={handleSuggestMeal}
            />
          ))
        )}
      </ScrollView>

      {/* Cook Simulator + Reply */}
      <View
        style={{
          backgroundColor: colors.surface.base,
          borderTopWidth: 1,
          borderTopColor: colors.border.subtle,
          padding: 12,
          gap: 8,
        }}
      >
        {/* Simulate Button */}
        {__DEV__ && (
        <TouchableOpacity
          onPress={() => {
            simulateCookMessage();
            addNotification({
              type: "cook_message",
              title: `${household?.cooks?.[0]?.name || "Cook"} sent a message`,
              body: "New message from cook. Tap to view.",
              actionRoute: "/cook-chat",
              actionLabel: "View Message",
            });
          }}
          style={{
            backgroundColor: colors.accent.primaryDim,
            borderRadius: radius.md,
            paddingVertical: 10,
            alignItems: "center",
            flexDirection: "row",
            justifyContent: "center",
            gap: 6,
            borderWidth: 1,
            borderColor: colors.border.active,
          }}
        >
          <Ionicons name="chatbubble-ellipses" size={16} color={colors.accent.primary} />
          <Text style={{ fontSize: 13, fontWeight: "600", color: colors.accent.primary }}>
            Preview a cook message
          </Text>
        </TouchableOpacity>
        )}

        {/* Reply Input */}
        <View style={{ flexDirection: "row", gap: 8, alignItems: "flex-end" }}>
          <TextInput
            value={replyText}
            onChangeText={setReplyText}
            placeholder="Reply to cook..."
            placeholderTextColor={colors.text.muted}
            accessibilityLabel="Reply to cook"
            autoCapitalize="sentences"
            multiline
            style={{
              flex: 1,
              backgroundColor: colors.surface.glass,
              borderRadius: radius.pill,
              paddingHorizontal: 16,
              paddingVertical: 10,
              fontSize: 14,
              color: colors.text.primary,
              maxHeight: 100,
              borderWidth: 1,
              borderColor: colors.border.subtle,
            }}
          />
          <View style={{ alignItems: "center", gap: 2 }}>
            <TouchableOpacity
              onPress={handleSendReply}
              disabled={!replyText.trim()}
              accessibilityRole="button"
              accessibilityLabel="Send reply via WhatsApp"
              accessibilityState={{ disabled: !replyText.trim() }}
              style={{
                width: 40,
                height: 40,
                borderRadius: 20,
                backgroundColor: replyText.trim() ? colors.accent.primary : colors.surface.elevated,
                justifyContent: "center",
                alignItems: "center",
              }}
            >
              <Ionicons name="send" size={18} color={replyText.trim() ? colors.text.inverse : colors.text.muted} />
            </TouchableOpacity>
            <Text style={{ fontSize: 9, color: colors.text.muted }}>via WhatsApp</Text>
          </View>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}
