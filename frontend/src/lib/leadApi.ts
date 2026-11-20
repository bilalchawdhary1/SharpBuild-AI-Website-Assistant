import {
  API_URL,
  ChatApiError,
  throwForStatus,
  type ChatHistoryTurn,
} from "./chatApi";

/** Shown next to the checkbox. Backend CONSENT_VERSION must be bumped when this wording changes. */
export const LEAD_CONSENT_TEXT =
  "I agree that SharpBuild may store these details and contact me about my enquiry. " +
  "They are sent to SharpBuild only, not to the AI.";

/** Separate opt-in shown only on handoff requests. */
export const SHARE_CHAT_TEXT =
  "Also share my recent messages from this chat with the team, so I don't have to repeat myself (optional).";

export type LeadPayload = {
  name: string;
  email: string;
  phone?: string;
  company?: string;
  message?: string;
  consent: boolean;
  /** "handoff" = the visitor asked to talk to a person (the team answers these first). */
  kind?: "sales" | "handoff";
  /** Pass the visitor's own recent messages to the team. Off unless they tick the box. */
  shareChat?: boolean;
  /** Recent chat turns: the server uses them only to score the lead and does not store them. */
  history?: ChatHistoryTurn[];
  /** Honeypot: stays empty for people. */
  website?: string;
};

/** Sends the details straight to the backend /lead endpoint (never through the chat or the AI). */
export async function submitLead(
  payload: LeadPayload,
  signal?: AbortSignal,
  fetchImpl: typeof fetch = fetch,
): Promise<void> {
  const optional = (key: "phone" | "company" | "message") => {
    const value = payload[key]?.trim();
    return value ? {[key]: value} : {};
  };
  const history = (payload.history ?? [])
    .slice(-6)
    .map(turn => ({role: turn.role, text: turn.text.trim().slice(0, 500)}))
    .filter(turn => turn.text);
  const body = {
    name: payload.name.trim(),
    email: payload.email.trim(),
    consent: payload.consent,
    ...(payload.kind === "handoff" ? {kind: "handoff"} : {}),
    ...(payload.shareChat ? {share_chat: true} : {}),
    ...optional("phone"),
    ...optional("company"),
    ...optional("message"),
    ...(history.length ? {history} : {}),
    ...(payload.website ? {website: payload.website} : {}),
  };

  let response: Response;
  try {
    response = await fetchImpl(`${API_URL}/lead`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ChatApiError("network", "Could not reach the server.");
  }
  throwForStatus(response);
}
