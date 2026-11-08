import { expect, it } from "vitest";
import { stripCitations } from "./citations";

it("removes markers together with the space before them", () => {
  expect(stripCitations("We do X [1][2]. Also Y [3].")).toBe("We do X. Also Y.");
});

it("removes comma-separated and comma-joined markers", () => {
  expect(stripCitations("Goals [1], [2]. More [3, 4] here")).toBe("Goals. More here");
});

it("leaves ordinary brackets and text without markers alone", () => {
  expect(stripCitations("Plain answer.")).toBe("Plain answer.");
  expect(stripCitations("See [docs] and [a1] and [12345]")).toBe("See [docs] and [a1] and [12345]");
  expect(stripCitations("")).toBe("");
});
