import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { ASK_EVENT } from "@/lib/events";
import TryChips from "./TryChips";

it("asks the widget the question that was clicked", async () => {
  const listener = vi.fn();
  window.addEventListener(ASK_EVENT, listener);
  render(<TryChips questions={["Do you build Shopify stores?", "Weather?"]} />);
  await userEvent.click(screen.getByRole("button", { name: "Do you build Shopify stores?" }));
  window.removeEventListener(ASK_EVENT, listener);
  expect(listener).toHaveBeenCalledTimes(1);
  expect((listener.mock.calls[0][0] as CustomEvent).detail).toBe("Do you build Shopify stores?");
  expect(screen.getByRole("group", { name: /try asking/i })).toBeInTheDocument();
});
