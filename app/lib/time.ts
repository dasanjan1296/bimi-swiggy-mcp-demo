// H5: timezone display sweep.
//
// Single helper used by every screen to render dates + times. Always shows
// IST in the UI (the pilot is India-only); DB stores UTC, mobile stores
// whatever the OS provides (which on a Bangalore phone is also IST, but
// we don't rely on the device timezone).
//
// Replaces ad-hoc `new Date(x).toLocaleString()` calls scattered across
// screens, which were drifting between UTC and the device clock.

const IST_TZ = "Asia/Kolkata";

function _toDate(input: Date | string | number | null | undefined): Date | null {
  if (input == null) return null;
  if (input instanceof Date) return input;
  if (typeof input === "number") return new Date(input);
  if (typeof input === "string") {
    // Treat naive strings as UTC (matches our API convention).
    if (/Z|[+-]\d{2}:?\d{2}$/.test(input)) return new Date(input);
    return new Date(input + "Z");
  }
  return null;
}

export function formatIST(
  input: Date | string | number | null | undefined,
  opts: Intl.DateTimeFormatOptions = {
    year: "numeric", month: "short", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hour12: true,
  },
): string {
  const d = _toDate(input);
  if (d == null) return "—";
  try {
    return d.toLocaleString("en-IN", { timeZone: IST_TZ, ...opts });
  } catch {
    return d.toString();
  }
}

export function formatTimeIST(input: Date | string | number | null | undefined): string {
  return formatIST(input, { hour: "2-digit", minute: "2-digit", hour12: true });
}

export function formatDateIST(input: Date | string | number | null | undefined): string {
  return formatIST(input, { weekday: "short", month: "short", day: "2-digit" });
}

export function formatRelativeIST(input: Date | string | number | null | undefined): string {
  const d = _toDate(input);
  if (d == null) return "—";
  const diffMs = Date.now() - d.getTime();
  const min = Math.round(diffMs / 60000);
  if (min < 1) return "just now";
  if (min < 60) return `${min} min ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr} h ago`;
  const day = Math.round(hr / 24);
  if (day < 30) return `${day}d ago`;
  return formatDateIST(d);
}

/** Returns "07:30 IST" given the backend's raw "07:30" slot string. */
export function formatSlot(slotString: string | undefined | null): string {
  if (!slotString) return "—";
  return `${slotString.trim()} IST`;
}

/** Compact "Mon 7:30 PM" used by meal-calendar / recap. */
export function formatDayTime(input: Date | string | number | null | undefined): string {
  return formatIST(input, {
    weekday: "short", hour: "2-digit", minute: "2-digit", hour12: true,
  });
}
