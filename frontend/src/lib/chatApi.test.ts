import { describe, expect, it, vi } from "vitest";
import { askQuestion, ChatApiError, isSafeUrl } from "./chatApi";

const json = (body: unknown, init: ResponseInit = {}) =>
  new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" }, ...init });

const OK = { answer: "Yes. [1]", sources: [{ url: "https://sharpbuild.io/a", title: "A", section: "S" }], fallback: false };

async function kindOf(promise: Promise<unknown>) {
  try { await promise; } catch (e) { return e as ChatApiError; }
  throw new Error("expected a rejection");
}

describe("askQuestion", () => {
  it("posts the message as JSON to /chat and returns the reply", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json(OK));
    const reply = await askQuestion("Hello?", undefined, fetchMock);
    expect(reply).toEqual(OK);
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/chat$/);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ message: "Hello?" });
  });

  it("maps 429 to rate_limited and reads Retry-After", async () => {
    const f = vi.fn().mockResolvedValue(json({ detail: "x" }, { status: 429, headers: { "Retry-After": "42" } }));
    const err = await kindOf(askQuestion("q", undefined, f));
    expect(err.kind).toBe("rate_limited");
    expect(err.retryAfterSeconds).toBe(42);
  });

  it.each([[422, "invalid"], [500, "unavailable"], [503, "unavailable"]] as const)("maps HTTP %i to %s", async (status, kind) => {
    const err = await kindOf(askQuestion("q", undefined, vi.fn().mockResolvedValue(json({}, { status }))));
    expect(err.kind).toBe(kind);
  });

  it("maps a network failure to network", async () => {
    const err = await kindOf(askQuestion("q", undefined, vi.fn().mockRejectedValue(new TypeError("Failed to fetch"))));
    expect(err.kind).toBe("network");
  });

  it("lets an abort through unchanged so the UI can ignore it", async () => {
    const abort = new DOMException("aborted", "AbortError");
    await expect(askQuestion("q", undefined, vi.fn().mockRejectedValue(abort))).rejects.toBe(abort);
  });

  it("rejects responses with the wrong shape or unreadable bodies", async () => {
    for (const body of [{ nope: 1 }, { answer: 1, sources: [] }, { answer: "x", sources: "no" }, { answer: "x", sources: [{ url: 5, title: "t" }] }]) {
      expect((await kindOf(askQuestion("q", undefined, vi.fn().mockResolvedValue(json(body))))).kind).toBe("unavailable");
    }
    const garbled = vi.fn().mockResolvedValue(new Response("<html>", { status: 200 }));
    expect((await kindOf(askQuestion("q", undefined, garbled))).kind).toBe("unavailable");
  });

  it("drops sources whose URL is not a plain web link", async () => {
    const body = { answer: "x", fallback: false, sources: [
      { url: "javascript:alert(1)", title: "bad", section: "" },
      { url: "https://sharpbuild.io/ok", title: "ok", section: "" },
    ] };
    const reply = await askQuestion("q", undefined, vi.fn().mockResolvedValue(json(body)));
    expect(reply.sources.map((s) => s.title)).toEqual(["ok"]);
  });
});

describe("isSafeUrl", () => {
  it("allows only http(s)", () => {
    expect(isSafeUrl("https://sharpbuild.io/x")).toBe(true);
    expect(isSafeUrl("javascript:alert(1)")).toBe(false);
    expect(isSafeUrl("data:text/html,hi")).toBe(false);
    expect(isSafeUrl("not a url")).toBe(false);
  });
});
