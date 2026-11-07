export type Block =
  | { type: "p"; text: string }
  | { type: "ul"; items: string[] }
  | { type: "ol"; items: string[]; start: number };

const NUMBERED = /^\s*(\d{1,2})[.)]\s+(.+)$/;
const BULLET = /^\s*[•*-]\s+(.+)$/;

/** Turns the backend's plain-text answer into paragraphs and lists. The text itself is never
 *  treated as HTML: callers render every string as a React text node. */
export function parseAnswer(text: string): Block[] {
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  const flush = () => {
    if (paragraph.length) blocks.push({ type: "p", text: paragraph.join(" ") });
    paragraph = [];
  };

  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) { flush(); continue; }

    const numbered = NUMBERED.exec(line);
    const bullet = numbered ? null : BULLET.exec(line);
    const last = blocks[blocks.length - 1];

    if (numbered) {
      flush();
      if (last?.type === "ol" && paragraph.length === 0) last.items.push(numbered[2]);
      else blocks.push({ type: "ol", items: [numbered[2]], start: Number(numbered[1]) });
    } else if (bullet) {
      flush();
      if (last?.type === "ul" && paragraph.length === 0) last.items.push(bullet[1]);
      else blocks.push({ type: "ul", items: [bullet[1]] });
    } else {
      paragraph.push(line);
    }
  }
  flush();
  return blocks;
}
