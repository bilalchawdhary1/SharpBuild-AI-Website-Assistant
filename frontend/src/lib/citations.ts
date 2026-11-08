/** The backend removes "[1]" citation markers and returns sources separately. This is a safety net
 *  for an older backend (or a model slip): any marker left in the text is removed before display. */
export function stripCitations(text: string): string {
  return text
    .replace(/(\[\d{1,2}(?:\s*,\s*\d{1,2})*\])\s*,\s*(?=\[\d)/g, "$1") // "[1], [2]" -> "[1][2]"
    .replace(/[ \t]*\[\d{1,2}(?:\s*,\s*\d{1,2})*\]/g, "");
}
