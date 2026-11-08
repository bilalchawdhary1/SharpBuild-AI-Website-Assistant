import {expect, it} from "vitest";
import {parseAnswer, parseInline} from "./format";

it("splits paragraphs on blank lines and joins soft line breaks", () => {
  expect(parseAnswer("First line\nsame paragraph\n\nSecond paragraph")).toEqual(
    [
      {type: "p", text: "First line same paragraph"},
      {type: "p", text: "Second paragraph"},
    ],
  );
});

it("turns numbered and bullet lines into lists and keeps the start number", () => {
  expect(
    parseAnswer(
      "Steps:\n1. Discover [1]\n2. Build [2]\nThen:\n\u2022 one\n- two\n3. Ship",
    ),
  ).toEqual([
    {type: "p", text: "Steps:"},
    {type: "ol", items: ["Discover [1]", "Build [2]"], start: 1},
    {type: "p", text: "Then:"},
    {type: "ul", items: ["one", "two"]},
    {type: "ol", items: ["Ship"], start: 3},
  ]);
});

it("does not mistake years, decimals or hyphenated words for lists", () => {
  expect(parseAnswer("2024 was busy\n3.5 stars\nwell-known firm")).toEqual([
    {type: "p", text: "2024 was busy 3.5 stars well-known firm"},
  ]);
});

it("handles empty text and Windows line endings", () => {
  expect(parseAnswer("")).toEqual([]);
  expect(parseAnswer("a\r\n\r\nb")).toEqual([
    {type: "p", text: "a"},
    {type: "p", text: "b"},
  ]);
});

it("drops heading markers", () => {
  expect(parseAnswer("## Our process\nWe start early.")).toEqual([
    {type: "p", text: "Our process We start early."},
  ]);
});

it("splits bold text and hides unmatched asterisks (text still streaming in)", () => {
  expect(parseInline("a **b** c")).toEqual([
    {text: "a ", bold: false},
    {text: "b", bold: true},
    {text: " c", bold: false},
  ]);
  expect(parseInline("Discover: **learn")).toEqual([
    {text: "Discover: ", bold: false},
    {text: "learn", bold: false},
  ]);
  expect(
    parseInline("**One** and **Two**")
      .filter(s => s.bold)
      .map(s => s.text),
  ).toEqual(["One", "Two"]);
  expect(parseInline("no markup")).toEqual([{text: "no markup", bold: false}]);
});
