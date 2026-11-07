"use client";

import { ASK_EVENT } from "@/lib/events";
import styles from "./TryChips.module.css";

type Props = { questions: string[]; label?: string };

/** Buttons on the page that open the chat widget and ask a question in it. */
export default function TryChips({ questions, label = "Try asking" }: Props) {
  return (
    <div className={styles.wrap} role="group" aria-label={label}>
      {questions.map((q) => (
        <button key={q} type="button" className={styles.chip}
                onClick={() => window.dispatchEvent(new CustomEvent(ASK_EVENT, { detail: q }))}>
          {q}
        </button>
      ))}
    </div>
  );
}
