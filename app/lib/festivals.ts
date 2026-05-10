import { localIsoDate } from "./local-day";

interface Festival {
  name: string;
  date: string;
  endDate?: string;
  dietaryOverride?: "pure_veg" | "sattvic" | "no_onion_garlic" | "fasting";
  description: string;
  region?: string;
}

const INDIAN_FESTIVALS_2026: Festival[] = [
  { name: "Makar Sankranti", date: "2026-01-14", description: "Til-gur sweets, khichdi", dietaryOverride: "pure_veg" },
  { name: "Republic Day", date: "2026-01-26", description: "Special meals" },
  { name: "Maha Shivaratri", date: "2026-02-15", description: "Fasting day", dietaryOverride: "fasting" },
  { name: "Holi", date: "2026-03-14", description: "Gujiya, thandai, festive cooking" },
  { name: "Ugadi / Gudi Padwa", date: "2026-03-29", description: "New Year special meals", region: "South/West" },
  { name: "Ram Navami", date: "2026-04-06", description: "Fasting and prasad", dietaryOverride: "sattvic" },
  { name: "Eid ul-Fitr", date: "2026-04-21", description: "Biryani, seviyan, kebabs" },
  { name: "Buddha Purnima", date: "2026-05-12", description: "Sattvic meals", dietaryOverride: "pure_veg" },
  { name: "Rath Yatra", date: "2026-06-29", description: "Prasad and festive cooking" },
  { name: "Independence Day", date: "2026-08-15", description: "Special meals" },
  { name: "Janmashtami", date: "2026-08-24", description: "Fasting and festive sweets", dietaryOverride: "fasting" },
  { name: "Ganesh Chaturthi", date: "2026-09-07", description: "Modak, prasad", dietaryOverride: "pure_veg" },
  { name: "Navratri Start", date: "2026-09-22", endDate: "2026-09-30", description: "9 days of fasting/sattvic meals", dietaryOverride: "sattvic" },
  { name: "Dussehra", date: "2026-10-01", description: "Festive feast" },
  { name: "Karwa Chauth", date: "2026-10-15", description: "Fasting and sargi", dietaryOverride: "fasting" },
  { name: "Diwali", date: "2026-10-20", description: "Sweets, snacks, festive cooking" },
  { name: "Bhai Dooj", date: "2026-10-22", description: "Special meals for siblings" },
  { name: "Chhath Puja", date: "2026-10-25", description: "Thekua, prasad", region: "Bihar/UP" },
  { name: "Guru Nanak Jayanti", date: "2026-11-04", description: "Langar and community meals" },
  { name: "Christmas", date: "2026-12-25", description: "Cake, plum pudding, festive dinner" },
];

export function getUpcomingFestivals(daysAhead: number = 14): Festival[] {
  const now = new Date();
  const cutoff = new Date(now.getTime() + daysAhead * 86400000);
  const todayStr = localIsoDate(now);
  const cutoffStr = localIsoDate(cutoff);
  return INDIAN_FESTIVALS_2026.filter((f) => {
    const endDate = f.endDate || f.date;
    return endDate >= todayStr && f.date <= cutoffStr;
  });
}

export function getActiveFestival(): Festival | null {
  const todayStr = localIsoDate();
  return INDIAN_FESTIVALS_2026.find((f) => {
    const endDate = f.endDate || f.date;
    return f.date <= todayStr && endDate >= todayStr;
  }) || null;
}

export type { Festival };
