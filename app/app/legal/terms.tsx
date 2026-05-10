/**
 * Terms of Service — in-app screen.
 *
 * Self-hosted because Bimi doesn't have a public website yet. Plain-
 * language draft; full legal review before public-store submission.
 * Last reviewed: May 2026.
 */

import { ScrollView, Text, View } from "react-native";
import { GradientScreen } from "@/components/GradientScreen";
import { colors, spacing, typography } from "@/lib/theme";

const LAST_UPDATED = "May 2026";

export default function TermsOfServiceScreen() {
  return (
    <GradientScreen>
      <ScrollView
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: 96 }}
        showsVerticalScrollIndicator={false}
      >
        <Text style={typography.h1}>Terms of Service</Text>
        <Text style={{ ...typography.caption, marginTop: 4 }}>
          Last updated {LAST_UPDATED}
        </Text>

        <Section title="The short version">
          Bimi helps Indian households plan meals, coordinate with their
          cook, and manage groceries. By using the app you agree to use
          it the way it's meant to be used. We try to keep it running
          well, but a meal-planner can't promise miracles. If something
          goes sideways, please tell us so we can fix it.
        </Section>

        <Section title="What Bimi is">
          A coordination tool for your household. Bimi suggests meals,
          collects votes, helps you talk to your cook, and lets you
          place grocery orders through partner platforms. Bimi is not
          itself a restaurant, a grocery store, or a cook.
        </Section>

        <Section title="Your account">
          <Bullet>
            You sign in with your phone number. Don't share your account
            with people outside your household — give them a household
            invite instead.
          </Bullet>
          <Bullet>
            You're responsible for what you and your household members
            do inside the app.
          </Bullet>
          <Bullet>
            Keep your phone number current. We use it to send you the
            sign-in OTP and a few notifications.
          </Bullet>
        </Section>

        <Section title="Acceptable use">
          <Bullet>
            Don't use Bimi to harass, defame, or share illegal content.
          </Bullet>
          <Bullet>
            Don't try to scrape, reverse-engineer, or break the app's
            security. We rate-limit suspicious activity.
          </Bullet>
          <Bullet>
            Don't impersonate someone else's household, cook, or grocery
            account.
          </Bullet>
        </Section>

        <Section title="Cooks">
          When you save your cook's WhatsApp number, Bimi will hand off
          messages and meal plans to WhatsApp on your tap. We're a
          coordination layer — Bimi doesn't employ your cook, doesn't
          set their wages, and doesn't take a cut of what you pay them.
          That relationship is yours.
        </Section>

        <Section title="Grocery orders">
          Carts you build inside Bimi are placed on partner platforms
          (Swiggy Instamart, Zepto, Blinkit, BigBasket, JioMart, DMart
          Ready). The order, fulfilment, refunds, and customer support
          for that delivery sit with the platform's own terms. If a
          tomato shows up rotten, take it up with them — we'll help you
          figure out where to look.
        </Section>

        <Section title="Payments">
          Bimi is currently free to use. If we add paid features, we'll
          tell you before charging anything. Any future payments will be
          processed by a regulated Indian payment partner; Bimi never
          stores your card or UPI credentials.
        </Section>

        <Section title="What we can't promise">
          <Bullet>
            That a meal suggestion will always be exactly what your
            household wants.
          </Bullet>
          <Bullet>
            That a grocery partner will always have stock, deliver on
            time, or deliver at all.
          </Bullet>
          <Bullet>
            That a cook will always show up. We help you plan around
            absences, but we don't guarantee them.
          </Bullet>
          <Bullet>
            That the app will be available 24/7. We aim for it, but
            occasional downtime for upgrades is part of life.
          </Bullet>
        </Section>

        <Section title="Limitation of liability">
          To the extent allowed by law, Bimi and its team aren't liable
          for indirect or consequential losses — like a missed dinner, a
          delayed delivery, or a household disagreement over chole vs
          rajma. We will, of course, fix bugs and refund anything we
          incorrectly charged.
        </Section>

        <Section title="Ending things">
          You can delete your account at any time from
          Settings → Account → Delete account. We can suspend or end an
          account if it's being used to harass others, abuse the
          service, or break the law — we'll tell you why.
        </Section>

        <Section title="Updates to these terms">
          If we change these terms in a way that materially affects you,
          we'll let you know inside the app the next time you open it.
          Continued use after a change means you accept the new terms.
        </Section>

        <Section title="Governing law">
          These terms are governed by the laws of India. Disputes that
          can't be sorted out by talking to us go to the courts of
          Bengaluru, Karnataka.
        </Section>

        <Section title="Reach us">
          <Text
            style={{
              ...typography.body,
              color: colors.text.secondary,
              lineHeight: 22,
            }}
          >
            Questions about these terms? Write to{" "}
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
