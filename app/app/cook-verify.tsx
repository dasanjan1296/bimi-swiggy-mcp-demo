import { View, Text, ScrollView, TextInput } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useState, useMemo, useCallback } from "react";
import { useHouseholdStore } from "@/lib/store";
import { useNotificationStore } from "@/lib/notifications";
import { useCookProfileStore, COOK_INTERVIEW_QUESTIONS, SECTION_META } from "@/lib/cook-profile";
import { GuidanceTip } from "@/components/GuidanceTip";
import { colors, cardStyles, spacing, radius, typography, inputStyles, iconSize } from "@/lib/theme";
import { showAlert } from "@/lib/dialogs";
import { haptic } from "@/lib/haptics";
import {
  WizardLayout,
  Button,
  Pill,
  TextLink,
  Avatar,
  MeterBar,
  SectionEyebrow,
} from "@/components/ui";
import { RipplePressable } from "@/components/RipplePressable";

export default function CookVerifyScreen() {
  const router = useRouter();
  const household = useHouseholdStore((s) => s.household);
  const addNotification = useNotificationStore((s) => s.addNotification);
  const answers = useCookProfileStore((s) => s.answers);
  const addVerification = useCookProfileStore((s) => s.addVerification);
  const removeVerification = useCookProfileStore((s) => s.removeVerification);
  const verifications = useCookProfileStore((s) => s.verifications);
  const markVerificationComplete = useCookProfileStore((s) => s.markVerificationComplete);
  const getVerificationSummary = useCookProfileStore((s) => s.getVerificationSummary);

  const [currentMemberIdx, setCurrentMemberIdx] = useState(0);
  const [corrections, setCorrections] = useState<Record<string, string>>({});
  const [additions, setAdditions] = useState<Record<string, string>>({});
  // Multiple "I know something else" panels can be open simultaneously now (was single-string).
  const [openAdditionsFor, setOpenAdditionsFor] = useState<Set<string>>(new Set());
  // Per-question disagree-mode (only show correction input after the user actually disagrees).
  const [disagreeingFor, setDisagreeingFor] = useState<Set<string>>(new Set());
  // Per-question expanded "see other members' verifications" disclosure.
  const [expandedDetailFor, setExpandedDetailFor] = useState<Set<string>>(new Set());

  const activeMembers = useMemo(() => household?.members.filter((m) => m.isActive) || [], [household]);
  const currentMember = activeMembers[currentMemberIdx];
  const cookName = household?.cooks?.[0]?.name || "Cook";
  const isLastMember = currentMemberIdx === activeMembers.length - 1;

  const answeredQuestions = useMemo(
    () => COOK_INTERVIEW_QUESTIONS.filter((q) => answers.some((a) => a.questionId === q.id)),
    [answers],
  );

  const memberVerifiedCount = useMemo(
    () => verifications.filter((v) => v.memberId === currentMember?.id).length,
    [verifications, currentMember],
  );

  const toggleSet = useCallback((set: Set<string>, key: string, setter: (s: Set<string>) => void) => {
    const next = new Set(set);
    if (next.has(key)) next.delete(key);
    else next.add(key);
    setter(next);
  }, []);

  const handleAgree = (questionId: string) => {
    if (!currentMember) return;
    addVerification({ memberId: currentMember.id, memberName: currentMember.name, questionId, agrees: true });
    haptic("light");
    setDisagreeingFor((s) => {
      const n = new Set(s);
      n.delete(questionId);
      return n;
    });
  };

  const handleStartDisagree = (questionId: string) => {
    setDisagreeingFor((s) => new Set(s).add(questionId));
  };

  const handleSubmitDisagree = (questionId: string) => {
    if (!currentMember) return;
    const correction = corrections[questionId];
    addVerification({
      memberId: currentMember.id,
      memberName: currentMember.name,
      questionId,
      agrees: false,
      correction: correction || undefined,
    });
    haptic("light");
    setDisagreeingFor((s) => {
      const n = new Set(s);
      n.delete(questionId);
      return n;
    });
  };

  const handleChangeMyAnswer = (questionId: string) => {
    if (!currentMember || typeof removeVerification !== "function") return;
    removeVerification(currentMember.id, questionId);
    haptic("selection");
  };

  const handleAddKnowledge = (questionId: string) => {
    if (!currentMember) return;
    const addition = additions[questionId]?.trim();
    if (!addition) return;
    addVerification({
      memberId: currentMember.id,
      memberName: currentMember.name,
      questionId,
      agrees: true,
      additions: addition.split(",").map((s) => s.trim()).filter(Boolean),
    });
    setAdditions((p) => ({ ...p, [questionId]: "" }));
    setOpenAdditionsFor((s) => {
      const n = new Set(s);
      n.delete(questionId);
      return n;
    });
    haptic("success");
  };

  const handleNextMember = () => {
    if (isLastMember) {
      handleFinish();
    } else {
      setCurrentMemberIdx((p) => p + 1);
      setCorrections({});
      setAdditions({});
      setOpenAdditionsFor(new Set());
      setDisagreeingFor(new Set());
      setExpandedDetailFor(new Set());
    }
  };

  const handleFinish = () => {
    markVerificationComplete();

    const disputed = COOK_INTERVIEW_QUESTIONS.filter((q) => {
      const summary = getVerificationSummary(q.id);
      return summary.disagrees > 0;
    });

    if (disputed.length > 0) {
      addNotification({
        type: "cook_changed",
        title: `${cookName}'s profile needs attention`,
        body: `${disputed.length} answer${disputed.length > 1 ? "s" : ""} were disputed by the household. Review in Settings → Cook.`,
        actionRoute: "/(tabs)/settings",
      });
    }

    addNotification({
      type: "cook_changed",
      title: `${cookName}'s profile verified`,
      body: `${activeMembers.length} member${activeMembers.length > 1 ? "s" : ""} reviewed the cook profile. ${disputed.length === 0 ? "All answers confirmed." : `${disputed.length} need review.`}`,
    });

    haptic("success");
    showAlert(
      "Profile verified",
      `${cookName}'s profile has been reviewed.${disputed.length > 0 ? `\n\n${disputed.length} answers were disputed — check Settings → Cook.` : " All answers confirmed."}`,
    );
    router.replace("/(tabs)");
  };

  const handleSkipVerification = () => {
    markVerificationComplete();
    router.replace("/(tabs)");
  };

  const formatAnswer = (answer: string | string[] | number | boolean | undefined): string => {
    if (answer === undefined || answer === null) return "—";
    if (Array.isArray(answer)) return answer.join(", ");
    if (typeof answer === "boolean") return answer ? "Yes" : "No";
    return String(answer);
  };

  const renderAnswerCard = (q: typeof COOK_INTERVIEW_QUESTIONS[0]) => {
    const answer = answers.find((a) => a.questionId === q.id);
    if (!answer) return null;

    const memberVerification = verifications.find(
      (v) => v.memberId === currentMember?.id && v.questionId === q.id,
    );
    const isVerified = memberVerification !== undefined;
    const allVerifications = verifications.filter((v) => v.questionId === q.id);
    const otherVerifications = allVerifications.filter((v) => v.memberId !== currentMember?.id);
    const summary = getVerificationSummary(q.id);
    const isDisagreeing = disagreeingFor.has(q.id);
    const isAdditionOpen = openAdditionsFor.has(q.id);
    const isDetailExpanded = expandedDetailFor.has(q.id);

    const accentColor = isVerified
      ? (memberVerification?.agrees ? colors.accent.success : colors.accent.danger)
      : colors.border.subtle;

    return (
      <View
        key={q.id}
        style={{
          ...cardStyles,
          marginBottom: spacing.md,
          borderLeftWidth: 3,
          borderLeftColor: accentColor,
        }}
      >
        {/* Question is the eyebrow; answer dominates. */}
        <Text style={{ ...typography.tiny, marginBottom: spacing.xs }}>{q.question}</Text>
        <Text style={{ ...typography.h3, marginBottom: spacing.sm }}>{formatAnswer(answer.answer)}</Text>
        <Text style={{ ...typography.tiny }}>
          Answered by {answer.answeredBy} · {answer.confidence}
        </Text>

        {/* Aggregate summary + collapsible per-member breakdown. */}
        {summary.total > 0 && (
          <View style={{ marginTop: spacing.sm, gap: 4 }}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
                <Ionicons name="thumbs-up" size={iconSize.xs} color={colors.accent.success} />
                <Text style={{ ...typography.tiny, color: colors.accent.success }}>{summary.agrees}</Text>
              </View>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
                <Ionicons name="thumbs-down" size={iconSize.xs} color={colors.accent.danger} />
                <Text style={{ ...typography.tiny, color: colors.accent.danger }}>{summary.disagrees}</Text>
              </View>
              {otherVerifications.length > 0 && (
                <TextLink
                  size="sm"
                  tone="secondary"
                  onPress={() => toggleSet(expandedDetailFor, q.id, setExpandedDetailFor)}
                  trailingIcon={isDetailExpanded ? "chevron-up" : "chevron-down"}
                >
                  {`${otherVerifications.length} other${otherVerifications.length === 1 ? "" : "s"} verified`}
                </TextLink>
              )}
            </View>

            {isDetailExpanded && (
              <View style={{ gap: 2, marginTop: 4 }}>
                {otherVerifications.map((v, i) => (
                  <View key={i} style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
                    <Ionicons
                      name={v.agrees ? "checkmark-circle" : "close-circle"}
                      size={iconSize.xs}
                      color={v.agrees ? colors.accent.success : colors.accent.danger}
                    />
                    <Text style={{ ...typography.tiny }} numberOfLines={2}>
                      {v.memberName}: {v.agrees ? "agrees" : "disagrees"}
                      {v.correction ? ` — "${v.correction}"` : ""}
                      {v.additions?.length ? ` — added: ${v.additions.join(", ")}` : ""}
                    </Text>
                  </View>
                ))}
              </View>
            )}
          </View>
        )}

        {/* Action area */}
        {!isVerified ? (
          <View style={{ marginTop: spacing.md, gap: spacing.sm }}>
            {/* Looks-right is the dominant action; not-quite is muted to speed the agree path. */}
            <View style={{ flexDirection: "row", gap: spacing.sm }}>
              <View style={{ flex: 2 }}>
                <Button
                  variant="success"
                  size="md"
                  fullWidth
                  leadingIcon="checkmark"
                  onPress={() => handleAgree(q.id)}
                >
                  Looks right
                </Button>
              </View>
              <View style={{ flex: 1 }}>
                <Button
                  variant="ghost"
                  size="md"
                  fullWidth
                  onPress={() => handleStartDisagree(q.id)}
                >
                  Not quite
                </Button>
              </View>
            </View>

            {/* Correction input — only shown after "Not quite" is tapped. */}
            {isDisagreeing && (
              <View style={{ gap: spacing.sm }}>
                <TextInput
                  value={corrections[q.id] || ""}
                  onChangeText={(v) => setCorrections((p) => ({ ...p, [q.id]: v }))}
                  placeholder="What's the correct answer?"
                  placeholderTextColor={colors.text.muted}
                  accessibilityLabel="Correction"
                  autoCapitalize="sentences"
                  returnKeyType="done"
                  style={{ ...inputStyles, borderWidth: 1, borderColor: colors.border.subtle }}
                  autoFocus
                />
                <Button
                  variant="primary"
                  size="md"
                  fullWidth
                  onPress={() => handleSubmitDisagree(q.id)}
                >
                  Submit correction
                </Button>
              </View>
            )}

            {/* "I know something else" — only shown after toggle. */}
            {isAdditionOpen ? (
              <View style={{ flexDirection: "row", gap: spacing.sm, alignItems: "center" }}>
                <TextInput
                  value={additions[q.id] || ""}
                  onChangeText={(v) => setAdditions((p) => ({ ...p, [q.id]: v }))}
                  placeholder="Add what you know (comma-separated)"
                  placeholderTextColor={colors.text.muted}
                  accessibilityLabel="Additional information (comma-separated)"
                  autoCapitalize="words"
                  returnKeyType="done"
                  style={{ ...inputStyles, flex: 1, borderWidth: 1, borderColor: colors.border.subtle }}
                />
                <Button
                  variant="secondary"
                  size="sm"
                  onPress={() => handleAddKnowledge(q.id)}
                >
                  Add
                </Button>
              </View>
            ) : (
              <TextLink
                size="sm"
                tone="primary"
                leadingIcon="add-circle-outline"
                onPress={() => toggleSet(openAdditionsFor, q.id, setOpenAdditionsFor)}
              >
                I know something else about this
              </TextLink>
            )}
          </View>
        ) : (
          <View style={{ marginTop: spacing.md, flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.sm }}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: 6, flex: 1 }}>
              <Ionicons
                name={memberVerification.agrees ? "checkmark-circle" : "close-circle"}
                size={iconSize.sm}
                color={memberVerification.agrees ? colors.accent.success : colors.accent.danger}
              />
              <Text
                style={{ ...typography.caption, color: memberVerification.agrees ? colors.accent.success : colors.accent.danger, flex: 1 }}
                numberOfLines={2}
              >
                {memberVerification.agrees ? "You confirmed this" : "You disputed this"}
                {memberVerification.correction ? ` — "${memberVerification.correction}"` : ""}
              </Text>
            </View>
            {typeof removeVerification === "function" && (
              <TextLink size="sm" tone="secondary" onPress={() => handleChangeMyAnswer(q.id)}>
                Change
              </TextLink>
            )}
          </View>
        )}
      </View>
    );
  };

  const sections = [...new Set(answeredQuestions.map((q) => q.section))];
  const verificationProgress = answeredQuestions.length > 0
    ? memberVerifiedCount / answeredQuestions.length
    : 0;

  return (
    <WizardLayout
      step={currentMemberIdx + 1}
      of={Math.max(activeMembers.length, 1)}
      title={`Verify ${cookName}'s Profile`}
      subtitle={`${currentMember?.name}, review what ${answers[0]?.answeredBy || "another member"} shared.`}
      primaryCTA={
        <Button
          variant="primary"
          size="lg"
          fullWidth
          leadingIcon={isLastMember ? "checkmark-circle" : "arrow-forward"}
          onPress={handleNextMember}
        >
          {isLastMember ? "Finish verification" : `Next: ${activeMembers[currentMemberIdx + 1]?.name}'s turn`}
        </Button>
      }
      secondaryCTA={
        <TextLink onPress={handleSkipVerification} size="sm" tone="secondary">
          Skip verification for now
        </TextLink>
      }
    >
      {/* Member tabs */}
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={{ gap: spacing.sm, marginBottom: spacing.lg }}
      >
        {activeMembers.map((member, i) => {
          const isCurrent = i === currentMemberIdx;
          const memberVCount = verifications.filter((v) => v.memberId === member.id).length;
          const isDone = memberVCount >= answeredQuestions.length && answeredQuestions.length > 0;
          return (
            <RipplePressable
              key={member.id}
              onPress={() => { setCurrentMemberIdx(i); haptic("selection"); }}
              haptic="selection"
              accessibilityRole="tab"
              accessibilityLabel={`${member.name}${isDone ? ", complete" : ""}`}
              accessibilityState={{ selected: isCurrent }}
              style={{
                flexDirection: "row", alignItems: "center", gap: 6,
                paddingHorizontal: 14, paddingVertical: 8, borderRadius: radius.pill,
                backgroundColor: isCurrent
                  ? colors.accent.primary
                  : isDone ? colors.accent.successDim : colors.surface.elevated,
                borderWidth: 1,
                borderColor: isCurrent
                  ? colors.accent.primary
                  : isDone ? colors.accent.success : colors.border.subtle,
              }}
            >
              <Avatar name={member.name} id={member.id} size="xs" />
              <Text
                style={{
                  ...typography.captionBold,
                  color: isCurrent ? colors.text.inverse : isDone ? colors.accent.success : colors.text.primary,
                }}
              >
                {member.name}
              </Text>
              {!isDone && memberVCount > 0 && (
                <Text style={{ ...typography.tiny, color: isCurrent ? colors.text.inverse : colors.text.muted }}>
                  {memberVCount}/{answeredQuestions.length}
                </Text>
              )}
              {isDone && (
                <Ionicons
                  name="checkmark-circle"
                  size={iconSize.xs}
                  color={isCurrent ? colors.text.inverse : colors.accent.success}
                />
              )}
            </RipplePressable>
          );
        })}
      </ScrollView>

      <View style={{ marginBottom: spacing.lg }}>
        <GuidanceTip
          variant="info"
          icon="people-outline"
          title="Everyone's input matters"
          message={`Each member confirms or corrects what's known about ${cookName}. You can change your answer anytime.`}
          compact
        />
      </View>

      {/* Per-member progress */}
      <View style={{ marginBottom: spacing.lg }}>
        <MeterBar
          value={verificationProgress}
          tone="primary"
          size="sm"
          label={`${currentMember?.name}: ${memberVerifiedCount} of ${answeredQuestions.length} reviewed`}
        />
      </View>

      {/* Answer cards grouped by section */}
      {sections.map((section) => {
        const sectionMeta = SECTION_META[section];
        const sectionAnswers = answeredQuestions.filter((q) => q.section === section);
        return (
          <View key={section} style={{ marginBottom: spacing.xl }}>
            <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, marginBottom: spacing.md }}>
              <Ionicons name={sectionMeta.icon as any} size={iconSize.sm} color={colors.text.secondary} />
              <SectionEyebrow tone="secondary" spaced={false}>{sectionMeta.label}</SectionEyebrow>
            </View>
            {sectionAnswers.map(renderAnswerCard)}
          </View>
        );
      })}
    </WizardLayout>
  );
}
