import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ChatApiError, type ChatReply } from "@/lib/chatApi";
import { ASK_EVENT } from "@/lib/events";
import ChatWidget, { CONTACT_EMAIL, MAX_LENGTH } from "./ChatWidget";

const ANSWER: ChatReply = {
  answer: "Yes, SharpBuild builds Shopify stores [1][2].",
  sources: [
    { url: "https://sharpbuild.io/services/ecommerce-development", title: "E-commerce Development", section: "" },
    { url: "https://sharpbuild.io/portfolio/nothingfishy-shopify-store", title: "NothingFishy", section: "" },
  ],
  fallback: false,
};
const FALLBACK: ChatReply = { answer: "I couldn't find that information.", sources: [], fallback: true };

function setup(ask = vi.fn().mockResolvedValue(ANSWER), props: Record<string, unknown> = {}) {
  const user = userEvent.setup();
  render(<ChatWidget ask={ask} {...props} />);
  return { user, ask };
}
const openChat = (user: ReturnType<typeof userEvent.setup>) => user.click(screen.getByRole("button", { name: /ask the assistant/i }));
const box = () => screen.getByRole("textbox", { name: /your question/i });

describe("ChatWidget", () => {
  it("starts closed and opens a dialog with a welcome message, starters and a focused input", async () => {
    const { user } = setup();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await openChat(user);
    expect(screen.getByRole("dialog", { name: /sharpbuild assistant/i })).toBeInTheDocument();
    expect(screen.getByText(/can answer questions about sharpbuild/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Do you build Shopify stores?" })).toBeInTheDocument();
    expect(box()).toHaveFocus();
    expect(box()).toHaveAttribute("maxlength", String(MAX_LENGTH));
  });

  it("sends a typed question and shows the answer with numbered citation links and source chips", async () => {
    const { user, ask } = setup();
    await openChat(user);
    await user.type(box(), "Do you build Shopify stores?{Enter}");

    expect(ask).toHaveBeenCalledWith("Do you build Shopify stores?", expect.any(AbortSignal));
    expect(await screen.findByText(/yes, sharpbuild builds shopify stores/i)).toBeInTheDocument();

    const cite = screen.getByRole("link", { name: /source 1: e-commerce development/i });
    expect(cite).toHaveAttribute("href", ANSWER.sources[0].url);
    expect(cite).toHaveAttribute("rel", "noopener noreferrer");
    const list = within(screen.getByRole("list", { name: /sources/i }));
    expect(list.getByRole("link", { name: /2\. nothingfishy/i })).toHaveAttribute("href", ANSWER.sources[1].url);
    expect(screen.queryByText("Talk to a human")).not.toBeInTheDocument();
    expect(box()).toHaveValue("");
  });

  it("renders numbered steps and bullets as real lists with working citations inside them", async () => {
    const reply: ChatReply = { ...ANSWER, answer: "Our process:\n1. Discover the goals [1]\n2. Build in steps [2]\n\u2022 Fast\n\u2022 Honest" };
    const { user } = setup(vi.fn().mockResolvedValue(reply));
    await openChat(user);
    await user.type(box(), "Process?{Enter}");
    const step = await screen.findByText(/discover the goals/i);
    expect(step.closest("ol")).not.toBeNull();
    expect(step.closest("li")?.querySelector("a")).toHaveAttribute("href", ANSWER.sources[0].url);
    expect(screen.getByText("Fast").closest("ul")).not.toBeNull();
  });

  it("clicking a starter question sends it and hides the starters", async () => {
    const { user, ask } = setup();
    await openChat(user);
    await user.click(screen.getByRole("button", { name: "How does your process work?" }));
    expect(ask).toHaveBeenCalledWith("How does your process work?", expect.any(AbortSignal));
    await screen.findByText(/yes, sharpbuild builds/i);
    expect(screen.queryByRole("button", { name: "How does your process work?" })).not.toBeInTheDocument();
  });

  it("Enter sends, Shift+Enter adds a new line instead", async () => {
    const { user, ask } = setup();
    await openChat(user);
    await user.type(box(), "line one{Shift>}{Enter}{/Shift}line two");
    expect(ask).not.toHaveBeenCalled();
    expect(box()).toHaveValue("line one\nline two");
    await user.keyboard("{Enter}");
    expect(ask).toHaveBeenCalledWith("line one\nline two", expect.any(AbortSignal));
  });

  it("offers a human contact when the answer is a fallback", async () => {
    const { user } = setup(vi.fn().mockResolvedValue(FALLBACK));
    await openChat(user);
    await user.type(box(), "Weather?{Enter}");
    const human = await screen.findByRole("link", { name: "Talk to a human" });
    expect(human).toHaveAttribute("href", `mailto:${CONTACT_EMAIL}`);
    expect(screen.getByRole("link", { name: "Contact page" })).toHaveAttribute("href", "https://sharpbuild.io/contact");
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();   // a fallback is not an error
  });

  it.each([
    [new ChatApiError("rate_limited", "x", 42), /wait 42 seconds/i],
    [new ChatApiError("network", "x"), /couldn't reach the assistant/i],
    [new ChatApiError("invalid", "x"), /couldn't be sent/i],
    [new ChatApiError("unavailable", "x"), /went wrong on our side/i],
    [new Error("surprise"), /went wrong on our side/i],
  ])("shows a friendly message, Try again and human contact for %s", async (error, message) => {
    const { user } = setup(vi.fn().mockRejectedValue(error));
    await openChat(user);
    await user.type(box(), "Hi{Enter}");
    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Talk to a human" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  });

  it("Try again re-asks the same question without repeating the user's message", async () => {
    const ask = vi.fn().mockRejectedValueOnce(new ChatApiError("network", "x")).mockResolvedValue(ANSWER);
    const { user } = setup(ask);
    await openChat(user);
    await user.type(box(), "Do you build Shopify stores?{Enter}");
    await user.click(await screen.findByRole("button", { name: "Try again" }));
    expect(await screen.findByText(/yes, sharpbuild builds shopify stores/i)).toBeInTheDocument();
    expect(ask).toHaveBeenCalledTimes(2);
    expect(ask.mock.calls[1][0]).toBe("Do you build Shopify stores?");
    expect(screen.getAllByText("Do you build Shopify stores?")).toHaveLength(1);          // one user bubble
    expect(screen.queryByText(/couldn't reach the assistant/i)).not.toBeInTheDocument();  // error bubble replaced
  });

  it("shows a thinking indicator, then a hint when it takes long, and blocks double sending", async () => {
    let resolve!: (r: ChatReply) => void;
    const ask = vi.fn().mockReturnValue(new Promise<ChatReply>((r) => { resolve = r; }));
    const { user } = setup(ask, { slowHintMs: 30 });
    await openChat(user);
    await user.type(box(), "First{Enter}");
    expect(screen.getByRole("status", { name: /thinking/i })).toBeInTheDocument();
    expect(screen.queryByText(/still working/i)).not.toBeInTheDocument();
    expect(await screen.findByText(/still working on it/i)).toBeInTheDocument();
    await user.type(box(), "Second");
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    await user.keyboard("{Enter}");
    expect(ask).toHaveBeenCalledTimes(1);
    resolve(ANSWER);
    await waitFor(() => expect(screen.queryByRole("status", { name: /thinking/i })).not.toBeInTheDocument());
    expect(screen.queryByText(/still working/i)).not.toBeInTheDocument();
  });

  it("does not send blank messages", async () => {
    const { user, ask } = setup();
    await openChat(user);
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    await user.type(box(), "   {Enter}");
    expect(ask).not.toHaveBeenCalled();
  });

  it("New chat clears the conversation and brings the starters back", async () => {
    const { user } = setup();
    await openChat(user);
    expect(screen.queryByRole("button", { name: "Start a new chat" })).not.toBeInTheDocument();
    await user.type(box(), "Hi{Enter}");
    await screen.findByText(/yes, sharpbuild builds/i);
    await user.click(screen.getByRole("button", { name: "Start a new chat" }));
    expect(screen.queryByText(/yes, sharpbuild builds/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Do you build Shopify stores?" })).toBeInTheDocument();
  });

  it("closes on Escape and on the close button, keeping the conversation", async () => {
    const { user } = setup();
    await openChat(user);
    await user.type(box(), "Hi{Enter}");
    await screen.findByText(/yes, sharpbuild builds/i);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await openChat(user);
    expect(screen.getByText(/yes, sharpbuild builds/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Close chat" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("opens itself and asks when the page fires the ask event", async () => {
    const { ask } = setup();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    act(() => { window.dispatchEvent(new CustomEvent(ASK_EVENT, { detail: "Do you build Shopify stores?" })); });
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    await waitFor(() => expect(ask).toHaveBeenCalledWith("Do you build Shopify stores?", expect.any(AbortSignal)));
    act(() => { window.dispatchEvent(new CustomEvent(ASK_EVENT, { detail: 42 })); });   // malformed events are ignored
    expect(ask).toHaveBeenCalledTimes(1);
  });

  it("renders answer text as plain text, never as HTML, and drops citations with no matching source", async () => {
    const evil: ChatReply = { answer: "<img src=x onerror=alert(1)> Hello [9]", sources: [], fallback: false };
    const { user } = setup(vi.fn().mockResolvedValue(evil));
    await openChat(user);
    await user.type(box(), "Hi{Enter}");
    expect(await screen.findByText(/<img src=x onerror=alert\(1\)> Hello/)).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
    expect(screen.queryByRole("link", { name: /source 9/i })).not.toBeInTheDocument();
  });
});
