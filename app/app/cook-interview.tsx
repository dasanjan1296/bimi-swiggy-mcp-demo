import { View, Text, TextInput } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useState, useMemo, useEffect, useCallback, useRef } from "react";
import { useHouseholdStore } from "@/lib/store";
import { client } from "@/lib/api";
import { useCookProfileStore, COOK_INTERVIEW_QUESTIONS, SECTION_META, type CookProfileQuestion } from "@/lib/cook-profile";
import { GuidanceTip } from "@/components/GuidanceTip";
import { colors, spacing, radius, typography, inputStyles, iconSize } from "@/lib/theme";
import { showAlert, showConfirm } from "@/lib/dialogs";
import {
  WizardLayout,
  Button,
  Pill,
  CalloutCard,
  IconBadge,
} from "@/components/ui";
import { haptic } from "@/lib/haptics";
import { safeBack } from "@/lib/safe-back";

interface SharedCookStatus {
  exists: boolean;
  household_count: number;
  name: string | null;
}

const SECTIONS = ["basics", "schedule", "skills", "preferences", "logistics"] as const;
type SectionKey = (typeof SECTIONS)[number];

export default function CookInterviewScreen() {
  const router = useRouter();
  const household = useHouseholdStore((s) => s.household);
  const setCook = useHouseholdStore((s) => s.setCook);
  const setAnswer = useCookProfileStore((s) => s.setAnswer);
  const getAnswer = useCookProfileStore((s) => s.getAnswer);
  const markInterviewComplete = useCookProfileStore((s) => s.markInterviewComplete);
  const answers = useCookProfileStore((s) => s.answers);

  const [currentSection, setCurrentSection] = useState(0);
  const [textInputs, setTextInputs] = useState<Record<string, string>>({});
  const [chipSelections, setChipSelections] = useState<Record<string, string[]>>({});
  const [numberInputs, setNumberInputs] = useState<Record<string, string>>({});
  const [yesnoAnswers, setYesnoAnswers] = useState<Record<string, boolean>>({});
  const [selectAnswers, setSelectAnswers] = useState<Record<string, string>>({});
  const [sharedCookStatus, setSharedCookStatus] = useState<SharedCookStatus | null>(null);

  const phoneValue = textInputs["phone"] ?? (useCookProfileStore.getState().getAnswer("phone")?.answer as string) ?? "";

  // AbortController per request so we can cancel the in-flight request
  // when the user types more digits or unmounts. Without this, fast-typing
  // stacked parallel lookups and setSharedCookStatus could fire on an
  // unmounted component (a setState-on-unmounted warning at best, a
  // null-deref crash inside reanimated at worst).
  const inFlightRef = useRef<AbortController | null>(null);

  const checkSharedCookStatus = useCallback(async (phone: string, signal: AbortSignal) => {
    const cleaned = phone.replace(/\s+/g, "").replace(/^\+/, "");
    if (cleaned.length < 10) {
      setSharedCookStatus(null);
      return;
    }
    try {
      const { data } = await client.get<SharedCookStatus>(
        `/households/cook-status/${cleaned}`,
        { signal },
      );
      if (!signal.aborted) setSharedCookStatus(data);
    } catch (err) {
      // Aborted → silently ignore. Other failures: also silently degrade
      // since the lookup is purely informational.
      if (!signal.aborted) setSharedCookStatus(null);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    inFlightRef.current?.abort();
    inFlightRef.current = controller;
    const timeout = setTimeout(() => {
      if (phoneValue) checkSharedCookStatus(phoneValue, controller.signal);
    }, 600);
    return () => {
      clearTimeout(timeout);
      controller.abort();
    };
  }, [phoneValue, checkSharedCookStatus]);

  const activeMembers = useMemo(() => household?.members.filter((m) => m.isActive) || [], [household]);
  const interviewer = activeMembers[0]?.name || "You";

  const sectionKey: SectionKey = SECTIONS[currentSection]!;
  const sectionQuestions = COOK_INTERVIEW_QUESTIONS.filter((q) => q.section === sectionKey);
  const meta = SECTION_META[sectionKey];
  const isLastSection = currentSection === SECTIONS.length - 1;

  const answeredCount = answers.length;

  // CTA copy adapts to household type — not all households have flatmates to ask.
  const finishCtaLabel = useMemo(() => {
    const t = household?.type;
    if (t === "couple") return "Save & ask partner to verify";
    if (t === "self_use" || t === "pg_hostel") return "Save cook profile";
    return "Save & ask family to verify";
  }, [household?.type]);

  const saveCurrentAnswers = () => {
    sectionQuestions.forEach((q) => {
      let value: string | string[] | number | boolean | undefined;
      if (q.type === "text") value = textInputs[q.id];
      else if (q.type === "chips" || q.type === "multiselect") value = chipSelections[q.id];
      else if (q.type === "number") value = numberInputs[q.id] ? parseInt(numberInputs[q.id]!) : undefined;
      else if (q.type === "yesno") value = yesnoAnswers[q.id];
      else if (q.type === "select") value = selectAnswers[q.id];

      if (value !== undefined && value !== "" && !(Array.isArray(value) && value.length === 0)) {
        setAnswer(q.id, value, interviewer);
      }
    });
  };

  const handleNext = () => {
    saveCurrentAnswers();
    haptic("light");
    if (isLastSection) handleFinish();
    else setCurrentSection((p) => p + 1);
  };

  const handleBack = () => {
    saveCurrentAnswers();
    if (currentSection > 0) {
      setCurrentSection((p) => p - 1);
    } else {
      // Cancelling from section 0 wipes interview progress — confirm first.
      showConfirm(
        "Discard cook profile?",
        "Your household is set up; you can add a cook later from Settings.",
        {
          confirmText: "Discard",
          destructive: true,
          onConfirm: () => safeBack(),
        },
      );
    }
  };

  const handleFinish = () => {
    const get = (id: string) => useCookProfileStore.getState().getAnswer(id)?.answer;

    const name = (get("name") as string) || household?.cooks?.[0]?.name || "Cook";
    if (!name || name === "Cook") {
      showAlert("Name Required", "Please enter the cook's name in Basics before finishing.");
      setCurrentSection(0);
      return;
    }
    const phone = (get("phone") as string) || household?.cooks?.[0]?.whatsappNumber || "";
    const dishes = (get("dishes") as string[]) || household?.cooks?.[0]?.repertoire || [];
    const slotType = ((get("slot_type") as string) || "Evening").toLowerCase();
    const arrival = (get("arrival") as string) || "19:00";
    const departure = (get("departure") as string) || "20:00";
    const workingDays = (get("working_days") as string[]) || ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    const payDay = get("pay_day") as number | undefined;
    const salary = get("salary") as number | undefined;
    const monthlyLeaves = (get("monthly_leaves") as number) || 4;
    const cookDiet = (get("cook_diet") as string[]) || [];
    const schedule = `${workingDays.join(",")}, ${arrival}-${departure}`;

    setCook({
      id: household?.cooks?.[0]?.id || `c-${Date.now()}`,
      name,
      whatsappNumber: phone,
      schedule,
      repertoire: dishes,
      payDay,
      salary,
      monthlyLeaves,
      dietaryRestrictions: cookDiet.filter((d) => d !== "None"),
      slots: [{
        type: (slotType === "morning" || slotType === "both" ? "morning" : "evening") as "morning" | "evening",
        arrivalTime: arrival,
        departureTime: departure,
        workingDays,
      }],
    });
    markInterviewComplete();
    haptic("success");
    router.push("/cook-verify" as any);
  };

  const renderQuestion = (q: CookProfileQuestion) => {
    const existingAnswer = getAnswer(q.id);

    return (
      <View key={q.id} style={{ marginBottom: spacing.xl }}>
        <Text style={{ ...typography.bodyBold, marginBottom: 4 }}>
          {q.question}
          {q.required && <Text style={{ color: colors.accent.danger }}> *</Text>}
        </Text>
        <Text style={{ ...typography.small, marginBottom: spacing.md }}>{q.hint}</Text>

        {q.type === "text" && (
          <TextInput
            value={textInputs[q.id] ?? (existingAnswer?.answer as string) ?? ""}
            onChangeText={(v) => setTextInputs((p) => ({ ...p, [q.id]: v }))}
            placeholder="Type here…"
            placeholderTextColor={colors.text.muted}
            keyboardType={q.id === "phone" ? "phone-pad" : "default"}
            style={{ ...inputStyles, borderWidth: 1, borderColor: colors.border.subtle }}
          />
        )}

        {q.type === "number" && (
          <TextInput
            value={numberInputs[q.id] ?? (existingAnswer?.answer?.toString()) ?? ""}
            onChangeText={(v) => setNumberInputs((p) => ({ ...p, [q.id]: v }))}
            placeholder="0"
            placeholderTextColor={colors.text.muted}
            keyboardType="numeric"
            style={{ ...inputStyles, borderWidth: 1, borderColor: colors.border.subtle, width: 120 }}
          />
        )}

        {/* Yes/No, select, and chips all share the same selected-state grammar via <Pill>. */}
        {q.type === "yesno" && (
          <View style={{ flexDirection: "row", gap: spacing.sm }}>
            {[true, false].map((val) => {
              const selected = (yesnoAnswers[q.id] ?? existingAnswer?.answer) === val;
              return (
                <View key={String(val)} style={{ flex: 1 }}>
                  <Pill
                    tone="primary"
                    active={selected}
                    onPress={() => setYesnoAnswers((p) => ({ ...p, [q.id]: val }))}
                    style={{ flex: 1, justifyContent: "center", alignSelf: "stretch", paddingVertical: 12 }}
                  >
                    {val ? "Yes" : "No"}
                  </Pill>
                </View>
              );
            })}
          </View>
        )}

        {q.type === "select" && q.options && (
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.xs }}>
            {q.options.map((opt) => {
              const selected = (selectAnswers[q.id] ?? existingAnswer?.answer) === opt;
              return (
                <Pill
                  key={opt}
                  tone="primary"
                  active={selected}
                  onPress={() => setSelectAnswers((p) => ({ ...p, [q.id]: opt }))}
                >
                  {opt}
                </Pill>
              );
            })}
          </View>
        )}

        {(q.type === "chips" || q.type === "multiselect") && q.options && (
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.xs }}>
            {q.options.map((opt) => {
              const current = chipSelections[q.id] ?? (existingAnswer?.answer as string[]) ?? [];
              const selected = current.includes(opt);
              return (
                <Pill
                  key={opt}
                  tone="primary"
                  active={selected}
                  onPress={() => {
                    setChipSelections((p) => {
                      const prev = p[q.id] ?? (existingAnswer?.answer as string[]) ?? [];
                      return { ...p, [q.id]: selected ? prev.filter((v) => v !== opt) : [...prev, opt] };
                    });
                  }}
                  trailingIcon={selected ? "close-circle" : undefined}
                >
                  {opt}
                </Pill>
              );
            })}
          </View>
        )}

        {existingAnswer && (
          <View style={{ flexDirection: "row", alignItems: "center", gap: 4, marginTop: spacing.sm }}>
            <Ionicons name="checkmark-circle" size={iconSize.xs} color={colors.accent.success} />
            <Text style={{ ...typography.tiny, color: colors.accent.success }}>
              Answered by {existingAnswer.answeredBy}
            </Text>
          </View>
        )}
      </View>
    );
  };

  return (
    <WizardLayout
      step={currentSection + 1}
      of={SECTIONS.length}
      onBack={handleBack}
      title={meta.label}
      subtitle={meta.description}
      primaryCTA={
        <Button
          variant="primary"
          size="lg"
          fullWidth
          onPress={handleNext}
          leadingIcon={isLastSection ? "checkmark-circle" : undefined}
        >
          {isLastSection ? finishCtaLabel : "Next"}
        </Button>
      }
      secondaryCTA={
        <Text style={{ ...typography.tiny, color: colors.text.muted }}>
          Section {currentSection + 1} of {SECTIONS.length} · {answeredCount} of {COOK_INTERVIEW_QUESTIONS.length} answered
        </Text>
      }
    >
      {/* Section identity icon — quiet, doesn't compete with WizardLayout's title above. */}
      <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, marginBottom: spacing.xl }}>
        <IconBadge icon={meta.icon as any} tone="primary" size="sm" />
        <Text style={{ ...typography.smallBold, textTransform: "uppercase", letterSpacing: 1 }}>
          {meta.label}
        </Text>
      </View>

      {currentSection === 0 && (
        <View style={{ marginBottom: spacing.xl }}>
          <GuidanceTip
            variant="hint"
            icon="chatbubbles-outline"
            title="Interview your cook"
            message="Sit with your cook and fill this in together. Ask them each question — they know their schedule, skills, and preferences best. Other members will verify the answers next."
            compact
          />
        </View>
      )}

      {currentSection === 0 && sharedCookStatus?.exists && (
        <View style={{ marginBottom: spacing.xl }}>
          <CalloutCard
            tone="primary"
            leadingIcon="people-circle"
            title={`${sharedCookStatus.name} already uses Bimi`}
          >
            Connected to {sharedCookStatus.household_count} other household{sharedCookStatus.household_count !== 1 ? "s" : ""}. Schedule and preferences will be imported.
          </CalloutCard>
        </View>
      )}

      {sectionQuestions.map(renderQuestion)}
    </WizardLayout>
  );
}
