"use client";

import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import {
  askQuestionStream as defaultAsk,
  ChatApiError,
  type ChatReply,
  type ChatSource,
} from "@/lib/chatApi";
import {ASK_EVENT} from "@/lib/events";
import {commonPrefixLength, nextShown} from "@/lib/typewriter";
import AnswerBody from "./AnswerBody";
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

type UserMessage = {id: number; role: "user"; text: string};
type AssistantMessage = {
  id: number;
  role: "assistant";
  text: string;
  sources: ChatSource[];
  needsHuman: boolean;
  streaming?: boolean;
  note?: string;
  retryQuestion?: string;
};
type Message = UserMessage | AssistantMessage;

/** The answer being written right now: what has arrived, and how much of it is visible. */
type StreamState = {
  id: number;
  question: string;
  received: string;
  shown: number;
  final?: ChatReply;
  error?: unknown;
};

type Props = {
  /** Injected in tests; defaults to the real streaming API call. */
  ask?: typeof defaultAsk;
  defaultOpen?: boolean;
  /** Show a "still working" hint after this many milliseconds without any text. */
  slowHintMs?: number;
  /** Milliseconds between reveal steps of the typewriter effect. */
  tickMs?: number;
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

const Icon = ({d}: {d: string}) => (
  <svg
    viewBox='0 0 24 24'
    width='18'
    height='18'
    fill='none'
    stroke='currentColor'
    strokeWidth='2'
    strokeLinecap='round'
    strokeLinejoin='round'
    aria-hidden='true'
  >
    <path d={d} />
  </svg>
);
const ICONS = {
  chat: "M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z",
  close: "M18 6 6 18M6 6l12 12",
  send: "m22 2-7 20-4-9-9-4zM22 2 11 13",
  reset: "M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5",
};

function HumanContact() {
  return (
    <div className={styles.contact}>
      <p className={styles.contactTitle}>Want to talk to a person?</p>
      <a className={styles.contactPrimary} href={`mailto:${CONTACT_EMAIL}`}>
        Talk to a human
      </a>
      <a
        className={styles.contactLink}
        href={CONTACT_URL}
        target='_blank'
        rel='noopener noreferrer'
      >
        Contact page
      </a>
    </div>
  );
}

export default function ChatWidget({
  ask = defaultAsk,
  defaultOpen = false,
  slowHintMs = 6000,
  tickMs = 28,
}: Props) {
  const [open, setOpen] = useState(defaultOpen);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [slow, setSlow] = useState(false);
  const nextId = useRef(1);
  const loadingRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);
  const streamRef = useRef<StreamState | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const panelId = useId();

  const hasStreamingText = messages.some(
    m => m.role === "assistant" && m.streaming,
  );

  const stopTimer = () => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
  };

  useEffect(
    () => () => {
      abortRef.current?.abort();
      stopTimer();
    },
    [],
  );
  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);
  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, loading, slow]);
  useEffect(() => {
    if (!loading || hasStreamingText) {
      setSlow(false);
      return;
    }
    const timer = setTimeout(() => setSlow(true), slowHintMs);
    return () => clearTimeout(timer);
  }, [loading, hasStreamingText, slowHintMs]);
  useEffect(() => {
    if (input === "" && inputRef.current)
      inputRef.current.style.height = "auto";
  }, [input]);

  /** Creates or updates the assistant message for the answer being written. */
  const show = (state: StreamState, patch: Partial<AssistantMessage> = {}) => {
    const message: AssistantMessage = {
      id: state.id,
      role: "assistant",
      text: state.received.slice(0, state.shown),
      sources: [],
      needsHuman: false,
      streaming: true,
      ...patch,
    };
    setMessages(prev =>
      prev.some(m => m.id === state.id)
        ? prev.map(m => (m.id === state.id ? message : m))
        : [...prev, message],
    );
  };

  const finish = (state: StreamState) => {
    stopTimer();
    streamRef.current = null;
    loadingRef.current = false;
    setLoading(false);
    if (state.error) {
      const partial = state.received.slice(0, state.shown).trim();
      show(
        state,
        partial
          ? {
              text: partial,
              note: "The answer was cut short.",
              needsHuman: true,
              retryQuestion: state.question,
              streaming: false,
            }
          : {
              text: errorText(state.error),
              needsHuman: true,
              retryQuestion: state.question,
              streaming: false,
            },
      );
    } else if (state.final) {
      show(state, {
        text: state.final.answer,
        sources: state.final.sources,
        needsHuman: state.final.fallback,
        streaming: false,
      });
    }
  };

  const tick = () => {
    const state = streamRef.current;
    if (!state) return;
    if (state.shown < state.received.length) {
      state.shown = nextShown(state.shown, state.received.length);
      show(state);
    }
    // Everything that arrived is visible and the request has ended: show sources and finish.
    if (state.shown >= state.received.length && (state.final || state.error))
      finish(state);
  };

  const ensureTimer = () => {
    if (!timerRef.current) timerRef.current = setInterval(tick, tickMs);
  };

  const send = useCallback(
    async (raw: string, echo = true) => {
      const text = raw.trim();
      if (!text || loadingRef.current) return;
      loadingRef.current = true;
      if (echo)
        setMessages(m => [...m, {id: nextId.current++, role: "user", text}]);
      setInput("");
      setLoading(true);

      const controller = new AbortController();
      abortRef.current = controller;
      const state: StreamState = {
        id: nextId.current++,
        question: text,
        received: "",
        shown: 0,
      };
      streamRef.current = state;

      try {
        const reply = await ask(text, {
          signal: controller.signal,
          onDelta: piece => {
            state.received += piece;
            ensureTimer();
          },
        });
        // The final answer is authoritative: keep what is already visible if it matches, else continue from the match.
        state.shown = Math.min(
          state.shown,
          commonPrefixLength(
            state.received.slice(0, state.shown),
            reply.answer,
          ),
        );
        state.received = reply.answer;
        state.final = reply;
      } catch (error) {
        if (controller.signal.aborted) return; // the Stop button or New chat already took care of it
        state.error = error;
      }
      ensureTimer();
      // eslint-disable-next-line react-hooks/exhaustive-deps
    },
    [ask, tickMs],
  );

  const sendRef = useRef(send);
  sendRef.current = send;
  useEffect(() => {
    const onAsk = (event: Event) => {
      const question = (event as CustomEvent<unknown>).detail;
      if (typeof question !== "string") return;
      setOpen(true);
      void sendRef.current(question);
    };
    window.addEventListener(ASK_EVENT, onAsk);
    return () => window.removeEventListener(ASK_EVENT, onAsk);
  }, []);

  const stop = () => {
    const state = streamRef.current;
    if (!state) return;
    abortRef.current?.abort();
    stopTimer();
    streamRef.current = null;
    loadingRef.current = false;
    setLoading(false);
    const partial = state.received.slice(0, state.shown).trim();
    if (partial) show(state, {text: partial, streaming: false});
  };

  const retry = (message: AssistantMessage) => {
    if (!message.retryQuestion) return;
    setMessages(m => m.filter(x => x.id !== message.id));
    void send(message.retryQuestion, false); // the user's bubble is already in the conversation
  };

  const reset = () => {
    abortRef.current?.abort();
    stopTimer();
    streamRef.current = null;
    loadingRef.current = false;
    setMessages([]);
    setInput("");
    setLoading(false);
    inputRef.current?.focus();
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault(); // Enter sends; Shift+Enter adds a new line
      void send(input);
    }
  };

  const canSend = input.trim().length > 0;

  return (
    <div className={styles.root} data-open={open}>
      {open && (
        <section
          id={panelId}
          role='dialog'
          aria-label='SharpBuild assistant'
          className={styles.panel}
          onKeyDown={e => {
            if (e.key === "Escape") setOpen(false);
          }}
        >
          <header className={styles.header}>
            <span className={styles.avatar} aria-hidden='true'>
              SB
            </span>
            <div className={styles.headerText}>
              <h2 className={styles.title}>SharpBuild Assistant</h2>
              <p className={styles.subtitle}>AI answers from sharpbuild.io</p>
            </div>
            {messages.length > 0 && (
              <button
                type='button'
                className={styles.iconButton}
                onClick={reset}
                aria-label='Start a new chat'
                title='New chat'
              >
                <Icon d={ICONS.reset} />
              </button>
            )}
            <button
              type='button'
              className={styles.iconButton}
              onClick={() => setOpen(false)}
              aria-label='Close chat'
              title='Close'
            >
              <Icon d={ICONS.close} />
            </button>
          </header>

          <div
            ref={listRef}
            className={styles.messages}
            role='log'
            aria-live='polite'
            aria-label='Conversation'
          >
            <div className={`${styles.bubble} ${styles.assistant}`}>
              <p className={styles.plain}>
                Hi! I can answer questions about SharpBuild&apos;s services,
                process and work, using what&apos;s published on sharpbuild.io.
              </p>
            </div>

            {messages.length === 0 && (
              <div className={styles.starters}>
                {STARTERS.map(q => (
                  <button
                    key={q}
                    type='button'
                    className={styles.chip}
                    onClick={() => void send(q)}
                  >
                    {q}
                  </button>
                ))}
              </div>
            )}

            {messages.map(m =>
              m.role === "user" ? (
                <div key={m.id} className={`${styles.bubble} ${styles.user}`}>
                  <p className={styles.plain}>{m.text}</p>
                </div>
              ) : (
                <div
                  key={m.id}
                  aria-busy={m.streaming ? true : undefined}
                  className={`${styles.bubble} ${styles.assistant} ${m.needsHuman ? styles.notice : ""}`}
                >
                  <AnswerBody text={m.text} caret={m.streaming} />
                  {m.note && <p className={styles.note}>{m.note}</p>}
                  {!m.streaming && m.sources.length > 0 && (
                    <ul className={styles.sources} aria-label='Sources'>
                      {m.sources.map((s, i) => (
                        <li key={s.url}>
                          <a
                            className={styles.sourceChip}
                            href={s.url}
                            target='_blank'
                            rel='noopener noreferrer'
                            title={s.title}
                          >{`${i + 1}. ${s.title}`}</a>
                        </li>
                      ))}
                    </ul>
                  )}
                  {m.retryQuestion && (
                    <button
                      type='button'
                      className={styles.retry}
                      onClick={() => retry(m)}
                    >
                      Try again
                    </button>
                  )}
                  {!m.streaming && m.needsHuman && <HumanContact />}
                </div>
              ),
            )}

            {loading && !hasStreamingText && (
              <div
                className={`${styles.bubble} ${styles.assistant}`}
                role='status'
                aria-label='Assistant is thinking'
              >
                <span className={styles.dots} aria-hidden='true'>
                  <i />
                  <i />
                  <i />
                </span>
                {slow && (
                  <p className={styles.slow}>
                    Still working on it. The AI service is busy right now.
                  </p>
                )}
              </div>
            )}
          </div>

          <form
            className={styles.form}
            onSubmit={e => {
              e.preventDefault();
              void send(input);
            }}
          >
            <textarea
              ref={inputRef}
              className={styles.input}
              rows={1}
              value={input}
              maxLength={MAX_LENGTH}
              onChange={e => {
                setInput(e.target.value);
                e.target.style.height = "auto";
                e.target.style.height = `${Math.min(e.target.scrollHeight, 120)}px`;
              }}
              onKeyDown={onKeyDown}
              placeholder='Ask about SharpBuild…'
              aria-label='Your question'
            />
            {loading ? (
              <button
                type='button'
                className={styles.send}
                onClick={stop}
                aria-label='Stop generating'
                title='Stop'
              >
                <span className={styles.stopSquare} aria-hidden='true' />
              </button>
            ) : (
              <button
                type='submit'
                className={styles.send}
                disabled={!canSend}
                aria-label='Send'
              >
                <Icon d={ICONS.send} />
              </button>
            )}
          </form>
          <p className={styles.footnote}>
            {input.length >= MAX_LENGTH - 100 && (
              <span>
                {input.length}/{MAX_LENGTH} ·{" "}
              </span>
            )}
            AI can make mistakes. Don&apos;t share personal or sensitive
            information; questions are processed by Google&apos;s Gemini API.
          </p>
        </section>
      )}

      <button
        type='button'
        className={styles.launcher}
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        onClick={() => setOpen(o => !o)}
      >
        <Icon d={open ? ICONS.close : ICONS.chat} />
        <span>{open ? "Hide chat" : "Ask the assistant"}</span>
      </button>
    </div>
  );
}
