import {expect, it} from "vitest";
import {commonPrefixLength, nextShown} from "./typewriter";

it("reveals a little at a time when little is waiting, and never overshoots", () => {
  expect(nextShown(0, 5)).toBe(2);
  expect(nextShown(4, 5)).toBe(5);
  expect(nextShown(5, 5)).toBe(5);
  expect(nextShown(9, 3)).toBe(3);
});

it("speeds up for large backlogs but caps the step so the reveal still looks typed", () => {
  expect(nextShown(0, 100)).toBe(6);
  expect(nextShown(0, 5000)).toBe(12);
});

it("finishes any answer in a bounded number of steps", () => {
  let shown = 0,
    steps = 0;
  while (shown < 600) {
    shown = nextShown(shown, 600);
    steps++;
  }
  expect(steps).toBeLessThan(120); // 600 characters at 28 ms per step is under about 3.4 s
});

it("finds how much of two strings match", () => {
  expect(commonPrefixLength("Hello world", "Hello there")).toBe(6);
  expect(commonPrefixLength("abc", "abc")).toBe(3);
  expect(commonPrefixLength("", "abc")).toBe(0);
  expect(commonPrefixLength("xyz", "abc")).toBe(0);
});
