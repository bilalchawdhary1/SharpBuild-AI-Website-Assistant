import {readFileSync} from "node:fs";
import {resolve} from "node:path";
import {describe, expect, it} from "vitest";

// Guards the widget's colours: normal-size text needs a 4.5:1 contrast ratio (WCAG AA).
// Vitest runs from the project root; a plain path avoids `new URL(import.meta.url)`, which fails in jsdom.
const css = readFileSync(resolve(process.cwd(), "src/components/ChatWidget.module.css"), "utf8");
const color = (name: string): string => {
  const match = css.match(new RegExp(`${name}:\\s*(#[0-9a-fA-F]{6})`));
  if (!match) throw new Error(`${name} not found in ChatWidget.module.css`);
  return match[1];
};

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map(i => parseInt(hex.slice(i, i + 2), 16) / 255).map(c =>
    c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4,
  );
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
const ratio = (a: string, b: string) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};

describe("widget colour contrast", () => {
  const surfaces = ["--bg", "--bot-bg", "--notice-bg"];

  it.each(surfaces)("body text, muted text and accent links are readable on %s", surface => {
    expect(ratio(color("--fg"), color(surface))).toBeGreaterThanOrEqual(4.5);
    expect(ratio(color("--muted"), color(surface))).toBeGreaterThanOrEqual(4.5);
    expect(ratio(color("--accent-text"), color(surface))).toBeGreaterThanOrEqual(4.5);
  });

  it("white text on the accent colour and on the dark bubbles is readable", () => {
    expect(ratio(color("--accent-fg"), color("--accent"))).toBeGreaterThanOrEqual(4.5);
    expect(ratio(color("--accent-fg"), color("--user-bg"))).toBeGreaterThanOrEqual(4.5);
  });

  it("small accent-coloured text uses the darker --accent-text, not the raw accent", () => {
    expect(css).not.toMatch(/\n\s+color:\s*var\(--accent\);/);
  });
});
