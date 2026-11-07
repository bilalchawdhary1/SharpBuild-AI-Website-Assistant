import type { ChatSource } from "@/lib/chatApi";
import { splitCitations } from "@/lib/citations";
import { parseAnswer } from "@/lib/format";
import styles from "./AnswerBody.module.css";

function Inline({ text, sources }: { text: string; sources: ChatSource[] }) {
  return (
    <>
      {splitCitations(text).map((part, i) => {
        if (part.type === "text") return <span key={i}>{part.text}</span>;
        const source = sources[part.index - 1];
        if (!source) return null; // a marker with no matching source is dropped, never shown as a dead link
        return (
          <sup key={i} className={styles.sup}>
            <a href={source.url} target="_blank" rel="noopener noreferrer" className={styles.cite}
               aria-label={`Source ${part.index}: ${source.title}`} title={source.title}>
              {part.index}
            </a>
          </sup>
        );
      })}
    </>
  );
}

export default function AnswerBody({ text, sources }: { text: string; sources: ChatSource[] }) {
  return (
    <div className={styles.answer}>
      {parseAnswer(text).map((block, i) => {
        if (block.type === "p") return <p key={i}><Inline text={block.text} sources={sources} /></p>;
        const items = block.items.map((item, j) => <li key={j}><Inline text={item} sources={sources} /></li>);
        return block.type === "ol"
          ? <ol key={i} start={block.start}>{items}</ol>
          : <ul key={i}>{items}</ul>;
      })}
    </div>
  );
}
