"use client";

import {useEffect, useId, useRef, useState, type FormEvent, type KeyboardEvent} from "react";
import {ChatApiError, type ChatHistoryTurn} from "@/lib/chatApi";
import {
  LEAD_CONSENT_TEXT,
  SHARE_CHAT_TEXT,
  submitLead as defaultSubmit,
} from "@/lib/leadApi";
import styles from "./LeadForm.module.css";

const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/;

type Props = {
  history: ChatHistoryTurn[];
  /** "handoff": the visitor asked for a person. Changes the wording and offers to share the chat. */
  kind?: "sales" | "handoff";
  /** Injected in tests; defaults to the real POST /lead call. */
  submit?: typeof defaultSubmit;
  onSent?: () => void;
  onCancel?: () => void;
};
type Errors = {name?: string; email?: string; consent?: string; form?: string};

function failureText(error: unknown): string {
  if (error instanceof ChatApiError) {
    switch (error.kind) {
      case "rate_limited":
        return "Too many attempts. Please wait a minute and try again.";
      case "network":
        return "Couldn't reach the server. Please check your connection and try again.";
      case "invalid":
        return "Please check your details (email and phone) and try again.";
    }
  }
  return "We couldn't save your details. Please email hello@sharpbuild.io instead.";
}

export default function LeadForm({
  history,
  kind = "sales",
  submit = defaultSubmit,
  onSent,
  onCancel,
}: Props) {
  const id = useId();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [company, setCompany] = useState("");
  const [message, setMessage] = useState("");
  const [website, setWebsite] = useState(""); // honeypot
  const [consent, setConsent] = useState(false);
  const [shareChat, setShareChat] = useState(false);
  const [errors, setErrors] = useState<Errors>({});
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const nameRef = useRef<HTMLInputElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const consentRef = useRef<HTMLInputElement>(null);

  // The form appears because the visitor asked for it: move keyboard / screen-reader focus into it.
  useEffect(() => {
    nameRef.current?.focus();
  }, []);

  const dirty = Boolean(name || email || phone || company || message);
  // Escape closes the whole chat, which would throw away what was typed here. Keep it for an
  // untouched form; the Close button always works.
  const onFormKeyDown = (event: KeyboardEvent) => {
    if (event.key === "Escape" && dirty) event.stopPropagation();
  };

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (sending) return;
    const next: Errors = {};
    if (!name.trim()) next.name = "Please enter your name.";
    if (!EMAIL.test(email.trim())) next.email = "Please enter a valid email address.";
    if (!consent) next.consent = "Please tick the box to agree.";
    setErrors(next);
    if (Object.keys(next).length) {
      (next.name ? nameRef : next.email ? emailRef : consentRef).current?.focus();
      return;
    }

    setSending(true);
    try {
      await submit({name, email, phone, company, message, consent, kind, shareChat, history, website});
      setSent(true);
      onSent?.();
    } catch (error) {
      setErrors({form: failureText(error)});
    } finally {
      setSending(false);
    }
  };

  if (sent)
    return (
      <p className={styles.thanks} role='status'>
        {kind === "handoff"
          ? "Thanks! A member of the SharpBuild team will contact you at the email you gave."
          : "Thanks! The SharpBuild team will contact you at the email you gave."}
      </p>
    );

  return (
    <form className={styles.form} onSubmit={onSubmit} onKeyDown={onFormKeyDown} noValidate
      aria-label='Leave your details'>
      <p className={styles.intro}>
        {kind === "handoff"
          ? "Leave your details and a person from the SharpBuild team will get back to you. This form is not sent to the AI."
          : "Optional: leave your details and the team will follow up. This form is not sent to the AI."}
      </p>

      <label className={styles.field} htmlFor={`${id}-name`}>
        Your name
        <input id={`${id}-name`} ref={nameRef} className={styles.input} value={name} maxLength={120}
          autoComplete='name' onChange={e => setName(e.target.value)}
          aria-invalid={errors.name ? true : undefined}
          aria-describedby={errors.name ? `${id}-name-error` : undefined} />
      </label>
      {errors.name && <p id={`${id}-name-error`} className={styles.error} role='alert'>{errors.name}</p>}

      <label className={styles.field} htmlFor={`${id}-email`}>
        Email
        <input id={`${id}-email`} ref={emailRef} className={styles.input} type='email' value={email}
          maxLength={254} autoComplete='email' onChange={e => setEmail(e.target.value)}
          aria-invalid={errors.email ? true : undefined}
          aria-describedby={errors.email ? `${id}-email-error` : undefined} />
      </label>
      {errors.email && <p id={`${id}-email-error`} className={styles.error} role='alert'>{errors.email}</p>}

      <label className={styles.field} htmlFor={`${id}-phone`}>
        Phone (optional)
        <input id={`${id}-phone`} className={styles.input} type='tel' value={phone} maxLength={40}
          autoComplete='tel' onChange={e => setPhone(e.target.value)} />
      </label>

      <label className={styles.field} htmlFor={`${id}-company`}>
        Company (optional)
        <input id={`${id}-company`} className={styles.input} value={company} maxLength={120}
          autoComplete='organization' onChange={e => setCompany(e.target.value)} />
      </label>

      <label className={styles.field} htmlFor={`${id}-message`}>
        {kind === "handoff" ? "How can we help? (optional)" : "What are you building? (optional)"}
        <textarea id={`${id}-message`} className={styles.input} rows={3} value={message}
          maxLength={1000} onChange={e => setMessage(e.target.value)} />
      </label>

      {/* Honeypot: hidden from people and assistive tech; bots tend to fill every field. */}
      <input className={styles.trap} name='website' value={website} tabIndex={-1}
        autoComplete='off' aria-hidden='true' onChange={e => setWebsite(e.target.value)} />

      <label className={styles.consent} htmlFor={`${id}-consent`}>
        <input id={`${id}-consent`} ref={consentRef} type='checkbox' checked={consent}
          onChange={e => setConsent(e.target.checked)}
          aria-invalid={errors.consent ? true : undefined}
          aria-describedby={errors.consent ? `${id}-consent-error` : undefined} />
        <span>{LEAD_CONSENT_TEXT}</span>
      </label>
      {errors.consent && <p id={`${id}-consent-error`} className={styles.error} role='alert'>{errors.consent}</p>}

      {kind === "handoff" && history.some(turn => turn.role === "user") && (
        <label className={styles.consent} htmlFor={`${id}-share`}>
          <input id={`${id}-share`} type='checkbox' checked={shareChat}
            onChange={e => setShareChat(e.target.checked)} />
          <span>{SHARE_CHAT_TEXT}</span>
        </label>
      )}
      {errors.form && <p className={styles.error} role='alert'>{errors.form}</p>}

      <div className={styles.actions}>
        <button type='submit' className={styles.primary} disabled={sending}>
          {sending ? "Sending…" : "Send my details"}
        </button>
        {onCancel && (
          <button type='button' className={styles.secondary} onClick={onCancel} disabled={sending}>
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}
