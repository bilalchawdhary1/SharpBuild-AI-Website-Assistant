import {describe, expect, it} from "vitest";
import nextConfig, {securityHeaders} from "../../next.config";

const value = (key: string) => securityHeaders.find(h => h.key === key)?.value ?? "";

describe("security headers", () => {
  it("are applied to every route", async () => {
    const rules = await nextConfig.headers!();
    expect(rules).toHaveLength(1);
    expect(rules[0].source).toBe("/:path*");
    expect(rules[0].headers).toBe(securityHeaders);
  });

  it("block framing, sniffing, plugins and rogue <base>/form targets", () => {
    expect(value("X-Frame-Options")).toBe("DENY");
    expect(value("X-Content-Type-Options")).toBe("nosniff");
    const csp = value("Content-Security-Policy");
    for (const rule of ["frame-ancestors 'none'", "base-uri 'self'", "object-src 'none'", "form-action 'self'"])
      expect(csp).toContain(rule);
  });

  it("do not restrict scripts, which would break Next.js inline bootstrap code", () => {
    expect(value("Content-Security-Policy")).not.toMatch(/script-src|default-src/);
  });

  it("turn off device features the site never uses", () => {
    expect(value("Permissions-Policy")).toMatch(/camera=\(\).*microphone=\(\)/);
  });

  it("keep the existing Next options", () => {
    expect(nextConfig.cacheComponents).toBe(true);
    expect(nextConfig.partialPrefetching).toBe(true);
  });
});
