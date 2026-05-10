import { View, Text, TextInput, ActivityIndicator } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useState, useRef, useCallback } from "react";
import { useHouseholdStore } from "@/lib/store";
import { lookupInviteCode } from "@/lib/api";
import { colors, spacing, radius, typography, inputStyles, iconSize } from "@/lib/theme";
import { showAlert } from "@/lib/dialogs";
import { WizardLayout, Button, Pill, CalloutCard } from "@/components/ui";

interface MatchedHousehold {
  householdId: string;
  name: string;
  memberCount: number;
  cookName?: string;
  expenseMode: string;
}

const CODE_LEN = 6;
const DIET_OPTIONS = ["Vegetarian", "Non-vegetarian", "Eggetarian", "Jain", "Vegan", "Other"] as const;
type DietOption = (typeof DIET_OPTIONS)[number];

export default function JoinHouseScreen() {
  const router = useRouter();
  const joinHousehold = useHouseholdStore((s) => s.joinHousehold);
  const [code, setCode] = useState<string[]>(Array(CODE_LEN).fill(""));
  const [name, setName] = useState("");
  const [diet, setDiet] = useState<DietOption>("Non-vegetarian");
  const [matched, setMatched] = useState(false);
  const [matchData, setMatchData] = useState<MatchedHousehold | null>(null);
  const [lookupLoading, setLookupLoading] = useState(false);
  const [lookupFailed, setLookupFailed] = useState(false);
  const cellRefs = useRef<(TextInput | null)[]>([]);

  const lookup = useCallback(async (full: string) => {
    setLookupLoading(true);
    setLookupFailed(false);
    try {
      const result = await lookupInviteCode(full);
      if (result) {
        setMatched(true);
        setMatchData(result);
      } else {
        setMatched(false);
        setMatchData(null);
        setLookupFailed(true);
      }
    } catch {
      setMatched(false);
      setMatchData(null);
      setLookupFailed(true);
    } finally {
      setLookupLoading(false);
    }
  }, []);

  const handleCellChange = (text: string, idx: number) => {
    const cleaned = text.toUpperCase().replace(/[^A-Z0-9]/g, "");
    if (!cleaned) {
      // Clearing this cell — also clear matched state.
      const next = [...code];
      next[idx] = "";
      setCode(next);
      setMatched(false);
      setMatchData(null);
      setLookupFailed(false);
      return;
    }
    // Handle paste of multiple chars
    if (cleaned.length > 1) {
      const chars = cleaned.slice(0, CODE_LEN - idx).split("");
      const next = [...code];
      chars.forEach((c, i) => {
        next[idx + i] = c;
      });
      setCode(next);
      const filledTo = idx + chars.length;
      if (filledTo >= CODE_LEN) {
        cellRefs.current[CODE_LEN - 1]?.blur();
        lookup(next.join(""));
      } else {
        cellRefs.current[filledTo]?.focus();
      }
      return;
    }
    const next = [...code];
    next[idx] = cleaned[0]!;
    setCode(next);
    if (idx < CODE_LEN - 1) {
      cellRefs.current[idx + 1]?.focus();
    } else {
      cellRefs.current[idx]?.blur();
      const full = next.join("");
      if (full.length === CODE_LEN) lookup(full);
    }
  };

  const handleCellKeyPress = (e: any, idx: number) => {
    if (e.nativeEvent.key === "Backspace" && !code[idx] && idx > 0) {
      cellRefs.current[idx - 1]?.focus();
    }
  };

  const handleJoin = () => {
    if (!name.trim()) {
      showAlert("Name Required", "Please enter your name.");
      return;
    }
    if (!matchData) {
      showAlert("Invite needed", "Please enter a valid invite code first.");
      return;
    }
    const dietaryPreferences = diet !== "Non-vegetarian"
      ? [{ item: diet, type: "avoidance" as const, safetyClass: "preference" as const, notes: diet }]
      : [];
    const newMember = {
      id: `m-${Date.now()}`,
      name: name.trim(),
      role: "flatmate" as const,
      avatar: "",
      isPayingMember: true,
      isAdmin: false,
      isActive: true,
      isAvailable: true,
      joinedAt: new Date().toISOString(),
      dietaryPreferences,
      healthConditions: [],
    };
    // P3 fix: this used to call addMember on the CURRENT household
    // (BACHELOR_HOUSEHOLD seed) — entirely the wrong household. Now we
    // swap the active household to the matched one before adding the
    // member, so the user truly joins the right house.
    joinHousehold(matchData, newMember);
    showAlert("Welcome!", `You've joined ${matchData.name}. Start voting on meals and splitting expenses!`);
    router.replace("/(tabs)");
  };

  return (
    <WizardLayout
      title="Join a house"
      subtitle="Enter the 6-character invite code from your flatmate."
      centered
      primaryCTA={
        matched ? (
          <Button
            variant="primary"
            size="lg"
            fullWidth
            leadingIcon="enter-outline"
            onPress={handleJoin}
            accessibilityLabel="Join this house"
          >
            Join {matchData?.name ?? "house"}
          </Button>
        ) : undefined
      }
    >
      {/* Real OTP-style cells — replaces the invisible-input + visual-cells anti-pattern. */}
      <View style={{ flexDirection: "row", gap: spacing.sm, justifyContent: "center", marginBottom: spacing.xl }}>
        {Array.from({ length: CODE_LEN }).map((_, i) => {
          const filled = !!code[i];
          return (
            <TextInput
              key={i}
              ref={(r) => { cellRefs.current[i] = r; }}
              value={code[i] || ""}
              onChangeText={(t) => handleCellChange(t, i)}
              onKeyPress={(e) => handleCellKeyPress(e, i)}
              maxLength={CODE_LEN}
              autoCapitalize="characters"
              autoFocus={i === 0}
              keyboardType="ascii-capable"
              accessibilityLabel={`Invite code character ${i + 1} of ${CODE_LEN}`}
              style={{
                width: 44,
                height: 56,
                backgroundColor: filled ? colors.surface.elevated : colors.surface.glass,
                borderWidth: 1,
                borderColor: filled ? colors.accent.primary : colors.border.subtle,
                borderRadius: radius.md,
                textAlign: "center",
                fontSize: 22,
                fontWeight: "800",
                color: colors.text.primary,
              }}
            />
          );
        })}
      </View>

      {lookupLoading && (
        <View style={{ alignItems: "center", marginBottom: spacing.lg }}>
          <ActivityIndicator size="small" color={colors.accent.primary} />
          <Text style={{ ...typography.tiny, marginTop: spacing.xs }}>Looking up invite code…</Text>
        </View>
      )}

      {lookupFailed && (
        <CalloutCard tone="danger" leadingIcon="close-circle">
          Code not found. Check with your flatmate.
        </CalloutCard>
      )}

      {matched && matchData && (
        <CalloutCard tone="success" leadingIcon="checkmark-circle" title={matchData.name}>
          {matchData.memberCount} member{matchData.memberCount !== 1 ? "s" : ""}
          {matchData.cookName ? ` · Cook: ${matchData.cookName}` : ""}
          {` · Split: ${matchData.expenseMode === "equal_split" ? "Equal" : matchData.expenseMode}`}
        </CalloutCard>
      )}

      {/* Join form — only after successful match. */}
      {matched && (
        <View style={{ gap: spacing.lg, marginTop: spacing.xl }}>
          <View>
            <Text style={{ ...typography.captionBold, marginBottom: spacing.xs }}>Your name</Text>
            <TextInput
              value={name}
              onChangeText={setName}
              placeholder="Enter your name"
              placeholderTextColor={colors.text.muted}
              accessibilityLabel="Your name"
              autoCapitalize="words"
              autoComplete="name"
              textContentType="name"
              returnKeyType="done"
              style={{ ...inputStyles, borderWidth: 1, borderColor: colors.border.subtle }}
            />
          </View>
          <View>
            <Text style={{ ...typography.captionBold, marginBottom: spacing.xs }}>Dietary preference</Text>
            <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.xs }}>
              {DIET_OPTIONS.map((d) => (
                <Pill
                  key={d}
                  tone="primary"
                  active={diet === d}
                  onPress={() => setDiet(d)}
                >
                  {d}
                </Pill>
              ))}
            </View>
          </View>
        </View>
      )}

      {/* Decorative spacer to anchor footer when nothing else has appeared yet. */}
      {!matched && !lookupLoading && !lookupFailed && (
        <Text style={{ ...typography.tiny, textAlign: "center" }}>
          <Ionicons name="information-circle-outline" size={iconSize.xs} color={colors.text.muted} /> Codes are case-insensitive.
        </Text>
      )}
    </WizardLayout>
  );
}
