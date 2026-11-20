import {describe, expect, it, vi} from "vitest";
import {ChatApiError} from "./chatApi";
import {submitLead} from "./leadApi";

const ok = () => new Response(JSON.stringify({ok: true}), {status: 200});
const base = {name: "  Ali Khan ", email: " ali@example.com ", consent: true};

async function kindOf(promise: Promise<unknown>) {
  try {
    await promise;
  } catch (e) {
    return e as ChatApiError;
  }
  throw new Error("expected a rejection");
}

describe("submitLead", () => {
  it("posts trimmed JSON to /lead and leaves out empty optional fields", async () => {
    const f = vi.fn().mockResolvedValue(ok());
    await submitLead({...base, phone: "  ", company: "", message: undefined}, undefined, f);
    const [url, init] = f.mock.calls[0];
    expect(String(url)).toMatch(/\/lead$/);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({
      name: "Ali Khan",
      email: "ali@example.com",
      consent: true,
    });
  });

  it("sends optional fields, the honeypot only when filled, and at most 6 history turns of 500 characters", async () => {
    const f = vi.fn().mockResolvedValue(ok());
    const history = Array.from({length: 8}, (_, i) => ({
      role: (i % 2 ? "assistant" : "user") as "user" | "assistant",
      text: "x".repeat(700),
    }));
    await submitLead(
      {...base, phone: "0300-1234567", company: "Acme", message: "An app", history, website: "spam"},
      undefined,
      f,
    );
    const body = JSON.parse(f.mock.calls[0][1].body);
    expect(body).toMatchObject({phone: "0300-1234567", company: "Acme", message: "An app", website: "spam"});
    expect(body.history).toHaveLength(6);
    expect(body.history[0].text).toHaveLength(500);
  });

  it("maps 429, 422, other statuses and network failures to ChatApiError kinds", async () => {
    const respond = (status: number) => vi.fn().mockResolvedValue(new Response("{}", {status}));
    expect((await kindOf(submitLead(base, undefined, respond(429)))).kind).toBe("rate_limited");
    expect((await kindOf(submitLead(base, undefined, respond(422)))).kind).toBe("invalid");
    expect((await kindOf(submitLead(base, undefined, respond(503)))).kind).toBe("unavailable");
    const down = vi.fn().mockRejectedValue(new TypeError("fetch failed"));
    expect((await kindOf(submitLead(base, undefined, down))).kind).toBe("network");
  });

  it("lets an abort through unchanged", async () => {
    const aborted = vi.fn().mockRejectedValue(new DOMException("x", "AbortError"));
    const error = await kindOf(submitLead(base, undefined, aborted));
    expect(error).toBeInstanceOf(DOMException);
  });
});

describe("submitLead handoff fields", () => {
  it("sends kind and share_chat only when they matter", async () => {
    const f = vi.fn().mockResolvedValue(ok());
    await submitLead({...base, kind: "handoff", shareChat: true}, undefined, f);
    expect(JSON.parse(f.mock.calls[0][1].body)).toMatchObject({kind: "handoff", share_chat: true});

    f.mockClear();
    await submitLead({...base, kind: "sales", shareChat: false}, undefined, f);
    const body = JSON.parse(f.mock.calls[0][1].body);
    expect("kind" in body).toBe(false);
    expect("share_chat" in body).toBe(false);
  });
});
