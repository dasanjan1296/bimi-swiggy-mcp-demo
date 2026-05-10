import { Text, TouchableOpacity } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useEffect, useState } from "react";

import { showAlert } from "@/lib/dialogs";
import { formatRemaining, type ComputedDeadline } from "@/lib/voting-deadlines";
import { colors, spacing, radius, typography } from "@/lib/theme";

export interface CountdownPillProps {
  deadline: ComputedDeadline;
  /** Fires once when the countdown crosses to expired. */
  onExpired?: () => void;
}

/**
 * P3 (PRD 4.11): Live ticking deadline pill, refreshes every 60s.
 * Color escalates from muted → warning (under 2 hr) → danger (under 30 min).
 * Tappable to show the deadline rationale (why this time was chosen).
 */
export function CountdownPill({ deadline, onExpired }: CountdownPillProps) {
  const [tick, setTick] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 60_000);
    return () => clearInterval(id);
  }, []);

  const remaining = formatRemaining(deadline.date);

  // Fire onExpired exactly once per pill mount when crossing the cutoff.
  useEffect(() => {
    if (remaining.expired && onExpired) onExpired();
  }, [remaining.expired]); // eslint-disable-line react-hooks/exhaustive-deps

  const palette = remaining.expired
    ? { fg: colors.text.muted, bg: colors.surface.glass, border: colors.border.subtle }
    : remaining.urgent
      ? { fg: colors.accent.danger, bg: colors.accent.dangerDim, border: colors.accent.danger }
      : { fg: colors.accent.warning, bg: colors.accent.warningDim, border: colors.accent.warning };

  const onTap = () => {
    showAlert(
      remaining.expired ? "Voting closed" : "Voting deadline",
      `${deadline.rationale}${
        remaining.expired
          ? " Bimi has filled in proxy votes for anyone who didn't pick."
          : ""
      }`,
    );
  };

  return (
    <TouchableOpacity
      onPress={onTap}
      accessibilityLabel={
        remaining.expired
          ? "Voting closed. Tap for details."
          : `${remaining.label}. Tap for details.`
      }
      style={{
        flexDirection: "row",
        alignItems: "center",
        gap: 6,
        alignSelf: "flex-start",
        paddingHorizontal: 10,
        paddingVertical: 4,
        borderRadius: radius.sm,
        backgroundColor: palette.bg,
        borderWidth: 1,
        borderColor: palette.border,
      }}
    >
      <Ionicons
        name={remaining.expired ? "lock-closed" : "time"}
        size={12}
        color={palette.fg}
      />
      <Text style={{ ...typography.tiny, color: palette.fg, fontWeight: "700" }}>
        {remaining.expired ? "Closed" : remaining.label}
      </Text>
    </TouchableOpacity>
  );
}

