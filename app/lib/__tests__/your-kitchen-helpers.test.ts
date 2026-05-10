/**
 * Pure-function tests for Your Kitchen client helpers (PRD §4.13).
 *
 * Run with: cd bimi/app && npm test
 *
 * Component/screen tests live as Maestro flows under
 * .maestro/flows/dish_first/your_kitchen_happy_path.yaml because spinning up
 * react-native-testing-library would be disproportionate for this scope.
 */

import { describe, expect, it } from "vitest";

import {
  initialsFor,
  relativeServedLabel,
  sortReactionsForDisplay,
  type MemberReaction,
  type Sentiment,
} from "../your-kitchen-helpers";

const r = (sentiment: Sentiment, name = "X", id = name): MemberReaction => ({
  person_id: id,
  name,
  sentiment,
  confidence: 0.5,
});

describe("relativeServedLabel", () => {
  it("returns null for null/undefined input", () => {
    expect(relativeServedLabel(null)).toBeNull();
    expect(relativeServedLabel(undefined as unknown as null)).toBeNull();
  });

  it("renders 0 days as 'today'", () => {
    expect(relativeServedLabel(0)).toBe("today");
    // Negative days (clock skew) collapse to today, not 'in -2 days'.
    expect(relativeServedLabel(-2)).toBe("today");
  });

  it("renders 1 day as 'yesterday'", () => {
    expect(relativeServedLabel(1)).toBe("yesterday");
  });

  it("renders <7 days as 'N days ago'", () => {
    expect(relativeServedLabel(3)).toBe("3 days ago");
    expect(relativeServedLabel(6)).toBe("6 days ago");
  });

  it("renders 7-13 as 'last week'", () => {
    expect(relativeServedLabel(7)).toBe("last week");
    expect(relativeServedLabel(13)).toBe("last week");
  });

  it("renders 14-29 as 'N weeks ago'", () => {
    expect(relativeServedLabel(14)).toBe("2 weeks ago");
    expect(relativeServedLabel(20)).toBe("3 weeks ago");
  });

  it("renders 30-364 as 'N months ago'", () => {
    expect(relativeServedLabel(30)).toBe("1 months ago");
    expect(relativeServedLabel(180)).toBe("6 months ago");
  });

  it("renders >=365 as 'over a year ago'", () => {
    expect(relativeServedLabel(365)).toBe("over a year ago");
    expect(relativeServedLabel(800)).toBe("over a year ago");
  });
});

describe("initialsFor", () => {
  it("returns ? for empty string", () => {
    expect(initialsFor("")).toBe("?");
    expect(initialsFor("   ")).toBe("?");
  });

  it("uses first 2 characters for single names", () => {
    expect(initialsFor("Anjan")).toBe("AN");
    expect(initialsFor("malti")).toBe("MA");
  });

  it("uses first+last initials for multi-word names", () => {
    expect(initialsFor("Anjan Das")).toBe("AD");
    expect(initialsFor("Malti Didi Sharma")).toBe("MS");
  });

  it("collapses multiple whitespace cleanly", () => {
    expect(initialsFor("Anjan   Das")).toBe("AD");
  });

  it("uppercases lowercase input", () => {
    expect(initialsFor("anjan das")).toBe("AD");
  });
});

describe("sortReactionsForDisplay", () => {
  it("orders love → like → untried → dislike", () => {
    const input = [
      r("dislike", "D"),
      r("untried", "U"),
      r("like", "L"),
      r("love", "V"),
    ];
    const out = sortReactionsForDisplay(input);
    expect(out.map((x) => x.name)).toEqual(["V", "L", "U", "D"]);
  });

  it("preserves relative order within the same sentiment (stable sort)", () => {
    const input = [
      r("love", "Anjan"),
      r("love", "Mom"),
      r("love", "Sister"),
    ];
    const out = sortReactionsForDisplay(input);
    expect(out.map((x) => x.name)).toEqual(["Anjan", "Mom", "Sister"]);
  });

  it("does not mutate input", () => {
    const input = [r("dislike", "X"), r("love", "Y")];
    const before = [...input];
    sortReactionsForDisplay(input);
    expect(input).toEqual(before);
  });

  it("returns empty for empty input", () => {
    expect(sortReactionsForDisplay([])).toEqual([]);
  });
});
