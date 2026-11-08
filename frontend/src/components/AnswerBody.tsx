import {stripCitations} from "@/lib/citations";
import {parseAnswer, parseInline} from "@/lib/format";
import styles from "./AnswerBody.module.css";

function Inline({text}: {text: string}) {
  return (
    <>
      {parseInline(text).map((segment, i) =>
        segment.bold ? (
          <strong key={i}>{segment.text}</strong>
        ) : (
          <span key={i}>{segment.text}</span>
        ),
      )}
    </>
  );
}

/** Renders a plain-text answer as paragraphs, lists and bold text. Every string is a React text
 *  node, so nothing the model writes can become HTML. */
export default function AnswerBody({
  text,
  caret = false,
}: {
  text: string;
  caret?: boolean;
}) {
  const blocks = parseAnswer(stripCitations(text));
  const cursor = caret ? (
    <span className={styles.caret} aria-hidden='true' />
  ) : null;
  const lastBlock = blocks.length - 1;

  return (
    <div className={styles.answer}>
      {blocks.map((block, i) => {
        const tail = i === lastBlock ? cursor : null;
        if (block.type === "p")
          return (
            <p key={i}>
              <Inline text={block.text} />
              {tail}
            </p>
          );
        const last = block.items.length - 1;
        const items = block.items.map((item, j) => (
          <li key={j}>
            <Inline text={item} />
            {j === last ? tail : null}
          </li>
        ));
        return block.type === "ol" ? (
          <ol key={i} start={block.start}>
            {items}
          </ol>
        ) : (
          <ul key={i}>{items}</ul>
        );
      })}
      {blocks.length === 0 && cursor}
    </div>
  );
}
