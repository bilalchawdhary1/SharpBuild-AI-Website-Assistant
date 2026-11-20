/** True when the visitor's system asks for less motion. Safe on the server and in test environments. */
export function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

/** How near the bottom (in px) the log must be for new text to keep scrolling it into view. */
export const STICK_TO_BOTTOM_PX = 80;

/** Whether the visitor is reading the latest message; if they scrolled up, leave them there. */
export function isNearBottom(el: {scrollHeight: number; scrollTop: number; clientHeight: number}): boolean {
  return el.scrollHeight - el.scrollTop - el.clientHeight < STICK_TO_BOTTOM_PX;
}
