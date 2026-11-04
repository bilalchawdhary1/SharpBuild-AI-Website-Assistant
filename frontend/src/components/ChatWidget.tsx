"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { askQuestion as defaultAsk, ChatApiError, type ChatSource } from "@/lib/chatApi";
import { splitCitations } from "@/lib/citations";
import styles from "./ChatWidget.module.css";

export const CONTACT_EMAIL = "hello@sharpbuild.io";
export const CONTACT_URL = "https://sharpbuild.io/contact";
export const MAX_LENGTH = 500; // must match the backend's ChatRequest limit

const STARTERS = [
  "What services do you offer?",
  "Do you build Shopify stores?",
  "How does your process work?",
  "How can I contact you?",
];

type Message =
  | { id: number; role: "user"; text: string }
  | { id: number; role: "assistant"; text: string; sources: ChatSource[]; needsHuman: boolean };

type Props = {
  /** Injected in tests; defaults to the real API call. */
  ask?: typeof defaultAsk;
  defaultOpen?: boolean;
};

function errorText(error: unknown): string {
  if (error instanceof ChatApiError) {
    switch (error.kind) {
      case "rate_limited":
        return `You're asking quickly. Please wait ${error.retryAfterSeconds ?? 30} seconds and try again.`;
      case "network":
        return "I couldn't reach the assistant. Please check your connection and try again.";
      case "invalid":
        return "That message couldn't be sent. Please shorten or rephrase it.";
    }
  }
  return "Something went wrong on our side. Please try again in a moment.";
}

function AnswerText({ text, sources }: { text: string; sources: ChatSource[] }) {
  return (
    <p className={styles.text}>
      {splitCitations(text).map((part, i) => {
        if (part.type === "text") return <span key={i}>{part.text}</span>;
        const source = sources[part.index - 1];
        if (!source) return null; // a marker with no matching source is dropped, never shown as a dead link
        return (
          <sup key={i}>
            <a href={source.url} target="_blank" rel="noopener noreferrer"
               aria-label={`Source ${part.index}: ${source.title}`} className={styles.cite}>
              [{part.index}]
            </a>
          </sup>
        );
      })}
    </p>
  );
}

function HumanContact() {
  return (
    <div className={styles.contact}>
      <p className={styles.contactTitle}>Want to talk to a person?</p>
      <a className={styles.contactLink} href={`mailto:${CONTACT_EMAIL}`}>Talk to a human</a>
      <a className={styles.contactLink} href={CONTACT_URL} target="_blank" rel="noopener noreferrer">Contact page</a>
    </div>
  );
}

export default function ChatWidget({ ask = defaultAsk, defaultOpen = false }: Props) {
  const [open, setOpen] = useState(defaultOpen);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const nextId = useRef(1);
  const abortRef = useRef<AbortController | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const panelId = useId();

  useEffect(() => () => abortRef.current?.abort(), []);
  useEffect(() => { if (open) inputRef.current?.focus(); }, [open]);
  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, loading]);

  const send = useCallback(async (raw: string) => {
    const text = raw.trim();
    if (!text || loading) return;
    setMessages((m) => [...m, { id: nextId.current++, role: "user", text }]);
    setInput("");
    setLoading(true);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const reply = await ask(text, controller.signal);
      setMessages((m) => [...m, {
        id: nextId.current++, role: "assistant", text: reply.answer,
        sources: reply.sources, needsHuman: reply.fallback,
      }]);
    } catch (error) {
      if (controller.signal.aborted) return;
      setMessages((m) => [...m, {
        id: nextId.current++, role: "assistant", text: errorText(error), sources: [], needsHuman: true,
      }]);
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [ask, loading]);

  const canSend = input.trim().length > 0 && !loading;

  return (
    <div className={styles.root}>
      {open && (
        <section id={panelId} role="dialog" aria-label="SharpBuild assistant" className={styles.panel}
                 onKeyDown={(e) => { if (e.key === "Escape") setOpen(false); }}>
          <header className={styles.header}>
            <div>
              <h2 className={styles.title}>SharpBuild Assistant</h2>
              <p className={styles.subtitle}>AI answers from sharpbuild.io</p>
            </div>
            <button type="button" className={styles.close} onClick={() => setOpen(false)} aria-label="Close chat">×</button>
          </header>

          <div ref={listRef} className={styles.messages} role="log" aria-live="polite" aria-label="Conversation">
            <div className={`${styles.bubble} ${styles.assistant}`}>
              <p className={styles.text}>
                Hi! I can answer questions about SharpBuild&apos;s services, process and work, using what&apos;s
                published on sharpbuild.io.
              </p>
            </div>

            {messages.map((m) =>
              m.role === "user" ? (
                <div key={m.id} className={`${styles.bubble} ${styles.user}`}><p className={styles.text}>{m.text}</p></div>
              ) : (
                <div key={m.id} className={`${styles.bubble} ${styles.assistant}`}>
                  <AnswerText text={m.text} sources={m.sources} />
                  {m.sources.length > 0 && (
                    <ol className={styles.sources} aria-label="Sources">
                      {m.sources.map((s, i) => (
                        <li key={s.url}>
                          <a href={s.url} target="_blank" rel="noopener noreferrer">{i + 1}. {s.title}</a>
                        </li>
                      ))}
                    </ol>
                  )}
                  {m.needsHuman && <HumanContact />}
                </div>
              ),
            )}

            {loading && (
              <div className={`${styles.bubble} ${styles.assistant}`} role="status" aria-label="Assistant is thinking">
                <span className={styles.dots} aria-hidden="true"><i /><i /><i /></span>
              </div>
            )}

            {messages.length === 0 && (
              <div className={styles.starters}>
                {STARTERS.map((q) => (
                  <button key={q} type="button" className={styles.chip} onClick={() => send(q)}>{q}</button>
                ))}
              </div>
            )}
          </div>

          <form className={styles.form} onSubmit={(e) => { e.preventDefault(); void send(input); }}>
            <input ref={inputRef} className={styles.input} type="text" value={input} maxLength={MAX_LENGTH}
                   onChange={(e) => setInput(e.target.value)} placeholder="Ask about SharpBuild…"
                   aria-label="Your question" autoComplete="off" />
            <button type="submit" className={styles.send} disabled={!canSend}>Send</button>
          </form>
          <p className={styles.notice}>
            {input.length >= MAX_LENGTH - 100 && <span>{input.length}/{MAX_LENGTH} · </span>}
            AI can make mistakes. Don&apos;t share personal or sensitive information; questions are processed by
            Google&apos;s Gemini API.
          </p>
        </section>
      )}

      <button type="button" className={styles.launcher} aria-expanded={open} aria-controls={open ? panelId : undefined}
              onClick={() => setOpen((o) => !o)}>
        {open ? "Hide chat" : "Ask the assistant"}
      </button>
    </div>
  );
}
