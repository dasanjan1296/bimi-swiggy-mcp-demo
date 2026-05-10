import { View, Text, ScrollView, Pressable } from "react-native";
import { useMemo } from "react";

import { colors, spacing, radius, typography } from "@/lib/theme";
import { haptic } from "@/lib/haptics";

export interface DateScrubberProps {
  /** YYYY-MM-DD */
  selectedDate: string;
  /** How many days to render starting from today (defaults to 7). */
  days?: number;
  onChange: (date: string) => void;
}

const DAY_LABELS_SHORT = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

/**
 * F9: Horizontal date chips for the next N days. The chip for today is
 * labelled "Today", tomorrow is "Tomorrow", everything else uses the day
 * name + day-of-month so users can scrub a whole week.
 */
export function DateScrubber({
  selectedDate,
  days = 7,
  onChange,
}: DateScrubberProps) {
  const items = useMemo(() => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const out: { date: string; label: string; sub: string }[] = [];
    for (let i = 0; i < days; i++) {
      const d = new Date(today);
      d.setDate(d.getDate() + i);
      const yyyy = d.getFullYear();
      const mm = (d.getMonth() + 1).toString().padStart(2, "0");
      const dd = d.getDate().toString().padStart(2, "0");
      const date = `${yyyy}-${mm}-${dd}`;
      let label: string;
      let sub: string;
      if (i === 0) {
        label = "Today";
        sub = `${DAY_LABELS_SHORT[d.getDay()]} ${d.getDate()}`;
      } else if (i === 1) {
        label = "Tomorrow";
        sub = `${DAY_LABELS_SHORT[d.getDay()]} ${d.getDate()}`;
      } else {
        label = DAY_LABELS_SHORT[d.getDay()];
        sub = d.getDate().toString();
      }
      out.push({ date, label, sub });
    }
    return out;
  }, [days]);

  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={{ gap: spacing.sm, paddingHorizontal: 0, paddingVertical: spacing.xs }}
    >
      {items.map((item) => {
        const isSelected = item.date === selectedDate;
        return (
          <Pressable
            key={item.date}
            onPress={() => {
              haptic("selection");
              onChange(item.date);
            }}
            accessibilityLabel={`${item.label}, ${item.sub}${isSelected ? ", selected" : ""}`}
            accessibilityState={{ selected: isSelected }}
            style={{
              minWidth: 76,
              paddingHorizontal: 14,
              paddingVertical: 10,
              borderRadius: radius.md,
              backgroundColor: isSelected ? colors.accent.primary : colors.surface.card,
              borderWidth: 1,
              borderColor: isSelected ? colors.accent.primary : colors.border.subtle,
              alignItems: "center",
            }}
          >
            <Text
              style={{
                ...typography.captionBold,
                color: isSelected ? colors.text.inverse : colors.text.primary,
              }}
            >
              {item.label}
            </Text>
            <Text
              style={{
                ...typography.tiny,
                color: isSelected ? colors.text.inverse : colors.text.muted,
                marginTop: 1,
                opacity: isSelected ? 0.8 : 1,
              }}
            >
              {item.sub}
            </Text>
          </Pressable>
        );
      })}
    </ScrollView>
  );
}
