/**
 * Cook brief — the cook's surface, not the household's.
 *
 * Reachable two ways:
 *   1. A signed deep-link sent to the cook's phone via WhatsApp every
 *      morning at 7am: "Aaj ka plan ↗" → opens this screen scoped to
 *      her active household for today.
 *   2. From inside the app, by the kitchen lead, for previewing what
 *      didi will see (Settings → Cook profile → Preview today's brief).
 *
 * This is *the cook's* UX, so the design rules diverge from the rest
 * of the app:
 *   - Hindi-first copy where possible (English fallback).
 *   - Big tap targets, large type — assumes a 5" Android in Hindi.
 *   - Voice-note primary input ("Mic dabake bolo, Bimi sun rahi hai").
 *   - Three quick actions: "Need this" / "I'll be late" / "I'm off
 *     tomorrow" — covering ~80% of cook-side messages without typing.
 *   - No tabs, no nested navigation — single screen.
 *
 * The bridge to the rest of the app is `lib/whatsapp-intents.ts`:
 * every action here produces an `InboundIntent` that flows back through
 * the same handler the WhatsApp webhook uses, so cook-side reports
 * land in the household's data the same way regardless of channel.
 */

import React, { useMemo, useState } from "react";
import {
  ScrollView,
  Text,
  View,
} from "react-native";
import { useLocalSearchParams } from "expo-router";
import { useChatStore, useHouseholdStore, useMealStore } from "@/lib/store";
import { Button, IconButton, SafeScreen } from "@/components/ui";
import { Card, GuidanceTip } from "@/components/patterns";
import { showAlert } from "@/lib/dialogs";
import { haptic } from "@/lib/haptics";
import { safeBack } from "@/lib/safe-back";
import {
  colors,
  fontFamily,
  iconSize,
  radius,
  spacing,
  typography,
} from "@/lib/theme";

const MEAL_LABELS_HI: Record<string, string> = {
  breakfast: "Subah",
  lunch: "Dopahar",
  dinner: "Raat",
  snack: "Snack",
};

export default function CookBriefScreen() {
  const params = useLocalSearchParams<{ date?: string; preview?: string }>();
  const isPreview = params.preview === "1";

  const household = useHouseholdStore((s) => s.household);
  const todaysPlans = useMealStore((s) => s.todaysPlans);
  const addMessage = useChatStore((s) => s.addMessage);

  const cook = household?.cooks?.[0];
  const portions = useMemo(
    () => (household?.members.filter((m) => m.isActive) || []).length || 2,
    [household],
  );

  const dateLabel = useMemo(() => {
    const d = params.date ? new Date(params.date) : new Date();
    return d.toLocaleDateString("en-IN", {
      weekday: "long",
      day: "numeric",
      month: "long",
    });
  }, [params.date]);

  const [voiceRecording, setVoiceRecording] = useState(false);

  // ── Quick action handlers ─────────────────────────────────────────
  // Each emits a CookMessage with the appropriate ActionItem, mirroring
  // what the WhatsApp NLU pipeline would emit if didi sent the same
  // message via WhatsApp. The household's lead sees these in the cook
  // actions sheet on home.

  const reportLowStock = (itemHint?: string) => {
    haptic("selection");
    addMessage({
      id: `cb-${Date.now()}-stock`,
      type: "text",
      content: itemHint
        ? `Need: ${itemHint}`
        : "Cook flagged something running low (open chat for details)",
      timestamp: new Date().toISOString(),
      isFromCook: true,
      actionItems: [
        {
          type: "low_stock",
          description: itemHint || "Cook flagged something running low",
          resolved: false,
        },
      ],
    });
    showAlert("Bimi sun li", "Ghar wale ko bata diya jaayega.");
  };

  const reportRunningLate = (minutes: number) => {
    haptic("selection");
    addMessage({
      id: `cb-${Date.now()}-late`,
      type: "text",
      content: `Cook will be ~${minutes} min late`,
      timestamp: new Date().toISOString(),
      isFromCook: true,
      actionItems: [
        {
          type: "prep_note",
          description: `Cook will be ~${minutes} min late today`,
          resolved: false,
        },
      ],
    });
    showAlert("Bimi sun li", `${minutes} minute late ka message bhej diya.`);
  };

  const reportAbsenceTomorrow = () => {
    haptic("warning");
    addMessage({
      id: `cb-${Date.now()}-absent`,
      type: "text",
      content: "Kal nahi aa paungi",
      timestamp: new Date().toISOString(),
      isFromCook: true,
      actionItems: [
        {
          type: "absence",
          description: "Cook flagged absence for tomorrow",
          resolved: false,
        },
      ],
    });
    showAlert(
      "Bimi sun li",
      "Ghar wale ko bata diya jaayega. They'll arrange something.",
    );
  };

  return (
    <SafeScreen>
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{
          padding: spacing.lg,
          paddingBottom: spacing.xxxl,
          gap: spacing.lg,
        }}
      >
        {/* Header — large, friendly, Hindi-first. The kitchen lead's
            ScreenHeader pattern doesn't fit; cook's surface needs more
            warmth and less navigation chrome. */}
        <View
          style={{
            flexDirection: "row",
            alignItems: "center",
            gap: spacing.md,
          }}
        >
          {isPreview ? (
            <IconButton
              icon="chevron-back"
              onPress={() => safeBack()}
              accessibilityLabel="Back"
              size="sm"
            />
          ) : null}
          <View style={{ flex: 1 }}>
            <Text style={typography.h2}>Namaste{cook ? `, ${cook.name}` : ""}</Text>
            <Text style={typography.caption}>{dateLabel}</Text>
          </View>
        </View>

        {isPreview && (
          <GuidanceTip
            variant="info"
            compact
            message="Preview — this is what your cook sees on her phone."
          />
        )}

        {/* Today's plan, in big readable cards. */}
        <View style={{ gap: spacing.md }}>
          <Text style={{ ...typography.smallBold, color: colors.text.muted, textTransform: "uppercase", letterSpacing: 0.8 }}>
            Aaj ka plan
          </Text>

          {todaysPlans.length === 0 ? (
            <Card variant="flat">
              <Text style={typography.body}>
                Plan abhi tak set nahi hua. Ghar wale tay karenge.
              </Text>
            </Card>
          ) : (
            todaysPlans.map((plan) => (
              <Card key={plan.id} variant="flat">
                <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
                  <View
                    style={{
                      width: 56,
                      height: 56,
                      borderRadius: radius.md,
                      backgroundColor: colors.accent.primaryDim,
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    <Text style={{ ...typography.h3, color: colors.accent.primary }}>
                      {(MEAL_LABELS_HI[plan.mealType] || plan.mealType).slice(0, 1)}
                    </Text>
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={{ ...typography.smallBold, color: colors.text.muted, textTransform: "uppercase" }}>
                      {MEAL_LABELS_HI[plan.mealType] || plan.mealType}
                    </Text>
                    <Text style={{ ...typography.h3, marginTop: 2 }}>
                      {plan.selectedMeal || "Tay nahi hua"}
                    </Text>
                    <Text style={typography.caption}>
                      {portions} portions · {plan.dishes.length > 0 ? plan.dishes.join(" · ") : "—"}
                    </Text>
                    {plan.prepInstructions ? (
                      <Text style={{ ...typography.small, color: colors.accent.warning, marginTop: 4 }}>
                        ⚠ {plan.prepInstructions}
                      </Text>
                    ) : null}
                  </View>
                </View>
              </Card>
            ))
          )}
        </View>

        {/* Voice note (Hindi). The PRIMARY input — most cooks won't
            type. This is a stub button; the real wiring records audio,
            uploads to backend, transcribes via Sarvam, and feeds into
            the WhatsApp NLU pipeline (services/whatsapp_intents.py). */}
        <Card variant="elevated">
          <View style={{ alignItems: "center", gap: spacing.md }}>
            <Text style={{ ...typography.h3, textAlign: "center" }}>
              Bimi se kuch kehna hai?
            </Text>
            <Text style={{ ...typography.caption, textAlign: "center" }}>
              Mic dabake bol do — Hindi mein bhi chalega.
            </Text>
            <Button
              variant={voiceRecording ? "danger" : "primary"}
              size="lg"
              fullWidth
              leadingIcon={voiceRecording ? "stop-circle" : "mic"}
              onPress={() => {
                haptic("medium");
                setVoiceRecording((r) => !r);
                if (voiceRecording) {
                  // Stub — real flow uploads + transcribes + feeds NLU.
                  showAlert(
                    "Recording saved",
                    "Bimi will transcribe and notify the household.",
                  );
                }
              }}
            >
              {voiceRecording ? "Stop recording" : "Voice note record karo"}
            </Button>
          </View>
        </Card>

        {/* Three quick-tap reports — covers ~80% of cook-side messages.
            Each maps directly to an InboundIntent (see whatsapp-intents.ts):
              - Need this   → cook_low_stock
              - Late        → cook_running_late
              - Off tomorrow → cook_absence */}
        <View style={{ gap: spacing.md }}>
          <Text style={{ ...typography.smallBold, color: colors.text.muted, textTransform: "uppercase", letterSpacing: 0.8 }}>
            Quick reports
          </Text>

          <Card variant="flat" onPress={undefined}>
            <Text style={{ ...typography.h3, marginBottom: spacing.md }}>
              Kuch kam ho gaya?
            </Text>
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
              {["Atta", "Doodh", "Tel", "Pyaaz", "Tamatar", "Sabzi"].map((item) => (
                <Button
                  key={item}
                  variant="secondary"
                  size="sm"
                  onPress={() => reportLowStock(item)}
                >
                  {item}
                </Button>
              ))}
            </View>
            <Text style={{ ...typography.tiny, marginTop: spacing.sm }}>
              Tap kisi bhi item ko — ghar wale ko bata diya jaayega.
            </Text>
          </Card>

          <Card variant="flat">
            <Text style={{ ...typography.h3, marginBottom: spacing.md }}>
              Late ho rahi ho?
            </Text>
            <View style={{ flexDirection: "row", gap: spacing.sm }}>
              {[15, 30, 60].map((mins) => (
                <Button
                  key={mins}
                  variant="secondary"
                  size="sm"
                  onPress={() => reportRunningLate(mins)}
                >
                  +{mins} min
                </Button>
              ))}
            </View>
          </Card>

          <Card variant="flat">
            <Text style={{ ...typography.h3, marginBottom: spacing.md }}>
              Kal nahi aa rahi?
            </Text>
            <Button
              variant="danger"
              size="md"
              fullWidth
              leadingIcon="calendar-outline"
              onPress={reportAbsenceTomorrow}
            >
              Kal off bata do
            </Button>
            <Text style={{ ...typography.tiny, marginTop: spacing.sm }}>
              Bimi ghar wale ko notify kar degi. They'll figure out an alternative.
            </Text>
          </Card>
        </View>

        {/* Footer — sign-off. */}
        <Text
          style={{
            ...typography.tiny,
            textAlign: "center",
            marginTop: spacing.xl,
            fontFamily: fontFamily.regular,
            color: colors.text.muted,
          }}
        >
          ❤️ Bimi — making your day easier.
        </Text>
      </ScrollView>
    </SafeScreen>
  );
}
