/**
 * `new Date(undefined)` produces "Invalid Date" silently; call any
 * Date.prototype.toLocale*() on it and you crash with `RangeError:
 * Invalid time value` on Hermes (or render literal "Invalid Date" copy
 * on JSC). This module wraps the construction so call sites can branch
 * on `null` instead of guessing.
 *
 * Use everywhere you accept a date string from a route param, a backend
 * response, or AsyncStorage.
 */

export function safeParseDate(input: string | number | Date | undefined | null): Date | null {
  if (input === null || input === undefined || input === "") return null;
  const d = input instanceof Date ? input : new Date(input);
  if (Number.isNaN(d.getTime())) return null;
  return d;
}

/** Format a date with a graceful fallback (default "—"). Never throws. */
export function safeFormatDate(
  input: string | number | Date | undefined | null,
  format: (d: Date) => string,
  fallback: string = "—",
): string {
  const d = safeParseDate(input);
  if (!d) return fallback;
  try {
    return format(d);
  } catch {
    return fallback;
  }
}
