/**
 * Login — three-step credential capture (phone → OTP → profile).
 *
 * Strict design-system citizen: every visual decision routes through
 * the canonical `<AuthScreen>` scaffold + `<InputField>` + `<OtpInput>`
 * + `<Button>` + `<TextLink>` atoms. No bespoke chrome.
 *
 * Previous (pre-overhaul) version embedded:
 *   - A custom `<PrimaryCTA>` with hand-rolled glow shadows, a fake
 *     gradient inner-highlight, and amber tinting that didn't translate
 *     to the light theme.
 *   - An auto-rotating "proof" carousel selling Bimi to the visitor.
 *     That's marketing content; it has no place on a credential-capture
 *     screen (see design-system.md §8.5).
 *   - Hand-rolled phone, OTP, and name inputs that bypassed the strict
 *     accessibility + autofill defaults baked into <InputField> and
 *     <OtpInput>.
 *
 * All of that is gone. The screen is now three Airbnb-style auth steps:
 * brand mark → headline → form → primary action → tertiary links.
 */

import React, { useEffect, useState } from "react";
import { useRouter } from "expo-router";
import { useAuthStore } from "@/lib/auth-store";
import { sendOtp, verifyOtp, completeProfile } from "@/lib/api";
import { haptic } from "@/lib/haptics";
import { showAlert } from "@/lib/dialogs";
import { InputField, OtpInput, TextLink } from "@/components/ui";
import { AuthScreen } from "@/components/patterns";
import { Text, View } from "react-native";
import { colors, spacing, typography } from "@/lib/theme";

type Step = "phone" | "otp" | "profile";

export default function LoginScreen() {
  const router = useRouter();
  const setAuth = useAuthStore((s) => s.setAuth);
  const setDemo = useAuthStore((s) => s.setDemo);

  const [step, setStep] = useState<Step>("phone");
  const [phone, setPhone] = useState("");
  const [otp, setOtp] = useState("");
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [pendingToken, setPendingToken] = useState("");
  const [resendTimer, setResendTimer] = useState(0);

  useEffect(() => {
    if (resendTimer <= 0) return;
    const t = setTimeout(() => setResendTimer(resendTimer - 1), 1000);
    return () => clearTimeout(t);
  }, [resendTimer]);

  // ── Step handlers ─────────────────────────────────────────────────────

  const handleSendOtp = async () => {
    haptic("light");
    const cleaned = phone.replace(/\s/g, "");
    if (cleaned.length < 10) {
      showAlert("Invalid phone", "Please enter a valid phone number.");
      return;
    }

    setLoading(true);
    try {
      const result = await sendOtp(cleaned);
      // QA-036 fix: only autofill the OTP fields in dev builds. Defense-in-depth
      // even if the backend mistakenly returns dev_otp in production.
      if (__DEV__ && result.dev_otp) {
        setOtp(result.dev_otp);
      }
      setStep("otp");
      setResendTimer(30);
    } catch (error: any) {
      const msg = error.response?.data?.detail || "Could not send OTP. Please try again.";
      showAlert("Error", msg);
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyOtp = async () => {
    haptic("light");
    if (otp.length !== 6) {
      showAlert("Invalid OTP", "Please enter the complete 6-digit code.");
      return;
    }

    setLoading(true);
    try {
      const result = await verifyOtp(phone.replace(/\s/g, ""), otp);
      if (result.is_new_user) {
        setPendingToken(result.pending_token || "");
        setStep("profile");
      } else {
        setAuth({
          token: result.access_token!,
          familyId: result.family_id!,
          childId: result.child_id!,
          childName: result.child_name || phone,
        });
        haptic("success");
        router.replace("/(tabs)");
      }
    } catch (error: any) {
      const msg = error.response?.data?.detail || "Invalid OTP. Please try again.";
      showAlert("Verification failed", msg);
    } finally {
      setLoading(false);
    }
  };

  const handleCompleteProfile = async () => {
    haptic("light");
    if (!name.trim()) {
      showAlert("Missing name", "Please enter your name to continue.");
      return;
    }

    setLoading(true);
    try {
      const result = await completeProfile(pendingToken, name.trim());
      setAuth({
        token: result.access_token,
        familyId: result.family_id,
        childId: result.child_id,
        childName: result.child_name,
      });
      haptic("success");
      router.replace("/(tabs)");
    } catch (error: any) {
      const msg = error.response?.data?.detail || "Profile setup failed. Please try again.";
      showAlert("Error", msg);
    } finally {
      setLoading(false);
    }
  };

  const handleDemoMode = () => {
    haptic("success");
    // setDemo() vs setAuth() — keeps isDemo flag consistent with what
    // isDemoMode()/isRealAuth() check.
    setDemo("fam-001", "child-001", "Anjan");
    router.replace("/(tabs)");
  };

  // ── Step UIs ─────────────────────────────────────────────────────────

  if (step === "phone") {
    const tertiaryLinks = [
      { label: "Have an invite code? Join a house", onPress: () => router.push("/join-house") },
      ...(__DEV__
        ? [{ label: "Try demo mode", onPress: handleDemoMode, testID: "auth-demo-link" }]
        : []),
    ];

    return (
      <AuthScreen
        title="The kitchen, off your mind."
        subtitle="Meals, cook, groceries — all of it, sorted."
        primaryAction={{
          label: loading ? "Sending OTP…" : "Continue",
          loading,
          disabled: phone.replace(/\s/g, "").length < 10,
          onPress: handleSendOtp,
        }}
        tertiaryLinks={tertiaryLinks}
      >
        <InputField
          label="Phone number"
          value={phone}
          onChangeText={setPhone}
          kind="phone"
          placeholder="+91 98765 43210"
          accessibilityLabel="Phone number"
        />
      </AuthScreen>
    );
  }

  if (step === "otp") {
    return (
      <AuthScreen
        title="Enter the code"
        subtitle={`We sent a 6-digit code to ${phone}.`}
        onBack={() => {
          setStep("phone");
          setOtp("");
        }}
        primaryAction={{
          label: loading ? "Verifying…" : "Verify",
          loading,
          disabled: otp.length !== 6,
          onPress: handleVerifyOtp,
        }}
        tertiaryLinks={
          resendTimer > 0
            ? []
            : [{ label: "Didn't get it? Resend code", onPress: handleSendOtp }]
        }
      >
        <OtpInput value={otp} onChange={setOtp} />
        {resendTimer > 0 ? (
          <View style={{ alignItems: "center", marginTop: spacing.sm }}>
            <Text style={{ ...typography.small, color: colors.text.muted }}>
              You can resend the code in {resendTimer}s
            </Text>
          </View>
        ) : null}
      </AuthScreen>
    );
  }

  return (
    <AuthScreen
      title="One last thing"
      subtitle="What should your household call you?"
      primaryAction={{
        label: loading ? "Setting up…" : "Let's go",
        loading,
        disabled: !name.trim(),
        onPress: handleCompleteProfile,
      }}
    >
      <InputField
        label="Your name"
        value={name}
        onChangeText={setName}
        kind="name"
        placeholder="Anjan"
        hint="This is the name your household will see."
        autoFocus
      />
    </AuthScreen>
  );
}
