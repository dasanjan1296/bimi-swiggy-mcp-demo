/**
 * Safe URL opening — validates schemes and (for http/https) hosts before
 * handing the URL to the OS. The audit flagged that several call sites
 * pass server-supplied URLs to `Linking.openURL` without scheme/host
 * validation, which is an open-redirect-style risk if the API is ever
 * compromised or a notification payload is tampered.
 *
 * Use:
 *   await openExternalUrl(serverUrl);            // strict, https-only
 *   await openExternalUrl(deepLinkUrl, {         // explicit scheme list
 *     allowedSchemes: ["whatsapp", "https"],
 *   });
 *   openInternalDeepLink(myAppDeepLink);          // bimi:// allowlist
 *
 * Always returns a boolean — true on success, false on a rejection or
 * runtime error. Never throws.
 */

import { Linking } from "react-native";

export interface OpenUrlOptions {
  /** Schemes (without trailing colon) accepted on this call. Default: ["https"]. */
  allowedSchemes?: string[];
  /** Optional hostname allowlist — only consulted when scheme is http/https.
   *  Hosts match exactly; subdomains require explicit entries. */
  allowedHosts?: string[];
}

const SCHEME_RE = /^([a-zA-Z][a-zA-Z0-9+\-.]*):/;

/**
 * Opens an external URL after validating it. Returns true if the OS was
 * asked to open it (success or not), false if validation rejected it.
 */
export async function openExternalUrl(
  url: string | null | undefined,
  opts: OpenUrlOptions = {},
): Promise<boolean> {
  const cleaned = (url ?? "").trim();
  if (!cleaned) return false;
  const allowedSchemes = opts.allowedSchemes ?? ["https"];

  const m = SCHEME_RE.exec(cleaned);
  if (!m) return false;
  const scheme = m[1]!.toLowerCase();
  if (!allowedSchemes.includes(scheme)) return false;

  // Block known-dangerous schemes regardless of allowlist.
  if (
    scheme === "javascript" ||
    scheme === "data" ||
    scheme === "file" ||
    scheme === "vbscript"
  ) {
    return false;
  }

  // For http/https, optionally validate the host.
  if ((scheme === "https" || scheme === "http") && opts.allowedHosts) {
    try {
      const u = new URL(cleaned);
      if (!opts.allowedHosts.includes(u.hostname)) return false;
    } catch {
      return false;
    }
  }

  try {
    await Linking.openURL(cleaned);
    return true;
  } catch {
    return false;
  }
}

/**
 * Specifically for our own deep-link scheme. Rejects any URL that isn't
 * `bimi://...`. Useful for handling server-supplied push payloads.
 */
export async function openInternalDeepLink(
  url: string | null | undefined,
): Promise<boolean> {
  return openExternalUrl(url, { allowedSchemes: ["bimi"] });
}

/**
 * UPI helper — only opens `upi://` URIs (used for settlement payments).
 */
export async function openUpiUrl(
  url: string | null | undefined,
): Promise<boolean> {
  return openExternalUrl(url, { allowedSchemes: ["upi"] });
}

/**
 * WhatsApp helper — opens `whatsapp://` URIs and falls back to
 * https://wa.me.
 */
export async function openWhatsAppUrl(
  url: string | null | undefined,
): Promise<boolean> {
  return openExternalUrl(url, {
    allowedSchemes: ["whatsapp", "https"],
    allowedHosts: ["wa.me"],
  });
}
