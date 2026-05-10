/**
 * Quick recipes — local seed used by the home-screen "Self cook ideas"
 * sheet when the backend is unreachable, the device is in demo mode,
 * or the network call hasn't completed yet. Mirrors the shape returned
 * by `GET /recipe-archive/quick`.
 *
 * The full set of curated recipes lives in the backend's `recipes`
 * table (seeded by alembic migration 049). The list below is a small
 * subset — fewer entries, but enough that the modal feels populated
 * before the network reply lands. When the backend responds, the FE
 * hook swaps the seed for the live data.
 *
 * Image + YouTube URLs follow the same pattern as the backend seed:
 * the YouTube `hqdefault.jpg` thumbnail CDN host so we don't need to
 * ship our own asset pipeline. If a video ID changes, the broken
 * thumbnail is the canary.
 */

import type { MealType } from "./types";

export interface QuickRecipe {
  id: string;
  slug: string;
  title: string;
  description?: string;
  imageUrl?: string;
  youtubeUrl?: string;
  totalTimeMins: number;
  difficulty: "easy" | "medium" | "hard";
  // Course on the backend maps directly to MealType + "snack". The
  // home modal only filters by breakfast/lunch/dinner, but we keep
  // snack reachable for any future surface that wants it.
  course: MealType;
  dietType: "vegetarian" | "non_vegetarian" | "vegan" | "egg_only";
  tags?: string[];
}

function ytUrl(id: string): string {
  return `https://www.youtube.com/watch?v=${id}`;
}

function ytThumb(id: string): string {
  return `https://img.youtube.com/vi/${id}/hqdefault.jpg`;
}

export const QUICK_RECIPES: QuickRecipe[] = [
  {
    id: "seed-maggi",
    slug: "maggi-masala",
    title: "Maggi Masala",
    description: "The classic 2-minute noodle dish, jazzed up with onions and chillies.",
    totalTimeMins: 7,
    difficulty: "easy",
    course: "lunch",
    dietType: "vegetarian",
    tags: ["quick", "comfort", "kid-friendly"],
    youtubeUrl: ytUrl("KFP7KZqxJA8"),
    imageUrl: ytThumb("KFP7KZqxJA8"),
  },
  {
    id: "seed-bread-omelette",
    slug: "bread-omelette",
    title: "Bread Omelette",
    description: "Two eggs, two slices of bread — a 5-minute brunch saviour.",
    totalTimeMins: 8,
    difficulty: "easy",
    course: "breakfast",
    dietType: "non_vegetarian",
    tags: ["quick", "high-protein"],
    youtubeUrl: ytUrl("7-dJ-ioXfBQ"),
    imageUrl: ytThumb("7-dJ-ioXfBQ"),
  },
  {
    id: "seed-cheese-toast",
    slug: "cheese-toast",
    title: "Cheese Chilli Toast",
    description: "Crisp toast with melty cheese and a hint of chilli.",
    totalTimeMins: 8,
    difficulty: "easy",
    course: "breakfast",
    dietType: "vegetarian",
    tags: ["quick", "tea-time"],
    youtubeUrl: ytUrl("Y9Cj_J5K_oA"),
    imageUrl: ytThumb("Y9Cj_J5K_oA"),
  },
  {
    id: "seed-curd-rice",
    slug: "curd-rice",
    title: "Curd Rice",
    description: "South Indian comfort in a bowl — 10 minutes if rice is leftover.",
    totalTimeMins: 10,
    difficulty: "easy",
    course: "lunch",
    dietType: "vegetarian",
    tags: ["quick", "comfort", "south-indian"],
    youtubeUrl: ytUrl("uzH_jsi2bvs"),
    imageUrl: ytThumb("uzH_jsi2bvs"),
  },
  {
    id: "seed-poha",
    slug: "poha",
    title: "Poha",
    description: "Soft flattened rice tempered with mustard, peanuts, and lemon.",
    totalTimeMins: 15,
    difficulty: "easy",
    course: "breakfast",
    dietType: "vegetarian",
    tags: ["quick", "breakfast", "maharashtrian"],
    youtubeUrl: ytUrl("pNzxeWcbVtU"),
    imageUrl: ytThumb("pNzxeWcbVtU"),
  },
  {
    id: "seed-upma",
    slug: "rava-upma",
    title: "Rava Upma",
    description: "Roasted semolina cooked into a savoury one-pot in 15 minutes.",
    totalTimeMins: 17,
    difficulty: "easy",
    course: "breakfast",
    dietType: "vegetarian",
    tags: ["quick", "south-indian"],
    youtubeUrl: ytUrl("lLoHd6T-SRM"),
    imageUrl: ytThumb("lLoHd6T-SRM"),
  },
  {
    id: "seed-khichdi",
    slug: "khichdi",
    title: "Moong Dal Khichdi",
    description: "One-pot rice and dal porridge, gentle on the stomach.",
    totalTimeMins: 23,
    difficulty: "easy",
    course: "dinner",
    dietType: "vegetarian",
    tags: ["quick", "comfort", "one-pot"],
    youtubeUrl: ytUrl("kt7MVTjbl4A"),
    imageUrl: ytThumb("kt7MVTjbl4A"),
  },
  {
    id: "seed-sandwich",
    slug: "veg-sandwich",
    title: "Veg Mayo Sandwich",
    description: "Cucumber, tomato, onion, and mayo — school-tiffin classic.",
    totalTimeMins: 10,
    difficulty: "easy",
    course: "lunch",
    dietType: "vegetarian",
    tags: ["quick", "kid-friendly"],
    youtubeUrl: ytUrl("RQoWMIz6NX0"),
    imageUrl: ytThumb("RQoWMIz6NX0"),
  },
  {
    id: "seed-besan-chilla",
    slug: "besan-chilla",
    title: "Besan Chilla",
    description: "Savoury gram-flour pancake with onions and chillies.",
    totalTimeMins: 10,
    difficulty: "easy",
    course: "breakfast",
    dietType: "vegetarian",
    tags: ["quick", "high-protein", "gluten-free"],
    youtubeUrl: ytUrl("Zs7Z8h_R-LU"),
    imageUrl: ytThumb("Zs7Z8h_R-LU"),
  },
  {
    id: "seed-dal-tadka",
    slug: "dal-rice-tadka",
    title: "5-Min Dal Tadka with Rice",
    description: "Pre-cooked dal hit with a quick ghee tempering. Honest comfort.",
    totalTimeMins: 11,
    difficulty: "easy",
    course: "dinner",
    dietType: "vegetarian",
    tags: ["quick", "comfort", "leftovers"],
    youtubeUrl: ytUrl("GwxIO8K-FrY"),
    imageUrl: ytThumb("GwxIO8K-FrY"),
  },
];
