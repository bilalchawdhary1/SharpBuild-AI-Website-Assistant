/** Splits a growing text buffer into complete server-sent events (JSON in "data:" lines).
 *  Returns what it could parse and the unfinished remainder to keep for the next piece. */
export function parseSse(buffer: string): {events: unknown[]; rest: string} {
  const events: unknown[] = [];
  let rest = buffer;
  for (;;) {
    const boundary = /\r?\n\r?\n/.exec(rest);
    if (!boundary) break;
    const frame = rest.slice(0, boundary.index);
    rest = rest.slice(boundary.index + boundary[0].length);
    const data = frame
      .split(/\r?\n/)
      .filter(line => line.startsWith("data:"))
      .map(line => line.slice(5).replace(/^ /, ""))
      .join("\n");
    if (!data) continue; // comments such as ": ping", and empty frames
    try {
      events.push(JSON.parse(data));
    } catch {
      /* a malformed frame is skipped, never fatal */
    }
  }
  return {events, rest};
}
