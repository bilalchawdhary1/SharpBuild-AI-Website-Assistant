export type AnswerPart = { type: "text"; text: string } | { type: "cite"; index: number };

/** Splits "We do X [1][2]." into text and citation parts. The backend already renumbers
 *  markers so [n] is the n-th item of the returned sources list. */
export function splitCitations(answer: string): AnswerPart[] {
  const parts: AnswerPart[] = [];
  let last = 0;
  for (const match of answer.matchAll(/\[(\d{1,2})\]/g)) {
    if (match.index > last) parts.push({ type: "text", text: answer.slice(last, match.index) });
    parts.push({ type: "cite", index: Number(match[1]) });
    last = match.index + match[0].length;
  }
  if (last < answer.length) parts.push({ type: "text", text: answer.slice(last) });
  return parts;
}
