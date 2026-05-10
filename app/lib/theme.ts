/**
 * Bimi design tokens — single source of truth.
 *
 * Strict, opinionated, light-first. Every screen, atom, and pattern in the
 * app reads from this file. Hardcoded hex literals in any other file are a
 * design-system violation (see bimi/app/design-system.md §Enforcement).
 *
 * Direction: Stripe / Notion / Airbnb-inspired — bright off-white surfaces,
 * Rausch coral accent, generous whitespace, soft cool shadows, photo-led
 * cards. The dark premium palette that lived here previously was retired
 * during the design system overhaul; commits prior to that retain it.
 */

import { StyleSheet, ViewStyle, TextStyle } from "react-native";

// ─── Typeface ────────────────────────────────────────────────────────────────
// Plus Jakarta Sans is the closest free analogue to Airbnb's Cereal — clean
// grotesque with humanist warmth. Three weights only (400 / 600 / 700) keep
// the type system simple; UI doesn't need the medium and extrabold variants.

export const fontFamily = {
  regular: "PlusJakartaSans_400Regular",
  medium: "PlusJakartaSans_500Medium",
  semibold: "PlusJakartaSans_600SemiBold",
  bold: "PlusJakartaSans_700Bold",
  extrabold: "PlusJakartaSans_800ExtraBold",
} as const;

// ─── Color tokens ───────────────────────────────────────────────────────────
// Hard rules — see design-system.md §Color for the full table:
//   • Only 4 surfaces. No mid-grays outside this set.
//   • Only 4 text tones. Don't invent new grays.
//   • accent.primary (Rausch) is reserved for the SINGLE primary action,
//     active state, link, or brand mark on a screen. Never decorative.
//   • Each accent has one Dim companion (~12% alpha equivalent, opaque)
//     for tinted backgrounds. Never fabricate intermediate alphas inline.

export const colors = {
  surface: {
    /** Default screen background — pure white. */
    base: "#FFFFFF",
    /** Card and grouped-row background — Airbnb's neutral gray. */
    card: "#F7F7F7",
    /** Elevated cards (white + shadow). Use with `elevation.low` or `mid`. */
    elevated: "#FFFFFF",
    /** Inputs — same as card by default; switch to white on focus. */
    input: "#F7F7F7",
    /**
     * Deprecated alias — "glass" was a translucent dark surface in the
     * previous theme. Kept as a compat shim so existing screen imports
     * (login, cook-chat, dish-cart, membership, etc.) still resolve.
     * Prefer `surface.card` in new code.
     */
    glass: "#F7F7F7",
    /** Tab bar background (slight transparency for under-content blur). */
    tabBar: "#FFFFFFF2",
    /** Disabled controls. */
    disabled: "#EBEBEB",
    /** Modal / bottom-sheet scrim. Lighter than dark-theme equivalent. */
    scrim: "rgba(0,0,0,0.45)",
    /** Very light warm cream — used as the Home tab background so the
     *  white day cards inside the bounded calendar viewport read as
     *  lifted surfaces against a softer ambient. Subtle enough that
     *  it doesn't compete with the warning amber palette. */
    warm: "#FFFAEB",
  },
  border: {
    /** Hairline divider between rows. */
    hairline: "#EBEBEB",
    /** Default 1px outline (cards, inputs, pills). */
    subtle: "#DDDDDD",
    /** Selected / focused outline — dark, NOT Rausch. Airbnb pattern. */
    active: "#222222",
    /** Lower-contrast variant — nested borders only. */
    muted: "#F0F0F0",
  },
  divider: {
    default: "#EBEBEB",
    strong: "#DDDDDD",
  },
  text: {
    /** Body and headings. ~15:1 on white — AAA. */
    primary: "#222222",
    /** Captions, metadata. ~5.5:1 on white — AA. */
    secondary: "#717171",
    /** Disabled / decorative. Never load-bearing copy. */
    muted: "#B0B0B0",
    /** Text on saturated brand fills (Rausch buttons, etc). */
    inverse: "#FFFFFF",
    /** Pure black — sparingly. */
    contrast: "#000000",
  },
  accent: {
    /** Rausch — the signature accent. Reserved for primary CTA + brand. */
    primary: "#FF385C",
    /** Tinted background for primary-toned chips, banners, hero cards. */
    primaryDim: "#FFE9EE",
    /** Pressed / hover state for the primary accent. */
    secondary: "#E61E4D",
    /** Verified / approved. */
    success: "#008A05",
    successDim: "#E8F5E9",
    /** Errors and destructive actions. */
    danger: "#C13515",
    dangerDim: "#FFF1EE",
    /** Warnings, soft urgency. */
    warning: "#FFB400",
    warningDim: "#FFF7E0",
    /** Informational state. */
    info: "#0A66C2",
    infoDim: "#E8F2FB",
    /** AI / system-generated content. */
    ai: "#7B5CFA",
    aiDim: "#F1ECFE",
    whatsapp: "#25D366",
  },
  // Cuisine accent palette — used on the Discover catalog. Translated to
  // light-friendly tints (was darker rgba on the dark theme).
  cuisine: {
    all: "#FFE9EE",
    north_indian: "#FFE9EE",
    bengali: "#F1ECFE",
    south_indian: "#E8F5E9",
    hyderabadi: "#FFF7E0",
  },
  // Ribbon badges on dish/meal cards. Saturated tones for legibility on
  // photo cards.
  ribbon: {
    bestsellerBg: "#FF385C", bestsellerFg: "#FFFFFF",
    chefPickBg: "#7B5CFA",   chefPickFg: "#FFFFFF",
    quickBg: "#008A05",      quickFg: "#FFFFFF",
    newBg: "#FFB400",        newFg: "#3A2A00",
  },
  // Third-party brand colors — only place outside this file allowed to hold
  // hex literals. Used to render "Send to Swiggy/Blinkit/etc" affordances.
  brand: {
    youtube: "#FF0000",
    instagram: "#E1306C",
    swiggy: "#FF6B00",
    blinkit: "#F5C518",
    bigbasket: "#86B049",
    zepto: "#7B3FE4",
    amazon: "#FF9900",
    flipkart: "#2874F0",
  },
  status: {
    cooking: "#FF385C",
    delivered: "#008A05",
    pending: "#717171",
    urgent: "#C13515",
  },
  // Shadow base — RN's shadowColor needs an opaque base; alpha lives on
  // shadowOpacity (see `elevation` below).
  shadow: {
    default: "#000000",
  },
  tab: {
    active: "#FF385C",
    inactive: "#717171",
    background: "#FFFFFF",
    border: "#EBEBEB",
  },
  // Deterministic per-person palette for avatars / chips. Index =
  // hash(memberId) % persons.length so the same member is consistently the
  // same color across the app. Values rebalanced for white surfaces.
  persons: [
    "#FF385C", // Rausch
    "#E07A5F", // coral
    "#7B5CFA", // violet
    "#0A66C2", // blue
    "#008A05", // green
    "#FFB400", // amber
    "#C13515", // brick
    "#22A6B3", // teal
  ],
} as const;

// Opacity levels used by `tintedBg()` and any dim-background pattern.
// Replaces ad-hoc `${color}18 / 20 / 30 / 40` string concatenations.
export const tint = {
  /** 1px outline around a tinted surface. */
  hairline: 0.20,
  /** Default tinted background (chip / banner). */
  fill: 0.12,
  /** High-emphasis tint. */
  strong: 0.30,
} as const;

// ─── Iconography ────────────────────────────────────────────────────────────
// Strict ladder. No `size={11}` / `size={13}` / `size={17}` chaos.

export const iconSize = {
  xs: 14,  // pill leading icons, micro chips
  sm: 16,  // button leading icons, list-row chevrons
  md: 20,  // section icons, content icons
  lg: 24,  // header back-arrow, IconButton md icon
  xl: 32,  // hero illustrations
  xxl: 48, // empty-state illustrations, brand mark
} as const;

// ─── Spacing — strict 4 pt grid ─────────────────────────────────────────────
// Group items use sm/md, sections use xl/xxl, screens use xxxl between bands.
// Anything outside this scale (e.g. `marginTop: 6`) is a design-system
// violation. See design-system.md §Spacing.

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
  xxxl: 48,
} as const;

// ─── Radius ladder ──────────────────────────────────────────────────────────
// Buttons = sm (8). Cards = lg (16). Photo cards = xl (20). Pills = pill.
// Inputs = md (12). Don't invent intermediates.

export const radius = {
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 24,
  pill: 100,
} as const;

// ─── Type scale ─────────────────────────────────────────────────────────────
// Hero / H1 / H2 / H3 / body / caption / small / tiny.
// Three weights only — 400 / 600 / 700.

export const typography = {
  hero: { fontSize: 44, fontWeight: "700" as const, fontFamily: fontFamily.bold, color: colors.text.primary, letterSpacing: -0.5 },
  h1: { fontSize: 32, fontWeight: "700" as const, fontFamily: fontFamily.bold, color: colors.text.primary, letterSpacing: -0.4 },
  h2: { fontSize: 22, fontWeight: "700" as const, fontFamily: fontFamily.bold, color: colors.text.primary, letterSpacing: -0.2 },
  h3: { fontSize: 16, fontWeight: "600" as const, fontFamily: fontFamily.semibold, color: colors.text.primary },
  body: { fontSize: 15, fontWeight: "400" as const, fontFamily: fontFamily.regular, color: colors.text.primary, lineHeight: 22 },
  bodyBold: { fontSize: 15, fontWeight: "600" as const, fontFamily: fontFamily.semibold, color: colors.text.primary, lineHeight: 22 },
  caption: { fontSize: 13, fontWeight: "400" as const, fontFamily: fontFamily.regular, color: colors.text.secondary, lineHeight: 18 },
  captionBold: { fontSize: 13, fontWeight: "600" as const, fontFamily: fontFamily.semibold, color: colors.text.secondary },
  small: { fontSize: 12, fontWeight: "400" as const, fontFamily: fontFamily.regular, color: colors.text.secondary },
  smallBold: { fontSize: 12, fontWeight: "600" as const, fontFamily: fontFamily.semibold, color: colors.text.secondary },
  tiny: { fontSize: 11, fontWeight: "400" as const, fontFamily: fontFamily.regular, color: colors.text.muted },
  tinyBold: { fontSize: 11, fontWeight: "700" as const, fontFamily: fontFamily.bold, color: colors.text.secondary },
  // Bottom-tab labels — 11px is the floor per HIG/Material.
  tabLabel: { fontSize: 11, fontWeight: "600" as const, fontFamily: fontFamily.semibold },
  display: { fontSize: 44, fontWeight: "700" as const, fontFamily: fontFamily.bold, color: colors.text.primary, letterSpacing: -0.5 },
  brandMark: { fontSize: 48, fontWeight: "700" as const, fontFamily: fontFamily.bold, color: colors.accent.primary },
  otp: { fontSize: 32, fontWeight: "700" as const, fontFamily: fontFamily.bold, color: colors.text.primary, letterSpacing: 12 },
  inviteCode: { fontSize: 22, fontWeight: "700" as const, fontFamily: fontFamily.bold, color: colors.text.primary, letterSpacing: 4 },
  badge: { fontSize: 10, fontWeight: "600" as const, fontFamily: fontFamily.semibold },
  subtitle: { fontSize: 15, fontWeight: "400" as const, fontFamily: fontFamily.regular, color: colors.text.secondary, lineHeight: 22 },
} as const;

// ─── Elevation ──────────────────────────────────────────────────────────────
// Cool gray shadows only. The previous warm-amber tinted shadows on the
// dark theme were tied to the brand-glow effect; they look out of place on
// white. Use sparingly — most cards should be flat-on-card-surface.

export const elevation = {
  /** Flat — no shadow. Default for grouped rows. */
  flat: {
    shadowColor: "transparent",
    elevation: 0,
  } as ViewStyle,
  /** Resting cards. */
  low: {
    shadowColor: colors.shadow.default,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.06,
    shadowRadius: 8,
    elevation: 2,
  } as ViewStyle,
  /** Interactive cards, hero cards. */
  mid: {
    shadowColor: colors.shadow.default,
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.10,
    shadowRadius: 16,
    elevation: 4,
  } as ViewStyle,
  /** Modals, sticky CTAs. */
  high: {
    shadowColor: colors.shadow.default,
    shadowOffset: { width: 0, height: 12 },
    shadowOpacity: 0.16,
    shadowRadius: 32,
    elevation: 8,
  } as ViewStyle,
} as const;

// ─── Reusable style objects ────────────────────────────────────────────────
// Spread these instead of writing inline styles. Kept stable so the dozens
// of existing consumers (`{ ...cardStyles }`) don't break.

export const cardStyles: ViewStyle = {
  backgroundColor: colors.surface.card,
  borderRadius: radius.lg,
  padding: spacing.lg,
};

/** White surface + soft shadow. Use for hero cards and lifted content. */
export const elevatedCardStyles: ViewStyle = {
  backgroundColor: colors.surface.elevated,
  borderRadius: radius.lg,
  padding: spacing.lg,
  ...elevation.low,
};

/**
 * Glass cards are deprecated in the light theme — alias to `cardStyles` so
 * existing imports keep resolving while the screen sweep migrates them.
 */
export const glassCardStyles: ViewStyle = cardStyles;

/**
 * Plain list-row spacing. Pair with a hairline divider on the parent
 * container instead of per-row borders.
 */
export const listRowStyles: ViewStyle = {
  paddingVertical: spacing.md,
  paddingHorizontal: spacing.xs,
};

// Pill chip style presets used by `<Pill>`. Active = filled dark (Airbnb's
// selected filter pattern). Inactive = white with subtle border.
export const pillStyles = {
  active: {
    backgroundColor: colors.text.primary,
    borderRadius: radius.pill,
    paddingHorizontal: 14,
    paddingVertical: 8,
  } as ViewStyle,
  inactive: {
    backgroundColor: colors.surface.base,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border.subtle,
    paddingHorizontal: 14,
    paddingVertical: 8,
  } as ViewStyle,
  activeText: {
    fontSize: 13,
    fontWeight: "600" as const,
    fontFamily: fontFamily.semibold,
    color: colors.text.inverse,
  } as TextStyle,
  inactiveText: {
    fontSize: 13,
    fontWeight: "600" as const,
    fontFamily: fontFamily.semibold,
    color: colors.text.primary,
  } as TextStyle,
};

// Inputs default to a quiet gray surface; on focus, components flip to
// white + dark border. Don't override per-screen — extend `<InputField>`
// instead.
export const inputStyles: TextStyle = {
  backgroundColor: colors.surface.input,
  borderRadius: radius.md,
  padding: spacing.md,
  fontSize: 15,
  fontFamily: fontFamily.regular,
  color: colors.text.primary,
  borderWidth: 1,
  borderColor: "transparent",
};

// Button presets. Source of truth for the `<Button>` atom — use the atom,
// not these tokens directly, in screen code.
export const buttonStyles = {
  primary: {
    backgroundColor: colors.accent.primary,
    borderRadius: radius.sm,
    paddingVertical: 14,
    alignItems: "center" as const,
    flexDirection: "row" as const,
    justifyContent: "center" as const,
    gap: 8,
  } as ViewStyle,
  secondary: {
    backgroundColor: colors.surface.base,
    borderRadius: radius.sm,
    paddingVertical: 14,
    alignItems: "center" as const,
    borderWidth: 1,
    borderColor: colors.border.active,
  } as ViewStyle,
  success: {
    backgroundColor: colors.accent.success,
    borderRadius: radius.sm,
    paddingHorizontal: 20,
    paddingVertical: 12,
    flexDirection: "row" as const,
    alignItems: "center" as const,
    gap: 6,
  } as ViewStyle,
  danger: {
    backgroundColor: colors.surface.base,
    borderWidth: 1,
    borderColor: colors.accent.danger,
    borderRadius: radius.sm,
    paddingHorizontal: 18,
    paddingVertical: 12,
  } as ViewStyle,
  disabled: {
    backgroundColor: colors.surface.disabled,
    borderRadius: radius.sm,
    paddingVertical: 14,
    alignItems: "center" as const,
  } as ViewStyle,
  primaryText: {
    fontSize: 15,
    fontWeight: "700" as const,
    fontFamily: fontFamily.bold,
    color: colors.text.inverse,
  } as TextStyle,
  secondaryText: {
    fontSize: 15,
    fontWeight: "600" as const,
    fontFamily: fontFamily.semibold,
    color: colors.text.primary,
  } as TextStyle,
  disabledText: {
    fontSize: 15,
    fontWeight: "700" as const,
    fontFamily: fontFamily.bold,
    color: colors.text.muted,
  } as TextStyle,
};

export const screenContainer: ViewStyle = {
  flex: 1,
  backgroundColor: colors.surface.base,
};

export const screenContentContainer: ViewStyle = {
  padding: spacing.lg,
  paddingBottom: 40,
};

// Glow has no place in the light theme. Kept as a no-op so existing imports
// don't crash; remove during the screen sweep.
export const glowStyles: ViewStyle = {};

export const circleButtonStyles = {
  container: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.surface.base,
    borderWidth: 1,
    borderColor: colors.border.subtle,
    alignItems: "center" as const,
    justifyContent: "center" as const,
  } as ViewStyle,
  label: {
    ...typography.tiny,
    marginTop: spacing.xs,
    textAlign: "center" as const,
  } as TextStyle,
};

/** Apply opacity to a hex color. Use sparingly — prefer the named Dim tokens. */
export function tintedBg(color: string, opacity = 0.1): string {
  const hex = color.replace("#", "");
  const r = parseInt(hex.substring(0, 2), 16);
  const g = parseInt(hex.substring(2, 4), 16);
  const b = parseInt(hex.substring(4, 6), 16);
  return `rgba(${r},${g},${b},${opacity})`;
}

/**
 * Time-of-day ambient palette — formerly drove a warm amber gradient on
 * the dark theme. On light, atmospheric color comes from photography and
 * whitespace, not background tints. Returns transparent so existing
 * consumers render no ambient at all.
 */
export function getTimeOfDayColor(): { primary: string; secondary: string } {
  return { primary: "transparent", secondary: "transparent" };
}

export const springPresets = {
  press: { damping: 15, stiffness: 300, mass: 0.8 },
  modal: { damping: 20, stiffness: 90 },
  enter: { damping: 18, stiffness: 200, mass: 0.8 },
  exitFast: { damping: 22, stiffness: 400, mass: 0.6 },
} as const;

export const staggerDelay = 40;
