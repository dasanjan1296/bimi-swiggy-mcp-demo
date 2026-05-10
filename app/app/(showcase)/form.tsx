/**
 * Form showcase. Reference layout for any input-heavy screen — household
 * setup, dietary preferences, cook profile, feedback. Demonstrates:
 *
 *   - ScreenHeader with back button
 *   - FormSection with title + helper
 *   - InputField in default / focus / error states
 *   - Pill-row selector for enum fields
 *   - SettingsRow toggles
 *   - Sticky footer with single primary submit + ghost cancel
 *
 * Strict rules visible here:
 *   - Labels above inputs (no floating placeholders).
 *   - Errors render as helper text, never silent.
 *   - One primary action in the footer.
 */

import React, { useState } from "react";
import { ScrollView, Switch, View } from "react-native";
import { safeBack } from "@/lib/safe-back";
import {
  Button,
  InputField,
  Pill,
  SafeScreen,
  ScreenHeader,
  SettingsRow,
  TextLink,
} from "@/components/ui";
import { FormSection } from "@/components/patterns";
import { colors, spacing } from "@/lib/theme";

export default function FormShowcase() {
  const [name, setName] = useState("Anjan");
  const [email, setEmail] = useState("invalid-email");
  const [phone, setPhone] = useState("");
  const [diet, setDiet] = useState<"veg" | "non-veg" | "vegan" | "jain">("veg");
  const [whatsappAlerts, setWhatsappAlerts] = useState(true);
  const [pushAlerts, setPushAlerts] = useState(false);
  const [emailDigest, setEmailDigest] = useState(true);

  const emailError = email && !email.includes("@") ? "Enter a valid email" : "";

  return (
    <SafeScreen>
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{
          padding: spacing.lg,
          paddingBottom: spacing.xxxl,
        }}
        keyboardShouldPersistTaps="handled"
      >
        <ScreenHeader title="Profile" subtitle="Tell me a bit about you" back />

        <FormSection title="About you" topSpacing={0}>
          <InputField
            label="Your name"
            value={name}
            onChangeText={setName}
            kind="name"
          />
          <InputField
            label="Email"
            value={email}
            onChangeText={setEmail}
            kind="email"
            errorText={emailError}
            hint="We'll only use this for important account changes."
          />
          <InputField
            label="Phone (optional)"
            value={phone}
            onChangeText={setPhone}
            kind="phone"
            hint="So your cook can reach you when you're away."
          />
        </FormSection>

        <FormSection
          title="Dietary preference"
          helper="I'll make sure tomorrow's suggestions match."
        >
          <View style={{ flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" }}>
            <Pill active={diet === "veg"} onPress={() => setDiet("veg")}>
              Vegetarian
            </Pill>
            <Pill active={diet === "non-veg"} onPress={() => setDiet("non-veg")}>
              Non-vegetarian
            </Pill>
            <Pill active={diet === "vegan"} onPress={() => setDiet("vegan")}>
              Vegan
            </Pill>
            <Pill active={diet === "jain"} onPress={() => setDiet("jain")}>
              Jain
            </Pill>
          </View>
        </FormSection>

        <FormSection title="Notifications" helper="How should I reach you?">
          <View
            style={{
              backgroundColor: colors.surface.card,
              borderRadius: 16,
              paddingHorizontal: spacing.lg,
            }}
          >
            <SettingsRow
              label="WhatsApp updates"
              description="Cook messages and order approvals"
              trailing={
                <Switch
                  value={whatsappAlerts}
                  onValueChange={setWhatsappAlerts}
                  trackColor={{ true: colors.accent.primary, false: colors.border.subtle }}
                />
              }
            />
            <SettingsRow
              label="Push notifications"
              description="In-app alerts when your phone is unlocked"
              trailing={
                <Switch
                  value={pushAlerts}
                  onValueChange={setPushAlerts}
                  trackColor={{ true: colors.accent.primary, false: colors.border.subtle }}
                />
              }
            />
            <SettingsRow
              label="Weekly digest email"
              description="Summary of meals, savings, and household activity"
              trailing={
                <Switch
                  value={emailDigest}
                  onValueChange={setEmailDigest}
                  trackColor={{ true: colors.accent.primary, false: colors.border.subtle }}
                />
              }
              isLast
            />
          </View>
        </FormSection>
      </ScrollView>

      <View
        style={{
          padding: spacing.lg,
          gap: spacing.sm,
          backgroundColor: colors.surface.base,
          borderTopWidth: 1,
          borderTopColor: colors.border.hairline,
        }}
      >
        <Button
          variant="primary"
          fullWidth
          onPress={() => safeBack()}
          disabled={!!emailError}
        >
          Save changes
        </Button>
        <View style={{ alignItems: "center" }}>
          <TextLink onPress={() => safeBack()}>Cancel</TextLink>
        </View>
      </View>
    </SafeScreen>
  );
}
