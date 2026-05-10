/**
 * Family API client — endpoints related to household onboarding and the
 * ICP-branched product rework (migration 033+).
 *
 * The existing api.ts is a sprawling monolith; keeping rework-specific
 * helpers in their own tiny file makes them easy to delete or re-scope
 * later if the rework framing changes.
 */

import { client } from "./api";

export type FamilyCookAnswer = {
  id: string;
  has_regular_cook: boolean | null;
  onboarding_completed_at: string | null;
};

/**
 * Persist the household's answer to "do you have a regular cook?"
 *
 * Used by (a) the household-setup finish step on new signups and (b) the
 * one-time Home prompt for users who predate the question. The backend
 * stamps `onboarding_completed_at` if it was previously null.
 */
export async function updateCookAnswer(
  familyId: string,
  hasRegularCook: boolean,
): Promise<FamilyCookAnswer> {
  const { data } = await client.patch(`/families/${familyId}/cook-answer`, {
    has_regular_cook: hasRegularCook,
  });
  return data;
}

export type FamilyDetail = {
  id: string;
  name: string;
  family_type: string;
  has_regular_cook: boolean | null;
  onboarding_completed_at: string | null;
  created_at: string;
};

export async function fetchFamilyDetail(familyId: string): Promise<FamilyDetail> {
  const { data } = await client.get(`/families/${familyId}`);
  return data;
}

// ────────────────────────────────────────────────────────────────────
// Cook brief — closes the loop on the WhatsApp intro Bimi sends to
// the cook at the end of onboarding (see lib/cook-brief-tracking.ts).
//
// Endpoint shape (proposed; backend implementation TODO):
//
//   POST /families/{familyId}/cook-briefs
//   Request:  { cook_name, cook_phone, message, sent_at }
//   Response: { id, status: "recorded" }
//
// Until the backend lands, the call 404s and is swallowed by the
// caller's try/catch. The local Zustand store
// (useCookBriefStore) is the source of truth in the meantime, so
// this client-side change ships independently of any backend work.
//
// When the backend is built, two follow-on capabilities become
// available without touching client code:
//   • Server-side scheduling of the 24h push (more reliable than the
//     local notification we schedule today).
//   • Cross-device awareness — if the user re-installs or switches
//     phones, their open briefs survive.
// ────────────────────────────────────────────────────────────────────

export interface CookBriefRecorded {
  id: string;
  status: "recorded";
}

export async function recordCookBrief(
  familyId: string,
  payload: {
    cook_name: string;
    cook_phone: string;
    message: string;
    sent_at: string;
  },
): Promise<CookBriefRecorded | null> {
  try {
    const { data } = await client.post(
      `/families/${familyId}/cook-briefs`,
      payload,
    );
    return data ?? null;
  } catch {
    // Endpoint not yet implemented server-side — caller treats this
    // as informational only.
    return null;
  }
}
