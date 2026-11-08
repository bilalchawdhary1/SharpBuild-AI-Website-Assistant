import {describe, expect, it, vi} from "vitest";
import {
  askQuestion,
  askQuestionStream,
  ChatApiError,
  isSafeUrl,
} from "./chatApi";

const json = (body: unknown, init: ResponseInit = {}) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: {"Content-Type": "application/json"},
    ...init,
  });

const OK = {
  answer: "Yes. [1]",
  sources: [{url: "https://sharpbuild.io/a", title: "A", section: "S"}],
  fallback: false,
};

async function kindOf(promise: Promise<unknown>) {
  try {
    await promise;
  } catch (e) {
    return e as ChatApiError;
  }
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
    expect(JSON.parse(init.body)).toEqual({message: "Hello?"});
  });

  it("maps 429 to rate_limited and reads Retry-After", async () => {
    const f = vi
      .fn()
      .mockResolvedValue(
        json({detail: "x"}, {status: 429, headers: {"Retry-After": "42"}}),
      );
    const err = await kindOf(askQuestion("q", undefined, f));
    expect(err.kind).toBe("rate_limited");
    expect(err.retryAfterSeconds).toBe(42);
  });

  it.each([
    [422, "invalid"],
    [500, "unavailable"],
    [503, "unavailable"],
  ] as const)("maps HTTP %i to %s", async (status, kind) => {
    const err = await kindOf(
      askQuestion(
        "q",
        undefined,
        vi.fn().mockResolvedValue(json({}, {status})),
      ),
    );
    expect(err.kind).toBe(kind);
  });

  it("maps a network failure to network", async () => {
    const err = await kindOf(
      askQuestion(
        "q",
        undefined,
        vi.fn().mockRejectedValue(new TypeError("Failed to fetch")),
      ),
    );
    expect(err.kind).toBe("network");
  });

  it("lets an abort through unchanged so the UI can ignore it", async () => {
    const abort = new DOMException("aborted", "AbortError");
    await expect(
      askQuestion("q", undefined, vi.fn().mockRejectedValue(abort)),
    ).rejects.toBe(abort);
  });

  it("rejects responses with the wrong shape or unreadable bodies", async () => {
    for (const body of [
      {nope: 1},
      {answer: 1, sources: []},
      {answer: "x", sources: "no"},
      {answer: "x", sources: [{url: 5, title: "t"}]},
    ]) {
      expect(
        (
          await kindOf(
            askQuestion("q", undefined, vi.fn().mockResolvedValue(json(body))),
          )
        ).kind,
      ).toBe("unavailable");
    }
    const garbled = vi
      .fn()
      .mockResolvedValue(new Response("<html>", {status: 200}));
    expect((await kindOf(askQuestion("q", undefined, garbled))).kind).toBe(
      "unavailable",
    );
  });

  it("drops sources whose URL is not a plain web link", async () => {
    const body = {
      answer: "x",
      fallback: false,
      sources: [
        {url: "javascript:alert(1)", title: "bad", section: ""},
        {url: "https://sharpbuild.io/ok", title: "ok", section: ""},
      ],
    };
    const reply = await askQuestion(
      "q",
      undefined,
      vi.fn().mockResolvedValue(json(body)),
    );
    expect(reply.sources.map(s => s.title)).toEqual(["ok"]);
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

// ---------- streaming ----------
const enc = new TextEncoder();
const frame = (event: unknown) => `data: ${JSON.stringify(event)}\n\n`;
function streamOf(pieces: string[], init: ResponseInit = {}) {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      pieces.forEach(p => controller.enqueue(enc.encode(p)));
      controller.close();
    },
  });
  return new Response(body, {
    status: 200,
    headers: {"Content-Type": "text/event-stream"},
    ...init,
  });
}
const DONE = {
  type: "done",
  answer: "Yes, we do.",
  sources: [{url: "https://sharpbuild.io/a", title: "A", section: ""}],
  fallback: false,
};

describe("askQuestionStream", () => {
  it("delivers text pieces as they arrive, then resolves with the final answer", async () => {
    const pieces = [
      frame({type: "start"}),
      frame({type: "delta", text: "Yes, "}),
      frame({type: "delta", text: "we do."}),
      frame(DONE),
    ];
    const fetchMock = vi.fn().mockResolvedValue(streamOf(pieces));
    const received: string[] = [];
    const reply = await askQuestionStream(
      "Hi?",
      {onDelta: t => received.push(t)},
      fetchMock,
    );
    expect(received).toEqual(["Yes, ", "we do."]);
    expect(reply).toEqual({
      answer: "Yes, we do.",
      sources: DONE.sources,
      fallback: false,
    });
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toMatch(/\/chat\/stream$/);
    expect(JSON.parse(init.body)).toEqual({message: "Hi?"});
  });

  it("reassembles frames that are cut in the middle, even inside a multi-byte character", async () => {
    const all = enc.encode(
      frame({type: "delta", text: "caf\u00e9 \ud83d\ude00"}) + frame(DONE),
    );
    const cut = all.indexOf(0xc3) + 1; // split inside the two bytes of "\u00e9"
    const body = new ReadableStream<Uint8Array>({
      start(c) {
        c.enqueue(all.slice(0, cut));
        c.enqueue(all.slice(cut, cut + 9));
        c.enqueue(all.slice(cut + 9));
        c.close();
      },
    });
    const received: string[] = [];
    await askQuestionStream(
      "q",
      {onDelta: t => received.push(t)},
      vi.fn().mockResolvedValue(new Response(body, {status: 200})),
    );
    expect(received).toEqual(["caf\u00e9 \ud83d\ude00"]);
  });

  it("works when the whole answer arrives in one piece (a buffering proxy)", async () => {
    const reply = await askQuestionStream(
      "q",
      {},
      vi
        .fn()
        .mockResolvedValue(streamOf([frame({type: "start"}) + frame(DONE)])),
    );
    expect(reply.answer).toBe("Yes, we do.");
  });

  it("reads a last frame that has no closing blank line", async () => {
    const reply = await askQuestionStream(
      "q",
      {},
      vi.fn().mockResolvedValue(streamOf([`data: ${JSON.stringify(DONE)}`])),
    );
    expect(reply.answer).toBe("Yes, we do.");
  });

  it("raises an error event as unavailable, after delivering the text that came before it", async () => {
    const received: string[] = [];
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        streamOf([
          frame({type: "delta", text: "Part"}),
          frame({type: "error", message: "boom"}),
        ]),
      );
    const err = await kindOf(
      askQuestionStream("q", {onDelta: t => received.push(t)}, fetchMock),
    );
    expect(err.kind).toBe("unavailable");
    expect(received).toEqual(["Part"]);
  });

  it("treats a stream that ends without a final event as unavailable", async () => {
    const err = await kindOf(
      askQuestionStream(
        "q",
        {},
        vi
          .fn()
          .mockResolvedValue(streamOf([frame({type: "delta", text: "Part"})])),
      ),
    );
    expect(err.kind).toBe("unavailable");
  });

  it("maps HTTP errors and network failures before the stream starts, like the plain endpoint", async () => {
    const limited = vi
      .fn()
      .mockResolvedValue(
        json({}, {status: 429, headers: {"Retry-After": "7"}}),
      );
    const e1 = await kindOf(askQuestionStream("q", {}, limited));
    expect([e1.kind, e1.retryAfterSeconds]).toEqual(["rate_limited", 7]);
    expect(
      (
        await kindOf(
          askQuestionStream(
            "q",
            {},
            vi.fn().mockResolvedValue(json({}, {status: 422})),
          ),
        )
      ).kind,
    ).toBe("invalid");
    expect(
      (
        await kindOf(
          askQuestionStream(
            "q",
            {},
            vi.fn().mockResolvedValue(json({}, {status: 503})),
          ),
        )
      ).kind,
    ).toBe("unavailable");
    expect(
      (
        await kindOf(
          askQuestionStream(
            "q",
            {},
            vi.fn().mockRejectedValue(new TypeError("Failed to fetch")),
          ),
        )
      ).kind,
    ).toBe("network");
  });

  it("falls back to the plain endpoint when the backend has no streaming route yet", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(json({detail: "Not Found"}, {status: 404}))
      .mockResolvedValueOnce(json(OK));
    const reply = await askQuestionStream("q", {}, fetchMock);
    expect(reply.answer).toBe("Yes. [1]");
    expect(String(fetchMock.mock.calls[1][0])).toMatch(/\/chat$/);
  });

  it("lets an abort through unchanged, and drops unsafe source links", async () => {
    const abort = new DOMException("aborted", "AbortError");
    await expect(
      askQuestionStream("q", {}, vi.fn().mockRejectedValue(abort)),
    ).rejects.toBe(abort);
    const unsafe = {
      ...DONE,
      sources: [
        {url: "javascript:alert(1)", title: "bad", section: ""},
        DONE.sources[0],
      ],
    };
    const reply = await askQuestionStream(
      "q",
      {},
      vi.fn().mockResolvedValue(streamOf([frame(unsafe)])),
    );
    expect(reply.sources.map(s => s.title)).toEqual(["A"]);
  });
});
