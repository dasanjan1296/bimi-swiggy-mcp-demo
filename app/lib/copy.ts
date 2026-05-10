// H7: error + status message catalogue.
//
// All API error / network / generic UI strings flow through this catalogue
// so the elder persona (Devi, 64) gets readable Hinglish copy instead of
// "Failed to fetch". Larger font is applied via theme.ts for these surfaces.
//
// Conventions:
//   - Hinglish for action prompts + errors.
//   - English for technical artefacts (cart IDs, version numbers).
//   - One short, plain sentence per entry.

export const ERR = {
  // ---- Network / generic ----
  network_offline: "Internet thoda dheela hai. 30 second mein dobara try karenge.",
  network_timeout: "Server jawab nahi de raha. Thodi der mein dobara koshish karein.",
  unknown: "Kuch galat ho gaya. Aap dobara koshish karein, ya pilot lead ko bata dijiye.",

  // ---- Auth ----
  auth_otp_invalid: "OTP galat hai. Kripaya sahi 6-digit code daliye.",
  auth_otp_expired: "OTP expire ho gaya. Naya OTP request karein.",
  auth_phone_invalid: "Phone number sahi nahi lag raha. 10-digit Indian number dijiye.",
  auth_session_expired: "Aap log out ho gaye hain. Phir se login karein.",

  // ---- Family / household ----
  family_not_found: "Yeh family system mein nahi mili. Pilot lead se confirm karein.",
  invite_code_invalid: "Invite code galat hai. Family lead se naya code mangwa lijiye.",

  // ---- Voting / meal ----
  vote_already_locked: "Voting band ho gayi hai is meal ke liye. Cook ko already plan bhej diya hai.",
  vote_no_options: "Aaj koi options nahi mile. Bimi ko dobara try karne dijiye.",
  meal_paused: "Bimi suggestions paused hain. Pilot lead se baat karein.",

  // ---- Cook ----
  cook_message_failed: "Cook ko message nahi gaya. Network check karein.",
  cook_not_set: "Cook ka profile nahi hai. Settings mein add karein.",

  // ---- Cart / approval ----
  cart_already_approved: "Yeh cart already approved hai.",
  cart_already_rejected: "Yeh cart already reject ho chuka hai.",
  cart_amount_too_high: "Cart amount aapke auto-approval limit se zyada hai.",

  // ---- Expenses ----
  expense_settle_failed: "Settlement nahi ho saka. Phir try karein.",

  // ---- Health ----
  health_value_invalid: "Reading sahi nahi lag rahi. Number dobara check karein.",

  // ---- Permission ----
  permission_denied: "Yeh option aapke role ke liye uplabdh nahi hai.",
  founder_only: "Sirf pilot lead access kar sakte hain.",
} as const;

export type ErrKey = keyof typeof ERR;

/** Map a fetch / API failure to a user-facing copy string. */
export function errorCopyFor(err: unknown): string {
  if (err == null) return ERR.unknown;
  const msg = (err instanceof Error ? err.message : String(err)).toLowerCase();
  if (msg.includes("network") || msg.includes("fetch")) return ERR.network_offline;
  if (msg.includes("timeout")) return ERR.network_timeout;
  if (msg.includes("401") || msg.includes("unauthor")) return ERR.auth_session_expired;
  if (msg.includes("403")) return ERR.permission_denied;
  if (msg.includes("404")) return ERR.family_not_found;
  if (msg.includes("422")) return ERR.unknown;
  return ERR.unknown;
}

// ---- Status / success messages (used in toasts) ----
export const OK = {
  vote_recorded: "Vote save ho gaya.",
  cart_approved: "Cart approved -- order ja raha hai.",
  cart_rejected: "Cart reject ho gaya.",
  cook_message_sent: "Cook ko bhej diya.",
  recap_received: "Thanks! Aapka feedback Bimi ne save kar liya.",
  meal_logged: "Meal logged. Kal ke planning mein use ho jayega.",
  health_logged: "Reading save ho gayi.",
  settings_saved: "Settings save.",
} as const;

export type OkKey = keyof typeof OK;

// ---- Inline UI captions (used by hero / vote / plan-a-day cards) ----
//
// Centralising these so we can switch them to other Indian languages later
// without grepping through every screen. Naming convention: <surface>_<role>.
export const UI = {
  cost_caption: "incl. cook + ingredients (est.)",
  toggle_bimi_handles: "Bimi handles",
  toggle_user_handles: "I'll handle",
  cook_arrives_in: "ready in",
  for_n_portions: (n: number) => `For ~${Math.max(1, Math.round(n))} portions`,
  prep_time_min: (min: number) => `~${Math.max(5, Math.round(min))} min cook time`,
} as const;
