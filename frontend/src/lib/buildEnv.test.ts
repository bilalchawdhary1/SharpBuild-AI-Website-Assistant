import {describe, expect, it} from "vitest";
import {assertBuildEnv} from "../../next.config";

const production = (url?: string) => ({VERCEL_ENV: "production", NEXT_PUBLIC_API_URL: url});

describe("assertBuildEnv", () => {
  it("lets local builds and previews through whatever the URL is", () => {
    expect(() => assertBuildEnv({})).not.toThrow();
    expect(() => assertBuildEnv({VERCEL_ENV: "preview"})).not.toThrow();
    expect(() => assertBuildEnv({VERCEL_ENV: "development", NEXT_PUBLIC_API_URL: "http://127.0.0.1:8000"})).not.toThrow();
  });

  it("accepts a deployed https backend", () => {
    expect(() => assertBuildEnv(production("https://api.sharpbuild.io"))).not.toThrow();
    expect(() => assertBuildEnv(production("https://api.sharpbuild.io/"))).not.toThrow();
  });

  it("fails a Production build with no API URL", () => {
    expect(() => assertBuildEnv(production(undefined))).toThrow(/NEXT_PUBLIC_API_URL is not set/);
    expect(() => assertBuildEnv(production(""))).toThrow(/not set/);
  });

  it("fails a Production build that would call an insecure or local backend", () => {
    expect(() => assertBuildEnv(production("http://api.sharpbuild.io"))).toThrow(/https/);
    expect(() => assertBuildEnv(production("https://localhost:8000"))).toThrow(/deployed backend/);
    expect(() => assertBuildEnv(production("https://127.0.0.1"))).toThrow(/deployed backend/);
  });
});
