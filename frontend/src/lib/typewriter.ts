/** How many characters should be visible after the next tick. Reveals 2 to 12 characters per tick:
 *  slower when little text is waiting (smooth, readable), faster when a lot has arrived at once
 *  (a whole answer in one piece), so the reveal never falls far behind. */
export function nextShown(shown: number, total: number): number {
  const backlog = total - shown;
  if (backlog <= 0) return total;
  const step = Math.min(12, Math.max(2, Math.ceil(backlog / 18)));
  return Math.min(total, shown + step);
}

export function commonPrefixLength(a: string, b: string): number {
  const max = Math.min(a.length, b.length);
  let i = 0;
  while (i < max && a[i] === b[i]) i++;
  return i;
}
