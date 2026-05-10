/**
 * Privacy Policy — in-app screen.
 *
 * Self-hosted because Bimi doesn't have a public website yet. Renders
 * the same content the App Store / Play Store listing references. Last
 * reviewed: May 2026.
 *
 * Brand-voice: calm, plain-language, no legalese fog. Each section
 * should be readable by a non-lawyer in under 30 seconds.
 */

import { ScrollView, Text, View } from "react-native";
import { GradientScreen } from "@/components/GradientScreen";
import { colors, spacing, typography } from "@/lib/theme";

const LAST_UPDATED = "May 2026";

export default function PrivacyPolicyScreen() {
  return (
    <GradientScreen>
      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: 96 }}
        showsVerticalScrollIndicator={false}
      >
        <Text style={typography.h1}>Privacy Policy</Text>
        <Text style={{ ...typography.caption, marginTop: 4 }}>
          Last updated {LAST_UPDATED}
        </Text>

        <Section title="The short version">
          We collect what we need to make Bimi work — your phone number,
          who's in your household, what your cook makes, what your family
          votes for, what's in your kitchen. We don't sell any of it. We
          don't share it with advertisers. You can delete your account
          and your data at any time.
        </Section>

        <Section title="What we collect">
          <Bullet>
            Your phone number, used only to sign you in and to send the
            occasional notification you've explicitly asked for.
          </Bullet>
          <Bullet>
            Household details you enter — names, dietary preferences,
            who pays for groceries, the cook's name and WhatsApp number.
          </Bullet>
          <Bullet>
            What your household votes for, what gets cooked, what gets
            rated. We use this to make next week's suggestions feel like
            yours and not a generic recipe blog.
          </Bullet>
          <Bullet>
            Inventory you log, expenses you split, the messages your
            cook leaves you.
          </Bullet>
          <Bullet>
            Anonymous crash reports if the app misbehaves — we strip
            phone numbers, OTPs, names, and addresses before they ever
            leave your device.
          </Bullet>
        </Section>

        <Section title="What we don't do">
          <Bullet>
            We don't sell your data — not now, not ever.
          </Bullet>
          <Bullet>
            We don't run third-party advertising trackers inside the
            app.
          </Bullet>
          <Bullet>
            We don't read your messages or contacts. The only contact we
            store is your cook's number, and only because you typed it
            in.
          </Bullet>
        </Section>

        <Section title="Who sees your data">
          <Bullet>
            Other people in your household, when you invite them.
            That's the whole point.
          </Bullet>
          <Bullet>
            When you place an order through a grocery partner like
            Swiggy Instamart, Zepto, or Blinkit, your cart is sent to
            them through their own app. We don't store what you bought
            on those platforms.
          </Bullet>
          <Bullet>
            When you message your cook, we hand off to WhatsApp using
            the number you've saved. WhatsApp's own terms apply to that
            conversation.
          </Bullet>
          <Bullet>
            If we add a feature that needs to share data with a new
            partner, we'll tell you before turning it on.
          </Bullet>
        </Section>

        <Section title="Where it lives">
          Your data sits on servers we run, in India. It travels there
          over an encrypted connection. Backups are encrypted too.
        </Section>

        <Section title="How long we keep it">
          As long as your account is active. When you delete your
          account, we wipe the household, votes, ratings, inventory,
          and expenses within 30 days. Some anonymous aggregate
          statistics may stay so we can improve suggestions, but they
          can't be traced back to you.
        </Section>

        <Section title="Children">
          Bimi is meant for adults running a household. If you're under
          18, please ask a parent or guardian before using it.
        </Section>

        <Section title="Your choices">
          <Bullet>
            You can edit or delete any household member, cook, or piece
            of inventory you've added — directly from the app.
          </Bullet>
          <Bullet>
            You can turn off any kind of notification under
            Settings → Notifications.
          </Bullet>
          <Bullet>
            You can delete your entire account from
            Settings → Account → Delete account. Everything tied to your
            phone number is removed.
          </Bullet>
        </Section>

        <Section title="When this changes">
          If we update this policy in a way that materially affects what
          we collect or how we share it, we'll let you know inside the
          app the next time you open it. Small wording fixes won't
          trigger a notice.
        </Section>

        <Section title="Reach us">
          <Text
            style={{
              ...typography.body,
              color: colors.text.secondary,
              lineHeight: 22,
            }}
          >
            Questions or concerns? Write to{" "}
            <Text style={{ color: colors.accent.primary }}>dasanjan1296@gmail.com</Text>
            {" "}— a real human reads it.
          </Text>
        </Section>
      </ScrollView>
    </GradientScreen>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <View style={{ marginTop: spacing.xl }}>
      <Text style={{ ...typography.h3, fontSize: 17 }}>{title}</Text>
      {typeof children === "string" ? (
        <Text
          style={{
            ...typography.body,
            color: colors.text.secondary,
            marginTop: spacing.sm,
            lineHeight: 22,
          }}
        >
          {children}
        </Text>
      ) : (
        <View style={{ marginTop: spacing.sm }}>{children}</View>
      )}
    </View>
  );
}

function Bullet({ children }: { children: React.ReactNode }) {
  return (
    <View style={{ flexDirection: "row", marginBottom: spacing.sm }}>
      <Text
        style={{
          ...typography.body,
          color: colors.accent.primary,
          marginRight: spacing.sm,
          lineHeight: 22,
        }}
      >
        •
      </Text>
      <Text
        style={{
          ...typography.body,
          color: colors.text.secondary,
          flex: 1,
          lineHeight: 22,
        }}
      >
        {children}
      </Text>
    </View>
  );
}
