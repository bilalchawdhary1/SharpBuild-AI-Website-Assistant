export type ChatSource = { url: string; title: string; section: string };
export type ChatReply = { answer: string; sources: ChatSource[]; fallback: boolean };

export type ChatErrorKind = "rate_limited" | "network" | "invalid" | "unavailable";

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

const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(/\/+$/, "");

/** Only plain web links are ever rendered as links: never trust a URL just because the server sent it. */
export function isSafeUrl(value: string): boolean {
  try {
    const { protocol } = new URL(value);
    return protocol === "https:" || protocol === "http:";
  } catch {
    return false;
  }
}

function parseReply(data: unknown): ChatReply | null {
  if (typeof data !== "object" || data === null) return null;
  const { answer, sources, fallback } = data as Record<string, unknown>;
  if (typeof answer !== "string" || !Array.isArray(sources)) return null;
  const clean: ChatSource[] = [];
  for (const s of sources) {
    if (typeof s !== "object" || s === null) return null;
    const { url, title, section } = s as Record<string, unknown>;
    if (typeof url !== "string" || typeof title !== "string") return null;
    if (isSafeUrl(url)) clean.push({ url, title, section: typeof section === "string" ? section : "" });
  }
  return { answer, sources: clean, fallback: fallback === true };
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
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ChatApiError("network", "Could not reach the assistant.");
  }

  if (response.status === 429) {
    const seconds = Number(response.headers.get("Retry-After"));
    throw new ChatApiError("rate_limited", "Too many requests.", Number.isFinite(seconds) && seconds > 0 ? seconds : undefined);
  }
  if (response.status === 422) throw new ChatApiError("invalid", "The message was rejected.");
  if (!response.ok) throw new ChatApiError("unavailable", `The assistant returned ${response.status}.`);

  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new ChatApiError("unavailable", "The assistant sent an unreadable response.");
  }
  const reply = parseReply(data);
  if (!reply) throw new ChatApiError("unavailable", "The assistant sent an unexpected response.");
  return reply;
}
