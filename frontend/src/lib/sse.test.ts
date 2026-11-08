import { expect, it } from "vitest";
import { parseSse } from "./sse";

it("parses complete frames and keeps the unfinished remainder", () => {
  const { events, rest } = parseSse('data: {"type":"delta","text":"Hi"}\n\ndata: {"type":"done"}\n\ndata: {"type":"del');
  expect(events).toEqual([{ type: "delta", text: "Hi" }, { type: "done" }]);
  expect(rest).toBe('data: {"type":"del');
});

it("joins the rest with the next piece and handles CRLF", () => {
  const first = parseSse('data: {"a":1}\r\n\r\ndata: {"b"');
  const second = parseSse(first.rest + ":2}\r\n\r\n");
  expect([...first.events, ...second.events]).toEqual([{ a: 1 }, { b: 2 }]);
});

it("skips comments, empty frames and malformed JSON without failing", () => {
  expect(parseSse(': ping\n\n\n\ndata: {not json}\n\ndata: {"ok":true}\n\n').events).toEqual([{ ok: true }]);
});

it("accepts 'data:' with or without a space and non-ASCII text", () => {
  expect(parseSse('data:{"t":"é 😀"}\n\n').events).toEqual([{ t: "é 😀" }]);
});
