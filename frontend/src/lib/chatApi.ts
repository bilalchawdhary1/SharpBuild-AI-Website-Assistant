export type ChatSource = {url: string; title: string; section: string};
export type ChatReply = {
  answer: string;
  sources: ChatSource[];
  fallback: boolean;
};

export type ChatErrorKind =
  | "rate_limited"
  | "network"
  | "invalid"
  | "unavailable";

export class ChatApiError extends Error {
  constructor(
    public kind: ChatErrorKind,
    message: string,
    public retryAfterSeconds?: number,
  ) {
    super(message);
    this.name = "ChatApiError";
  }
}

import {parseSse} from "./sse";

const API_URL = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000"
).replace(/\/+$/, "");

/** Only plain web links are ever rendered as links: never trust a URL just because the server sent it. */
export function isSafeUrl(value: string): boolean {
  try {
    const {protocol} = new URL(value);
    return protocol === "https:" || protocol === "http:";
  } catch {
    return false;
  }
}

function parseReply(data: unknown): ChatReply | null {
  if (typeof data !== "object" || data === null) return null;
  const {answer, sources, fallback} = data as Record<string, unknown>;
  if (typeof answer !== "string" || !Array.isArray(sources)) return null;
  const clean: ChatSource[] = [];
  for (const s of sources) {
    if (typeof s !== "object" || s === null) return null;
    const {url, title, section} = s as Record<string, unknown>;
    if (typeof url !== "string" || typeof title !== "string") return null;
    if (isSafeUrl(url))
      clean.push({
        url,
        title,
        section: typeof section === "string" ? section : "",
      });
  }
  return {answer, sources: clean, fallback: fallback === true};
}

function throwForStatus(response: Response): void {
  if (response.status === 429) {
    const seconds = Number(response.headers.get("Retry-After"));
    throw new ChatApiError(
      "rate_limited",
      "Too many requests.",
      Number.isFinite(seconds) && seconds > 0 ? seconds : undefined,
    );
  }
  if (response.status === 422)
    throw new ChatApiError("invalid", "The message was rejected.");
  if (!response.ok)
    throw new ChatApiError(
      "unavailable",
      `The assistant returned ${response.status}.`,
    );
}

export async function askQuestion(
  message: string,
  signal?: AbortSignal,
  fetchImpl: typeof fetch = fetch,
): Promise<ChatReply> {
  let response: Response;
  try {
    response = await fetchImpl(`${API_URL}/chat`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({message}),
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      throw error;
    throw new ChatApiError("network", "Could not reach the assistant.");
  }

  throwForStatus(response);

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new ChatApiError(
      "unavailable",
      "The assistant sent an unreadable response.",
    );
  }
  const reply = parseReply(data);
  if (!reply)
    throw new ChatApiError(
      "unavailable",
      "The assistant sent an unexpected response.",
    );
  return reply;
}

export type StreamHandlers = {
  signal?: AbortSignal;
  /** Called with each new piece of the answer text as it arrives. */
  onDelta?: (text: string) => void;
};

/** Asks the streaming endpoint. Resolves with the final answer, sources and fallback flag;
 *  `onDelta` receives the text piece by piece while the answer is being written. */
export async function askQuestionStream(
  message: string,
  {signal, onDelta}: StreamHandlers = {},
  fetchImpl: typeof fetch = fetch,
): Promise<ChatReply> {
  let response: Response;
  try {
    response = await fetchImpl(`${API_URL}/chat/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify({message}),
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      throw error;
    throw new ChatApiError("network", "Could not reach the assistant.");
  }

  // A backend without the streaming endpoint (older deployment): use the plain endpoint instead.
  if (response.status === 404 || response.status === 405)
    return askQuestion(message, signal, fetchImpl);
  throwForStatus(response);

  let final: ChatReply | null = null;
  const handle = (event: unknown) => {
    if (typeof event !== "object" || event === null) return;
    const e = event as Record<string, unknown>;
    if (e.type === "delta" && typeof e.text === "string") {
      onDelta?.(e.text);
    } else if (e.type === "done") {
      const reply = parseReply(e);
      if (!reply)
        throw new ChatApiError(
          "unavailable",
          "The assistant sent an unexpected response.",
        );
      final = reply;
    } else if (e.type === "error") {
      throw new ChatApiError(
        "unavailable",
        typeof e.message === "string" ? e.message : "The assistant failed.",
      );
    }
  };

  try {
    let buffer = "";
    const reader = response.body?.getReader();
    if (reader) {
      const decoder = new TextDecoder();
      for (;;) {
        const {done, value} = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, {stream: true});
        const parsed = parseSse(buffer);
        buffer = parsed.rest;
        parsed.events.forEach(handle);
      }
      buffer += decoder.decode();
    } else {
      buffer = await response.text(); // no streaming support in this environment: read it all at once
    }
    parseSse(buffer + "\n\n").events.forEach(handle); // a last frame without its blank line
  } catch (error) {
    if (error instanceof ChatApiError) throw error;
    if (error instanceof DOMException && error.name === "AbortError")
      throw error;
    throw new ChatApiError("network", "The connection was interrupted.");
  }

  if (!final)
    throw new ChatApiError("unavailable", "The answer ended unexpectedly.");
  return final;
}
