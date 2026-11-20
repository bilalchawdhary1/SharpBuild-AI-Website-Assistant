import {describe, expect, it, vi} from "vitest";
import {askQuestion} from "./chatApi";

const reply = (extra: Record<string, unknown>) =>
  vi.fn().mockResolvedValue(
    new Response(JSON.stringify({answer: "Hi", sources: [], fallback: false, ...extra}), {status: 200}),
  );

describe("lead hint in replies", () => {
  it("keeps a valid lead block in camelCase", async () => {
    const r = await askQuestion("q", undefined, reply({lead: {score: "warm", next_field: "contact", need: true}}));
    expect(r.lead).toEqual({score: "warm", nextField: "contact"});
  });

  it("has no `lead` key when the backend sends none or something invalid", async () => {
    for (const extra of [{}, {lead: null}, {lead: {score: "great"}}, {lead: "x"}]) {
      const r = await askQuestion("q", undefined, reply(extra));
      expect("lead" in r).toBe(false);
    }
  });

  it("treats a missing next_field as null", async () => {
    const r = await askQuestion("q", undefined, reply({lead: {score: "hot"}}));
    expect(r.lead).toEqual({score: "hot", nextField: null});
  });
});

describe("handoff flag in replies", () => {
  it("sets handoff only when the backend routed the message as a request for a person", async () => {
    const r = await askQuestion("q", undefined, reply({intent: "human_handoff", fallback: true}));
    expect(r.handoff).toBe(true);
    for (const intent of ["information", "pricing", 5, null]) {
      const other = await askQuestion("q", undefined, reply({intent}));
      expect("handoff" in other).toBe(false);
    }
  });

  it("keeps lead and handoff together", async () => {
    const r = await askQuestion(
      "q",
      undefined,
      reply({intent: "human_handoff", lead: {score: "warm", next_field: "contact"}}),
    );
    expect(r).toMatchObject({handoff: true, lead: {score: "warm", nextField: "contact"}});
  });
});
