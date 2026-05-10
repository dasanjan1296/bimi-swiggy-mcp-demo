/**
 * Household setup — conversational onboarding (v3).
 *
 * Replaces the v2 form-shaped wizard with a flow that feels like Bimi
 * learning about the household, not the household filling out a
 * profile. Every screen opens with a Bimi-bubble that reflects the
 * inference Bimi just made from the previous answer, and a quiet
 * "what I know so far" pill row at the top so the user always sees
 * accumulated state.
 *
 * Eight steps, each owning one decision:
 *
 *   0. Welcome — Bimi greets by name, frames the 3-minute commitment.
 *   1. City + composition — combined; sets cuisine defaults & cohort.
 *   2. Cuisine tradition — multi-select; biggest single ranking signal.
 *   3. Diet profile — household-level facets + allergy chips.
 *   4. Eat-in cadence — 7-day x 3-meal grid; replaces "orchestrated
 *      meals" multi-select with the actual weekly pattern.
 *   5. Cook — name + WhatsApp + slot + days, plus the WhatsApp-intro
 *      preview that LETS Bimi learn cook's repertoire instead of
 *      asking the user to guess it.
 *   6. Taste — 6-card swipe deck filtered by region + diet.
 *   7. Honest preview — what Bimi will do tonight + what it doesn't
 *      know yet (with the plan to learn each gap).
 *
 * Inputs dropped from v2 (no longer asked, sensible default applied):
 *   • Burner count — defaulted to 2 (most Bangalore flats); user can
 *     change in Settings if it matters for an absurd kitchen.
 *   • Cook repertoire grid — replaced by the WhatsApp-ask. Until the
 *     cook replies, Bimi uses REGION_DEFAULT_REPERTOIRE for the
 *     household's cuisine traditions.
 *   • Per-member diet cards — replaced by household-level facets;
 *     per-member exceptions live in settings.
 */

import React, { useMemo, useState, useEffect } from "react";
import { View, Text } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";

import {
  useHouseholdStore,
  useOnboardingStore,
  type CuisineTradition,
  type DietFacet,
  type CityKey,
  type OnboardingCookProfile,
} from "@/lib/store";
import { useKitchenCapacityStore } from "@/lib/kitchen-capacity-store";
import { useTasteStore } from "@/lib/taste-store";
import {
  HOUSEHOLD_DEFAULTS,
  type HouseholdType,
  type HouseholdMember,
  type DietaryPreference,
} from "@/lib/types";
import {
  CITIES,
  CITY_REFLECTIONS,
  CUISINE_TRADITIONS,
  DIET_PROFILE_OPTIONS,
  REGION_DEFAULT_REPERTOIRE,
  TASTE_DECK_DISHES,
  COOK_REPERTOIRE_OPTIONS,
  smartTasteDeck,
  reduceDietProfile,
  buildCookIntroMessage,
} from "@/lib/onboarding-data";
import {
  WizardLayout,
  Button,
  Pill,
  TextLink,
} from "@/components/ui";
import {
  BimiSays,
  LearnedSummary,
  CuisineTraditionPicker,
  DietProfileMultiSelect,
  EatInCadenceGrid,
  CookContactCard,
  HonestPreview,
  MemberCounter,
  DishSwipeDeck,
  type LearnedItem,
  type PreviewGap,
} from "@/components/onboarding";
import {
  colors,
  spacing,
  typography,
} from "@/lib/theme";
import { showAlert } from "@/lib/dialogs";
import { useAuthStore } from "@/lib/auth-store";
import { updateCookAnswer } from "@/lib/family-api";
import { shareWithCook } from "@/lib/whatsapp-share";
import { recordCookBriefSent } from "@/lib/cook-brief-tracking";
import { haptic } from "@/lib/haptics";

const TOTAL_STEPS = 8;

// ────────────────────────────────────────────────────────────────────
// Composition options. We collapse to 4 visible buckets — pg_hostel
// folds into self_use; single_parent / joint_family fold into
// nuclear_family. These edge cases adjust in Settings post-onboarding.
// ────────────────────────────────────────────────────────────────────
const COMPOSITIONS: { value: HouseholdType; label: string }[] = [
  { value: "self_use",        label: "Just me" },
  { value: "couple",          label: "Couple" },
  { value: "flatmates",       label: "Flatmates" },
  { value: "nuclear_family",  label: "Family" },
];

const DEFAULT_NAMES_BY_TYPE: Record<HouseholdType, string[]> = {
  self_use:        ["You"],
  couple:          ["You", "Partner"],
  flatmates:       ["You", "Flatmate"],
  nuclear_family:  ["You", "Partner", "Child"],
  pg_hostel:       ["You"],
  joint_family:    ["You", "Partner", "Parent"],
  single_parent:   ["You", "Child"],
};

export default function HouseholdSetupScreen() {
  const onboarding = useOnboardingStore();
  const setHousehold = useHouseholdStore((s) => s.setHousehold);
  const setOnboarded = useHouseholdStore((s) => s.setOnboarded);
  const router = useRouter();

  const setKitchenStore = useKitchenCapacityStore((s) => ({
    setBurners: s.setBurners,
    setOrchestratedMeals: s.setOrchestratedMeals,
    setMealTime: s.setMealTime,
  }));
  const bulkSeedTaste = useTasteStore((s) => s.bulkSeed);

  const step = onboarding.step;

  return (
    <>
      {step === 0 && <StepWelcome onNext={() => onboarding.setStep(1)} />}
      {step === 1 && <StepCityAndComposition />}
      {step === 2 && <StepCuisine />}
      {step === 3 && <StepDietProfile />}
      {step === 4 && <StepEatInCadence />}
      {step === 5 && <StepCook />}
      {step === 6 && <StepTaste />}
      {step === 7 && (
        <StepHonestPreview
          onConfirm={() =>
            commitOnboarding({
              router,
              onboarding: useOnboardingStore.getState(),
              setHousehold,
              setOnboarded,
              setKitchenStore,
              bulkSeedTaste,
            })
          }
        />
      )}
    </>
  );
}

// ════════════════════════════════════════════════════════════════════
// Shared selectors / helpers used inside step components
// ════════════════════════════════════════════════════════════════════

/**
 * Build the "what Bimi knows so far" pill row for the top of every
 * step. Compact — these are reflections, not answer summaries; users
 * don't need to be reminded of every chip they tapped.
 */
function buildLearnedItems(o: ReturnType<typeof useOnboardingStore.getState>): LearnedItem[] {
  const items: LearnedItem[] = [];
  if (o.householdType) {
    items.push({
      label: COMPOSITIONS.find((c) => c.value === o.householdType)?.label ?? o.householdType,
      icon: "people-outline",
    });
  }
  if (o.city) {
    items.push({ label: CITIES.find((c) => c.key === o.city)?.label ?? "", icon: "location-outline" });
  }
  if (o.cuisineTraditions.length > 0) {
    items.push({
      label:
        o.cuisineTraditions.length === 1
          ? CUISINE_TRADITIONS.find((c) => c.value === o.cuisineTraditions[0])?.label ?? ""
          : `${o.cuisineTraditions.length} cuisines`,
      icon: "restaurant-outline",
    });
  }
  if (o.dietProfile.length > 0) {
    items.push({ label: shortDietLabel(o.dietProfile), icon: "leaf-outline" });
  }
  const cellCount = Object.values(o.eatInPattern.cells).filter(Boolean).length;
  if (cellCount > 0 && o.step >= 5) {
    items.push({ label: `${cellCount} meals/wk`, icon: "calendar-outline" });
  }
  if (o.cookProfile.displayName && o.step >= 6) {
    items.push({ label: o.cookProfile.displayName, icon: "person-outline" });
  }
  return items;
}

function shortDietLabel(facets: DietFacet[]): string {
  if (facets.includes("non_veg_weekdays")) return "Non-veg";
  if (facets.includes("non_veg_weekends")) return "Wknd non-veg";
  if (facets.includes("eggs_ok")) return "Veg + eggs";
  if (facets.includes("pure_veg")) return "Pure veg";
  return "Diet set";
}

// ════════════════════════════════════════════════════════════════════
// Step 0 — Welcome
// ════════════════════════════════════════════════════════════════════

function StepWelcome({ onNext }: { onNext: () => void }) {
  const userName = useAuthStore((s) => s.childName);
  const greetName = (userName && userName.trim().length > 0 ? userName.trim().split(/\s+/)[0] : "there") ?? "there";

  return (
    <WizardLayout
      step={1}
      of={TOTAL_STEPS}
      hideBack
      title=""
      primaryCTA={
        <Button variant="primary" size="lg" fullWidth onPress={onNext}>
          Let's start
        </Button>
      }
    >
      <View style={{ gap: spacing.lg }}>
        <BimiSays
          message={`Hey ${greetName} 👋  I'm Bimi.\n\nI'm going to learn how your house eats — 6 quick questions, mostly tapping. By the end you'll see what I'd cook tonight.`}
        />
        <View
          style={{
            backgroundColor: colors.surface.card,
            borderRadius: 16,
            padding: spacing.lg,
            gap: spacing.md,
          }}
        >
          <Text style={typography.captionBold}>What I'll ask:</Text>
          <PromiseRow icon="people-circle" label="Who eats here & where you live" />
          <PromiseRow icon="restaurant" label="What you cook & what you avoid" />
          <PromiseRow icon="calendar" label="Which days & meals you eat at home" />
          <PromiseRow icon="logo-whatsapp" label="Your cook — I'll text her too" />
          <PromiseRow icon="heart" label="What you love eating (just swipe)" />
        </View>
      </View>
    </WizardLayout>
  );
}

function PromiseRow({
  icon,
  label,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
}) {
  return (
    <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
      <Ionicons name={icon} size={18} color={colors.accent.primary} />
      <Text style={{ ...typography.body, flex: 1 }}>{label}</Text>
    </View>
  );
}

// ════════════════════════════════════════════════════════════════════
// Step 1 — City + composition
// ════════════════════════════════════════════════════════════════════

function StepCityAndComposition() {
  const onboarding = useOnboardingStore();
  const learned = buildLearnedItems(onboarding);
  const composition = onboarding.householdType;
  const city = onboarding.city;

  // Once both city and composition are set, ensure default members
  // exist so the next steps have a concrete count to plan for.
  useEffect(() => {
    if (composition && onboarding.members.length === 0) {
      const names = DEFAULT_NAMES_BY_TYPE[composition] || ["You"];
      const baseline = composition === "flatmates" ? names.slice(0, 2) : names;
      baseline.forEach((name, i) => {
        onboarding.addOnboardMember(buildOnboardMember(name, composition, i === 0));
      });
    }
  }, [composition]);  

  const inc = () => {
    if (!composition) return;
    if (onboarding.members.length >= 8) return;
    const fallback = DEFAULT_NAMES_BY_TYPE[composition]?.[onboarding.members.length] ?? `Member ${onboarding.members.length + 1}`;
    onboarding.addOnboardMember(buildOnboardMember(fallback, composition, false));
    haptic("light");
  };
  const dec = () => {
    if (onboarding.members.length <= 1) return;
    const last = onboarding.members[onboarding.members.length - 1];
    if (last) {
      onboarding.removeOnboardMember(last.id);
      haptic("light");
    }
  };

  const ready = !!composition && !!city && onboarding.members.length >= 1;

  // Bimi reflects after BOTH answers come in; before that, use a quiet
  // single-line prompt.
  const reflection =
    composition && city
      ? `${COMPOSITIONS.find((c) => c.value === composition)?.label} in ${CITIES.find((c) => c.key === city)?.label}. ${CITY_REFLECTIONS[city]}`
      : `First — pick where you live and who eats with you. I'll use this to set sensible defaults.`;

  return (
    <WizardLayout
      step={2}
      of={TOTAL_STEPS}
      onBack={() => onboarding.setStep(0)}
      title=""
      primaryCTA={
        <Button
          variant="primary"
          size="lg"
          fullWidth
          onPress={() => onboarding.setStep(2)}
          disabled={!ready}
        >
          Next
        </Button>
      }
    >
      <View style={{ gap: spacing.lg }}>
        <LearnedSummary items={learned} />
        <BimiSays message={reflection} />

        {/* City picker */}
        <View style={{ gap: spacing.sm }}>
          <Text style={typography.captionBold}>City</Text>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.xs }}>
            {CITIES.map((c) => (
              <Pill
                key={c.key}
                tone="primary"
                size="md"
                active={city === c.key}
                onPress={() => onboarding.setCity(c.key as CityKey)}
              >
                {c.label}
              </Pill>
            ))}
          </View>
        </View>

        {/* Composition picker */}
        <View style={{ gap: spacing.sm }}>
          <Text style={typography.captionBold}>Who eats at home with you?</Text>
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.xs }}>
            {COMPOSITIONS.map((c) => (
              <Pill
                key={c.value}
                tone="primary"
                size="md"
                active={composition === c.value}
                onPress={() => onboarding.setHouseholdType(c.value)}
              >
                {c.label}
              </Pill>
            ))}
          </View>
        </View>

        {/* Counter only if composition is set */}
        {composition && composition !== "self_use" && (
          <View style={{ gap: spacing.sm, marginTop: spacing.sm }}>
            <Text style={typography.captionBold}>How many people in total?</Text>
            <MemberCounter
              count={onboarding.members.length}
              names={onboarding.members.map((m) => m.name)}
              onIncrement={inc}
              onDecrement={dec}
            />
          </View>
        )}
      </View>
    </WizardLayout>
  );
}

// ════════════════════════════════════════════════════════════════════
// Step 2 — Cuisine tradition
// ════════════════════════════════════════════════════════════════════

function StepCuisine() {
  const onboarding = useOnboardingStore();
  const picked = onboarding.cuisineTraditions;

  const reflection =
    picked.length === 0
      ? "What does your kitchen actually cook? Pick everything that's true. This is the single biggest signal I'll use to suggest meals."
      : picked.length === 1
        ? `Got it — ${CUISINE_TRADITIONS.find((c) => c.value === picked[0])?.label}. I'll keep most suggestions in that lane.`
        : picked.length === 2 && picked.includes("north_indian") && picked.includes("south_indian")
          ? "North + South Indian — a mixed kitchen. I'll alternate so neither side gets bored."
          : `Mixed kitchen — ${picked.length} traditions. I'll rotate so the week feels varied.`;

  return (
    <WizardLayout
      step={3}
      of={TOTAL_STEPS}
      onBack={() => onboarding.setStep(1)}
      title=""
      primaryCTA={
        <Button
          variant="primary"
          size="lg"
          fullWidth
          onPress={() => onboarding.setStep(3)}
          disabled={picked.length === 0}
        >
          Next
        </Button>
      }
    >
      <View style={{ gap: spacing.lg }}>
        <LearnedSummary items={buildLearnedItems(onboarding)} />
        <BimiSays message={reflection} />
        <CuisineTraditionPicker
          selected={picked}
          onToggle={(t) => onboarding.toggleCuisineTradition(t as CuisineTradition)}
        />
      </View>
    </WizardLayout>
  );
}

// ════════════════════════════════════════════════════════════════════
// Step 3 — Diet profile
// ════════════════════════════════════════════════════════════════════

function StepDietProfile() {
  const onboarding = useOnboardingStore();
  const facets = onboarding.dietProfile;
  const allergies = onboarding.allergies;

  const reflection = useMemo(() => buildDietReflection(facets, allergies), [facets, allergies]);

  return (
    <WizardLayout
      step={4}
      of={TOTAL_STEPS}
      onBack={() => onboarding.setStep(2)}
      title=""
      primaryCTA={
        <Button
          variant="primary"
          size="lg"
          fullWidth
          onPress={() => onboarding.setStep(4)}
          disabled={facets.length === 0}
        >
          Next
        </Button>
      }
    >
      <View style={{ gap: spacing.lg }}>
        <LearnedSummary items={buildLearnedItems(onboarding)} />
        <BimiSays message={reflection} />
        <DietProfileMultiSelect
          selectedFacets={facets}
          selectedAllergies={allergies}
          onToggleFacet={(f) => onboarding.toggleDietFacet(f)}
          onToggleAllergy={(a) => onboarding.toggleAllergy(a)}
          onReplaceFacets={(next) => {
            // Drop everything currently selected, then set the next set.
            const toRemove = facets.filter((f) => !next.includes(f));
            const toAdd = next.filter((f) => !facets.includes(f));
            toRemove.forEach((f) => onboarding.toggleDietFacet(f));
            toAdd.forEach((f) => onboarding.toggleDietFacet(f));
          }}
        />
      </View>
    </WizardLayout>
  );
}

function buildDietReflection(facets: DietFacet[], allergies: string[]): string {
  if (facets.length === 0) {
    return "How does your house eat? Pick everything that's true. Allergies are non-negotiable for me — I'll never put them in any suggestion.";
  }
  const reasons: string[] = [];
  for (const f of facets) {
    const opt = DIET_PROFILE_OPTIONS.find((o) => o.value === f);
    if (opt) reasons.push(opt.reflection);
  }
  const allergyLine =
    allergies.length === 0
      ? ""
      : ` Allergies noted: ${allergies.join(", ")}. Off the menu, always.`;
  return `${reasons.join(" ")}${allergyLine}`;
}

// ════════════════════════════════════════════════════════════════════
// Step 4 — Eat-in cadence
// ════════════════════════════════════════════════════════════════════

function StepEatInCadence() {
  const onboarding = useOnboardingStore();
  const cellCount = Object.values(onboarding.eatInPattern.cells).filter(Boolean).length;

  const reflection =
    cellCount === 0
      ? "When do you actually eat at home? Tap each meal. I won't bug you about meals you usually order out or eat at office."
      : cellCount > 17
        ? `${cellCount} home-cooked meals — that's a busy kitchen. I'll plan accordingly.`
        : cellCount < 7
          ? `${cellCount} meals at home this week. Light cooking week — I'll keep suggestions simple.`
          : `${cellCount} meals at home this week. Standard pattern — I'll plan with you, stay quiet on the rest.`;

  return (
    <WizardLayout
      step={5}
      of={TOTAL_STEPS}
      onBack={() => onboarding.setStep(3)}
      title=""
      primaryCTA={
        <Button
          variant="primary"
          size="lg"
          fullWidth
          onPress={() => onboarding.setStep(5)}
          disabled={cellCount === 0}
        >
          Next
        </Button>
      }
    >
      <View style={{ gap: spacing.lg }}>
        <LearnedSummary items={buildLearnedItems(onboarding)} />
        <BimiSays message={reflection} />
        <EatInCadenceGrid
          cells={onboarding.eatInPattern.cells}
          onToggle={(k) => onboarding.toggleEatInCell(k)}
        />
      </View>
    </WizardLayout>
  );
}

// ════════════════════════════════════════════════════════════════════
// Step 5 — Cook
// ════════════════════════════════════════════════════════════════════

function StepCook() {
  const onboarding = useOnboardingStore();
  const profile = onboarding.cookProfile;
  const userName = useAuthStore((s) => s.childName);
  const householdLeadName = (userName && userName.trim().split(/\s+/)[0]) || onboarding.members[0]?.name || "the household";

  const introMessage = useMemo(
    () =>
      buildCookIntroMessage({
        householdLeadName,
        cookDisplayName: profile.displayName,
      }),
    [householdLeadName, profile.displayName],
  );

  const reflection = useMemo(() => {
    if (!profile.displayName) {
      return "Tell me about your cook. Most Bangalore households call her Akka, Didi, or Aunty — pick whatever you actually use.";
    }
    if (!profile.whatsappNumber || profile.whatsappNumber.replace(/\s/g, "").length < 10) {
      return `${profile.displayName} — got it. Now her phone. If she doesn't use WhatsApp, tap the toggle and I'll send SMS instead.`;
    }
    if (profile.hasWhatsapp) {
      return `Perfect. Right after this, I'll text ${profile.displayName} on WhatsApp to learn her best dishes — that's how I'll know what to suggest.`;
    }
    return `Got it — I'll send ${profile.displayName} updates by SMS. Reply quality may be lower; I'll learn slower from her.`;
  }, [profile]);

  const onSend = () => {
    if (!profile.hasWhatsapp || !profile.whatsappNumber) return;
    // Record the brief intent BEFORE handing off to WhatsApp. Linking
    // can fail (WhatsApp not installed, deep-link blocked) and we'd
    // still want a record so the 24h reconciliation can ask the user
    // to try again. recordCookBriefSent also schedules a local
    // notification + fires a fire-and-forget backend POST.
    void recordCookBriefSent({
      cookName: profile.displayName || "your cook",
      cookPhone: profile.whatsappNumber,
      message: introMessage,
    });
    shareWithCook(profile.whatsappNumber, introMessage);
    onboarding.setCookBriefDeferred(false);
    haptic("success");
  };

  const onSkipBrief = () => {
    onboarding.setCookBriefDeferred(true);
    haptic("light");
  };

  const ready = profile.displayName.trim().length > 0 && profile.whatsappNumber.replace(/\s/g, "").length >= 10;

  return (
    <WizardLayout
      step={6}
      of={TOTAL_STEPS}
      onBack={() => onboarding.setStep(4)}
      title=""
      primaryCTA={
        <Button
          variant="primary"
          size="lg"
          fullWidth
          onPress={() => {
            if (!ready) {
              showAlert("One more thing", "Add the cook's name and a phone number — that's how I'll reach her.");
              return;
            }
            onboarding.setStep(6);
          }}
          disabled={!ready}
        >
          Next
        </Button>
      }
    >
      <View style={{ gap: spacing.lg }}>
        <LearnedSummary items={buildLearnedItems(onboarding)} />
        <BimiSays message={reflection} />
        <CookContactCard
          profile={profile}
          onChange={(p) => onboarding.setCookProfile(p)}
          introMessagePreview={introMessage}
          onSendNow={onSend}
          onSkipBrief={onSkipBrief}
        />
      </View>
    </WizardLayout>
  );
}

// ════════════════════════════════════════════════════════════════════
// Step 6 — Taste swipe (6 cards, smart-filtered)
// ════════════════════════════════════════════════════════════════════

function StepTaste() {
  const onboarding = useOnboardingStore();
  const dietPreset = useMemo(() => reduceDietProfile(onboarding.dietProfile), [onboarding.dietProfile]);
  const deck = useMemo(
    () =>
      smartTasteDeck({
        diets: [dietPreset],
        cuisines: onboarding.cuisineTraditions,
      }),
    [dietPreset, onboarding.cuisineTraditions],
  );

  const swipedCount = Object.keys(onboarding.tasteSeed.verdicts).length;
  const reflection =
    swipedCount === 0
      ? "Last thing — swipe through 6 dishes. Right = love it. Left = nope. Up = it's fine.\n\nThis is what I'll lean on for the very first suggestion before any meal history exists."
      : swipedCount < deck.length
        ? `${swipedCount} of ${deck.length} so far — keep going.`
        : "Got enough taste signal — let me show you tonight's plan.";

  return (
    <WizardLayout
      step={7}
      of={TOTAL_STEPS}
      onBack={() => onboarding.setStep(5)}
      title=""
      primaryCTA={
        <Button
          variant="primary"
          size="lg"
          fullWidth
          onPress={() => onboarding.setStep(7)}
          disabled={swipedCount === 0}
        >
          {swipedCount >= deck.length ? "See tonight's plan" : "Skip the rest"}
        </Button>
      }
    >
      <View style={{ gap: spacing.lg }}>
        <LearnedSummary items={buildLearnedItems(onboarding)} />
        <BimiSays message={reflection} />
        <DishSwipeDeck
          dishes={deck}
          onVerdict={(slug, verdict) => onboarding.setTasteVerdict(slug, verdict)}
          onDeckEmpty={() => onboarding.setStep(7)}
        />
      </View>
    </WizardLayout>
  );
}

// ════════════════════════════════════════════════════════════════════
// Step 7 — Honest preview
// ════════════════════════════════════════════════════════════════════

function StepHonestPreview({ onConfirm }: { onConfirm: () => void }) {
  const onboarding = useOnboardingStore();
  const previewSlug = pickPreviewDishSlug(onboarding);
  const previewName = displayNameForSlug(previewSlug);
  const portions = onboarding.members.length || 2;
  const cookDisplayName = onboarding.cookProfile.displayName || null;
  const arrivalLabel = arrivalLabelFor(onboarding.cookProfile);
  const briefAtLabel = arrivalLabel ? formatHHMMOffset(arrivalLabel, -45) : null;

  const gaps: PreviewGap[] = [];

  if (onboarding.cookBriefDeferred && onboarding.cookProfile.hasWhatsapp) {
    gaps.push({
      title: `${cookDisplayName ?? "Your cook"}'s actual best dishes`,
      plan: `You said you'd message her later. Until you do, I'll use standard ${primaryCuisineLabel(onboarding.cuisineTraditions)} dishes.`,
      icon: "logo-whatsapp",
    });
  } else if (!onboarding.cookBriefDeferred && onboarding.cookProfile.hasWhatsapp) {
    gaps.push({
      title: `${cookDisplayName ?? "Your cook"}'s reply`,
      plan: "I just sent her a message. As soon as she replies (voice note OK), I'll start suggesting her actual best dishes.",
      icon: "logo-whatsapp",
    });
  } else {
    gaps.push({
      title: `${cookDisplayName ?? "Your cook"}'s actual best dishes`,
      plan: "Without WhatsApp, I'll learn from your meal ratings — slower, but it works.",
      icon: "chatbubble-outline",
    });
  }

  gaps.push({
    title: "What's actually in your kitchen",
    plan: "I'll ask you after dinner tonight to add a couple of staples. Within a week I'll know your pantry rhythm.",
    icon: "basket-outline",
  });

  gaps.push({
    title: "How you like your grocery delivery",
    plan: "I'll ask which of Blinkit / Zepto / BigBasket you trust the first time something runs low.",
    icon: "bicycle-outline",
  });

  if (
    onboarding.cuisineTraditions.length >= 2 &&
    !onboarding.cuisineTraditions.includes("everything")
  ) {
    gaps.push({
      title: "Whose taste leads on which day",
      plan: "Mixed-cuisine kitchen. After a week of votes I'll learn whether you alternate or split by meal.",
      icon: "swap-horizontal-outline",
    });
  }

  return (
    <WizardLayout
      step={8}
      of={TOTAL_STEPS}
      onBack={() => onboarding.setStep(6)}
      title=""
      primaryCTA={
        <Button
          variant="primary"
          size="lg"
          fullWidth
          leadingIcon="checkmark-circle"
          onPress={onConfirm}
        >
          Looks right — let's go
        </Button>
      }
      secondaryCTA={
        <TextLink onPress={() => onboarding.setStep(2)} size="sm" tone="secondary" leadingIcon="chevron-back">
          Tweak something
        </TextLink>
      }
    >
      <View style={{ gap: spacing.lg }}>
        <LearnedSummary items={buildLearnedItems(onboarding)} />
        <BimiSays
          message="Done. Here's how tonight looks based on what I've learned — and what I still need to figure out as we go."
          learned={[
            { text: `${onboarding.members.length || 2} people, ${cellCountLabel(onboarding)} a week`, icon: "people" },
            { text: `${primaryCuisineLabel(onboarding.cuisineTraditions)} kitchen`, icon: "restaurant" },
            ...(onboarding.cookProfile.displayName
              ? [{ text: `${onboarding.cookProfile.displayName} on ${onboarding.cookProfile.workingDays.length} days`, icon: "logo-whatsapp" as const }]
              : []),
          ]}
        />
        <HonestPreview
          dishSlug={previewSlug}
          dishName={previewName}
          portions={portions}
          cookDisplayName={cookDisplayName}
          cookArrivalLabel={arrivalLabel}
          briefAtLabel={briefAtLabel}
          gaps={gaps}
        />
      </View>
    </WizardLayout>
  );
}

// ════════════════════════════════════════════════════════════════════
// Helpers
// ════════════════════════════════════════════════════════════════════

function buildOnboardMember(name: string, type: HouseholdType, isFirst: boolean): HouseholdMember {
  const role =
    type === "couple"          ? "partner" :
    type === "flatmates"       ? "flatmate" :
    type === "nuclear_family"  ? (isFirst ? "parent" : "member") :
    "member";
  return {
    id: `m-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    name,
    role,
    avatar: "",
    isPayingMember: true,
    isAdmin: isFirst,
    isActive: true,
    isAvailable: true,
    joinedAt: new Date().toISOString(),
    dietaryPreferences: [],
    healthConditions: [],
  };
}

/**
 * Convert household-level diet facets + allergy chips into the legacy
 * per-member `DietaryPreference[]` shape. Hard allergies → critical
 * safetyClass so the meal-suggestion filter blocks them outright.
 */
function dietProfileToPreferences(facets: DietFacet[], allergies: string[]): DietaryPreference[] {
  const prefs: DietaryPreference[] = [];

  if (facets.includes("pure_veg")) {
    prefs.push({ item: "Meat", type: "avoidance", safetyClass: "preference", notes: "Pure vegetarian household" });
    prefs.push({ item: "Egg",  type: "avoidance", safetyClass: "preference", notes: "Pure vegetarian household" });
  } else if (facets.includes("eggs_ok") && !facets.some((f) => f === "non_veg_weekdays" || f === "non_veg_weekends")) {
    prefs.push({ item: "Meat", type: "avoidance", safetyClass: "preference", notes: "Eggs OK; no meat" });
  }
  if (facets.includes("non_veg_weekends")) {
    prefs.push({ item: "Meat", type: "preference", safetyClass: "preference", notes: "Non-veg weekends only" });
  }
  if (facets.includes("no_onion_garlic")) {
    prefs.push({ item: "Onion",  type: "avoidance", safetyClass: "preference", notes: "Sattvik" });
    prefs.push({ item: "Garlic", type: "avoidance", safetyClass: "preference", notes: "Sattvik" });
  }
  if (facets.includes("no_beef")) {
    prefs.push({ item: "Beef", type: "avoidance", safetyClass: "preference", notes: "Religious" });
  }
  if (facets.includes("no_pork")) {
    prefs.push({ item: "Pork", type: "avoidance", safetyClass: "preference", notes: "Religious" });
  }
  if (facets.includes("jain")) {
    prefs.push({ item: "Roots / Allium", type: "avoidance", safetyClass: "preference", notes: "Jain" });
  }
  for (const item of allergies) {
    prefs.push({ item, type: "allergy", safetyClass: "critical", notes: "Captured at onboarding" });
  }
  return prefs;
}

function pickPreviewDishSlug(o: ReturnType<typeof useOnboardingStore.getState>): string {
  const loved = Object.entries(o.tasteSeed.verdicts).filter(([, v]) => v === "loved").map(([s]) => s);
  const liked = Object.entries(o.tasteSeed.verdicts).filter(([, v]) => v === "liked").map(([s]) => s);
  const regionPool = o.cuisineTraditions.flatMap((c) => REGION_DEFAULT_REPERTOIRE[c] ?? []);
  const intersection = loved.find((s) => regionPool.includes(s));
  if (intersection) return intersection;
  if (loved[0]) return loved[0];
  if (regionPool[0]) return regionPool[0];
  if (liked[0]) return liked[0];
  return "rajma-chawal";
}

function displayNameForSlug(slug: string): string {
  const all = [...COOK_REPERTOIRE_OPTIONS, ...TASTE_DECK_DISHES];
  return all.find((d) => d.slug === slug)?.name ??
    slug.split("-").map((s) => s.charAt(0).toUpperCase() + s.slice(1)).join(" ");
}

function arrivalLabelFor(profile: OnboardingCookProfile): string | null {
  if (!profile.displayName) return null;
  // Default windows — match SLOT_OPTIONS in CookContactCard.
  if (profile.slot === "morning") return "8:00 AM";
  if (profile.slot === "both") return "8:00 AM and 7:00 PM";
  return "7:00 PM";
}

function formatHHMMOffset(label: string, offsetMinutes: number): string {
  // "7:00 PM" or "8:00 AM and 7:00 PM" → offset the FIRST clock value.
  const match = label.match(/^(\d{1,2}):(\d{2})\s*(AM|PM)/);
  if (!match) return label;
  let hours = parseInt(match[1] ?? "0", 10);
  const minutes = parseInt(match[2] ?? "0", 10);
  const meridiem = match[3] ?? "AM";
  if (meridiem === "PM" && hours !== 12) hours += 12;
  if (meridiem === "AM" && hours === 12) hours = 0;
  let total = hours * 60 + minutes + offsetMinutes;
  total = ((total % 1440) + 1440) % 1440;
  const h24 = Math.floor(total / 60);
  const m = total % 60;
  const ampm = h24 >= 12 ? "PM" : "AM";
  const h12 = h24 === 0 ? 12 : h24 > 12 ? h24 - 12 : h24;
  return `${h12}:${m.toString().padStart(2, "0")} ${ampm}`;
}

function cellCountLabel(o: ReturnType<typeof useOnboardingStore.getState>): string {
  const n = Object.values(o.eatInPattern.cells).filter(Boolean).length;
  return `${n} home meals`;
}

function primaryCuisineLabel(traditions: CuisineTradition[]): string {
  if (traditions.length === 0) return "Mixed";
  if (traditions.length === 1) return CUISINE_TRADITIONS.find((c) => c.value === traditions[0])?.label ?? "Mixed";
  if (traditions.includes("everything")) return "Eat-everything";
  return `Mixed ${traditions.length}-cuisine`;
}

interface CommitArgs {
  router: ReturnType<typeof useRouter>;
  onboarding: ReturnType<typeof useOnboardingStore.getState>;
  setHousehold: ReturnType<typeof useHouseholdStore.getState>["setHousehold"];
  setOnboarded: ReturnType<typeof useHouseholdStore.getState>["setOnboarded"];
  setKitchenStore: {
    setBurners: (b: 1 | 2 | 3 | 4) => void;
    setOrchestratedMeals: (m: ("breakfast" | "lunch" | "dinner")[]) => void;
    setMealTime: (slot: "breakfast" | "lunch" | "dinner", hhmm: string) => void;
  };
  bulkSeedTaste: (verdicts: { slug: string; verdict: "loved" | "liked" | "disliked" }[]) => void;
}

async function commitOnboarding(args: CommitArgs) {
  const { router, onboarding, setHousehold, setOnboarded, setKitchenStore, bulkSeedTaste } = args;
  const type = onboarding.householdType ?? "couple";

  // 1. Members with household-level diet folded into per-member prefs.
  const sharedPreferences = dietProfileToPreferences(onboarding.dietProfile, onboarding.allergies);
  const members: HouseholdMember[] = onboarding.members.map((m) => ({
    ...m,
    dietaryPreferences: [...sharedPreferences],
  }));

  // 2. Cook — repertoire seeded from REGION defaults until WhatsApp
  // reply lands. We map slugs → display names to satisfy the legacy
  // Cook.repertoire string[] shape that the suggestion engine reads.
  const seededSlugs = onboarding.cuisineTraditions.flatMap((c) => REGION_DEFAULT_REPERTOIRE[c] ?? []);
  const dedupSeed = Array.from(new Set(seededSlugs));
  const repertoireNames = dedupSeed.map(displayNameForSlug);
  const slot = onboarding.cookProfile.slot;
  const arrivalDeparture = slot === "morning"
    ? { arrivalTime: "08:00", departureTime: "09:00", type: "morning" as const }
    : slot === "both"
      ? { arrivalTime: "08:00", departureTime: "20:00", type: "morning" as const }
      : { arrivalTime: "19:00", departureTime: "20:00", type: "evening" as const };

  const cook = onboarding.cookProfile.displayName
    ? {
        id: `c-${Date.now()}`,
        name: onboarding.cookProfile.displayName,
        whatsappNumber: onboarding.cookProfile.whatsappNumber,
        schedule: `${onboarding.cookProfile.workingDays.join(",")}, ${arrivalDeparture.arrivalTime}-${arrivalDeparture.departureTime}`,
        repertoire: repertoireNames,
        slots: [
          {
            type: arrivalDeparture.type,
            arrivalTime: arrivalDeparture.arrivalTime,
            departureTime: arrivalDeparture.departureTime,
            workingDays: onboarding.cookProfile.workingDays,
          },
        ],
      }
    : null;

  // 3. Persist household.
  setHousehold({
    id: `h-${Date.now()}`,
    type,
    name: members[0] ? `${members[0].name}'s Kitchen` : "Your Kitchen",
    members,
    cooks: cook ? [cook] : [],
    hasCook: !!cook,
    hasRegularCook: true,
    config: { ...HOUSEHOLD_DEFAULTS[type] },
    createdAt: new Date().toISOString(),
  });
  setOnboarded(true);

  // 4. Kitchen capacity. Burners default to 2 unless a previous
  // session set otherwise. Orchestrated meals = derived from eat-in
  // pattern: any slot with at least one cell on counts.
  const orchestrated: ("breakfast" | "lunch" | "dinner")[] = [];
  const slots: ("breakfast" | "lunch" | "dinner")[] = ["breakfast", "lunch", "dinner"];
  for (const s of slots) {
    const anyOn = Object.entries(onboarding.eatInPattern.cells).some(
      ([key, v]) => v && key.endsWith(`-${s}`),
    );
    if (anyOn) orchestrated.push(s);
  }
  setKitchenStore.setBurners(onboarding.kitchen.burners);
  setKitchenStore.setOrchestratedMeals(orchestrated.length > 0 ? orchestrated : ["dinner"]);
  setKitchenStore.setMealTime("breakfast", onboarding.kitchen.mealTimes.breakfast);
  setKitchenStore.setMealTime("lunch",     onboarding.kitchen.mealTimes.lunch);
  setKitchenStore.setMealTime("dinner",    onboarding.kitchen.mealTimes.dinner);

  // 5. Taste seed.
  bulkSeedTaste(
    Object.entries(onboarding.tasteSeed.verdicts).map(([slug, verdict]) => ({ slug, verdict })),
  );

  // 6. Backend hint — keeps the legacy KPI plumbing happy.
  try {
    const familyId = useAuthStore.getState().familyId;
    if (familyId) await updateCookAnswer(familyId, true);
  } catch {
    /* non-fatal */
  }

  onboarding.reset();
  haptic("success");
  router.replace("/(tabs)" as never);
}
