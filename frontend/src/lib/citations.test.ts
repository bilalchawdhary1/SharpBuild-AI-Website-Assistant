import { expect, it } from "vitest";
import { splitCitations } from "./citations";

it("splits text and citation markers in order", () => {
  expect(splitCitations("We do X [1][2]. Also Y [3].")).toEqual([
    { type: "text", text: "We do X " }, { type: "cite", index: 1 }, { type: "cite", index: 2 },
    { type: "text", text: ". Also Y " }, { type: "cite", index: 3 }, { type: "text", text: "." },
  ]);
});

it("leaves text without markers alone and ignores non-citation brackets", () => {
  expect(splitCitations("Plain answer.")).toEqual([{ type: "text", text: "Plain answer." }]);
  expect(splitCitations("See [docs] and [a1]")).toEqual([{ type: "text", text: "See [docs] and [a1]" }]);
  expect(splitCitations("")).toEqual([]);
});
