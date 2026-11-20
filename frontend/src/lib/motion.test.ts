import {afterEach, describe, expect, it, vi} from "vitest";
import {isNearBottom, prefersReducedMotion} from "./motion";

afterEach(() => vi.unstubAllGlobals());

describe("prefersReducedMotion", () => {
  it("is true only when the system asks for reduced motion", () => {
    vi.stubGlobal("matchMedia", (query: string) => ({matches: query.includes("reduce")}));
    expect(prefersReducedMotion()).toBe(true);
    vi.stubGlobal("matchMedia", () => ({matches: false}));
    expect(prefersReducedMotion()).toBe(false);
  });

  it("is false where matchMedia does not exist", () => {
    vi.stubGlobal("matchMedia", undefined);
    expect(prefersReducedMotion()).toBe(false);
  });
});

describe("isNearBottom", () => {
  const el = (scrollTop: number) => ({scrollHeight: 1000, clientHeight: 300, scrollTop});
  it("keeps following while the visitor is at, or close to, the latest message", () => {
    expect(isNearBottom(el(700))).toBe(true);
    expect(isNearBottom(el(640))).toBe(true);
  });
  it("lets go once they scroll up to read", () => {
    expect(isNearBottom(el(500))).toBe(false);
    expect(isNearBottom(el(0))).toBe(false);
  });
});
