import {act, render, screen, waitFor, within} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {afterEach, describe, expect, it, vi} from "vitest";
import {ChatApiError, type ChatReply, type StreamHandlers} from "@/lib/chatApi";
import {ASK_EVENT} from "@/lib/events";
import ChatWidget, {CONTACT_EMAIL, MAX_LENGTH} from "./ChatWidget";

const ANSWER: ChatReply = {
  answer: "Yes, SharpBuild builds Shopify stores.",
  sources: [
    {
      url: "https://sharpbuild.io/services/ecommerce-development",
      title: "E-commerce Development",
      section: "",
    },
    {
      url: "https://sharpbuild.io/portfolio/nothingfishy-shopify-store",
      title: "NothingFishy",
      section: "",
    },
  ],
  fallback: false,
};
const FALLBACK: ChatReply = {
  answer: "I couldn't find that information.",
  sources: [],
  fallback: true,
};

type AskFn = (message: string, handlers?: StreamHandlers) => Promise<ChatReply>;
const replyWith = (reply: ChatReply, pieces: string[] = []) =>
  vi.fn<AskFn>(async (_message, handlers) => {
    pieces.forEach(p => handlers?.onDelta?.(p));
    return reply;
  });

function setup(
  ask: AskFn = replyWith(ANSWER),
  props: Record<string, unknown> = {},
) {
  const user = userEvent.setup();
  render(<ChatWidget ask={ask} tickMs={1} {...props} />);
  return {user, ask};
}
const openChat = (user: ReturnType<typeof userEvent.setup>) =>
  user.click(screen.getByRole("button", {name: /ask the assistant/i}));
const box = () => screen.getByRole("textbox", {name: /your question/i});
const handlers = () =>
  expect.objectContaining({
    signal: expect.any(AbortSignal),
    onDelta: expect.any(Function),
  });

afterEach(() => {
  vi.useRealTimers();
});

describe("ChatWidget", () => {
  it("starts closed and opens a dialog with a welcome message, starters and a focused input", async () => {
    const {user} = setup();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await openChat(user);
    expect(
      screen.getByRole("dialog", {name: /sharpbuild assistant/i}),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/can answer questions about sharpbuild/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", {name: "Do you build Shopify stores?"}),
    ).toBeInTheDocument();
    expect(box()).toHaveFocus();
    expect(box()).toHaveAttribute("maxlength", String(MAX_LENGTH));
  });

  it("shows the answer and source chips once it is fully written, without any [1] markers", async () => {
    const {user, ask} = setup();
    await openChat(user);
    await user.type(box(), "Do you build Shopify stores?{Enter}");
    expect(ask).toHaveBeenCalledWith(
      "Do you build Shopify stores?",
      handlers(),
    );

    expect(
      await screen.findByText("Yes, SharpBuild builds Shopify stores."),
    ).toBeInTheDocument();
    const list = await screen.findByRole("list", {name: /sources/i});
    expect(
      within(list).getByRole("link", {name: /1\. e-commerce development/i}),
    ).toHaveAttribute("href", ANSWER.sources[0].url);
    expect(
      within(list).getByRole("link", {name: /2\. nothingfishy/i}),
    ).toHaveAttribute("rel", "noopener noreferrer");
    expect(document.body.textContent).not.toMatch(/\[\d+\]/);
    expect(screen.queryByText("Talk to a human")).not.toBeInTheDocument();
    expect(box()).toHaveValue("");
  });

  it("renders bold terms, numbered steps and bullets as real formatting", async () => {
    const reply: ChatReply = {
      ...ANSWER,
      answer:
        "Our process:\n1. **Discover**: learn the goals\n2. **Build**: ship in steps\n\u2022 **Fast**\n\u2022 Honest",
    };
    const {user} = setup(replyWith(reply));
    await openChat(user);
    await user.type(box(), "Process?{Enter}");
    const discover = await screen.findByText("Discover");
    expect(discover.tagName).toBe("STRONG");
    expect(discover.closest("ol")).not.toBeNull();
    expect((await screen.findByText("Fast")).closest("ul")).not.toBeNull();
    expect(document.body.textContent).not.toContain("**");
  });

  it("hides citation markers that an older backend might still send", async () => {
    const {user} = setup(replyWith({...ANSWER, answer: "Yes [1] we do [2]."}));
    await openChat(user);
    await user.type(box(), "Hi{Enter}");
    expect(await screen.findByText("Yes we do.")).toBeInTheDocument();
  });

  it("shows text while it is still being written, keeps sources back, and offers Stop", async () => {
    let release!: () => void;
    const finish = new Promise<void>(r => {
      release = r;
    });
    const ask = vi.fn<AskFn>(async (_m, h) => {
      h?.onDelta?.("Hello ");
      h?.onDelta?.("there");
      await finish;
      return {answer: "Hello there", sources: ANSWER.sources, fallback: false};
    });
    const {user} = setup(ask);
    await openChat(user);
    await user.type(box(), "Hi{Enter}");

    expect(await screen.findByText("Hello there")).toBeInTheDocument(); // visible before the request ends
    expect(
      screen.queryByRole("status", {name: /thinking/i}),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", {name: /stop generating/i}),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", {name: "Send"}),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("list", {name: /sources/i}),
    ).not.toBeInTheDocument();

    release();
    expect(
      await screen.findByRole("list", {name: /sources/i}),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", {name: "Send"})).toBeInTheDocument();
  });

  it("types out an answer that arrives all at once, a few characters at a time", async () => {
    vi.useFakeTimers();
    const ask = replyWith({
      answer: "A".repeat(60),
      sources: [],
      fallback: false,
    });
    render(<ChatWidget ask={ask} defaultOpen tickMs={50} />);
    act(() => {
      window.dispatchEvent(new CustomEvent(ASK_EVENT, {detail: "Hi"}));
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    }); // let the answer arrive
    await act(async () => {
      await vi.advanceTimersByTimeAsync(50);
    }); // one reveal step
    const visible = screen.getByText(/^A+$/).textContent ?? "";
    expect(visible.length).toBeGreaterThan(0);
    expect(visible.length).toBeLessThan(60); // partially revealed
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(screen.getByText("A".repeat(60))).toBeInTheDocument();
  });

  it("Stop keeps the words already shown, shows no error, and lets the visitor ask again", async () => {
    const ask = vi.fn<AskFn>(
      (_m, h) =>
        new Promise<ChatReply>((_resolve, reject) => {
          h?.onDelta?.("Partial answer text");
          h?.signal?.addEventListener("abort", () =>
            reject(new DOMException("aborted", "AbortError")),
          );
        }),
    );
    const {user} = setup(ask);
    await openChat(user);
    await user.type(box(), "Hi{Enter}");
    await screen.findByText("Partial answer text");
    await user.click(screen.getByRole("button", {name: /stop generating/i}));
    expect(screen.getByText("Partial answer text")).toBeInTheDocument();
    expect(screen.queryByText(/went wrong/i)).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", {name: "Try again"}),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", {name: "Send"})).toBeInTheDocument();
  });

  it("a failure halfway keeps the partial text, says it was cut short, and offers Try again", async () => {
    const ask = vi.fn<AskFn>(async (_m, h) => {
      h?.onDelta?.("Half an answer");
      throw new ChatApiError("unavailable", "x");
    });
    const {user} = setup(ask);
    await openChat(user);
    await user.type(box(), "Hi{Enter}");
    expect(await screen.findByText("Half an answer")).toBeInTheDocument();
    expect(await screen.findByText(/cut short/i)).toBeInTheDocument();
    expect(screen.getByRole("button", {name: "Try again"})).toBeInTheDocument();
    expect(
      screen.getByRole("link", {name: "Talk to a human"}),
    ).toBeInTheDocument();
  });

  it("clicking a starter question sends it and hides the starters", async () => {
    const {user, ask} = setup();
    await openChat(user);
    await user.click(
      screen.getByRole("button", {name: "How does your process work?"}),
    );
    expect(ask).toHaveBeenCalledWith("How does your process work?", handlers());
    await screen.findByText(/yes, sharpbuild builds/i);
    expect(
      screen.queryByRole("button", {name: "How does your process work?"}),
    ).not.toBeInTheDocument();
  });

  it("Enter sends, Shift+Enter adds a new line instead", async () => {
    const {user, ask} = setup();
    await openChat(user);
    await user.type(box(), "line one{Shift>}{Enter}{/Shift}line two");
    expect(ask).not.toHaveBeenCalled();
    expect(box()).toHaveValue("line one\nline two");
    await user.keyboard("{Enter}");
    expect(ask).toHaveBeenCalledWith("line one\nline two", handlers());
  });

  it("offers a human contact after a fallback answer, but not while it is still being typed", async () => {
    const {user} = setup(replyWith(FALLBACK));
    await openChat(user);
    await user.type(box(), "Weather?{Enter}");
    const human = await screen.findByRole("link", {name: "Talk to a human"});
    expect(human).toHaveAttribute("href", `mailto:${CONTACT_EMAIL}`);
    expect(screen.getByRole("link", {name: "Contact page"})).toHaveAttribute(
      "href",
      "https://sharpbuild.io/contact",
    );
    expect(
      screen.queryByRole("button", {name: "Try again"}),
    ).not.toBeInTheDocument(); // a fallback is not an error
  });

  it.each([
    [new ChatApiError("rate_limited", "x", 42), /wait 42 seconds/i],
    [new ChatApiError("network", "x"), /couldn't reach the assistant/i],
    [new ChatApiError("invalid", "x"), /couldn't be sent/i],
    [new ChatApiError("unavailable", "x"), /went wrong on our side/i],
    [new Error("surprise"), /went wrong on our side/i],
  ])(
    "shows a friendly message, Try again and human contact for %s",
    async (error, message) => {
      const {user} = setup(vi.fn<AskFn>().mockRejectedValue(error));
      await openChat(user);
      await user.type(box(), "Hi{Enter}");
      expect(await screen.findByText(message)).toBeInTheDocument();
      expect(
        await screen.findByRole("button", {name: "Try again"}),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("link", {name: "Talk to a human"}),
      ).toBeInTheDocument();
    },
  );

  it("Try again re-asks the same question without repeating the user's message", async () => {
    const ask = vi
      .fn<AskFn>()
      .mockRejectedValueOnce(new ChatApiError("network", "x"))
      .mockImplementation(async () => ANSWER);
    const {user} = setup(ask);
    await openChat(user);
    await user.type(box(), "Do you build Shopify stores?{Enter}");
    await user.click(await screen.findByRole("button", {name: "Try again"}));
    expect(
      await screen.findByText("Yes, SharpBuild builds Shopify stores."),
    ).toBeInTheDocument();
    expect(ask).toHaveBeenCalledTimes(2);
    expect(ask.mock.calls[1][0]).toBe("Do you build Shopify stores?");
    expect(screen.getAllByText("Do you build Shopify stores?")).toHaveLength(1);
    expect(
      screen.queryByText(/couldn't reach the assistant/i),
    ).not.toBeInTheDocument();
  });

  it("shows a thinking indicator, then a hint when nothing arrives for a while, and blocks double sending", async () => {
    let resolve!: (r: ChatReply) => void;
    const ask = vi.fn<AskFn>(
      () =>
        new Promise<ChatReply>(r => {
          resolve = r;
        }),
    );
    const {user} = setup(ask, {slowHintMs: 30});
    await openChat(user);
    await user.type(box(), "First{Enter}");
    expect(screen.getByRole("status", {name: /thinking/i})).toBeInTheDocument();
    expect(screen.queryByText(/still working/i)).not.toBeInTheDocument();
    expect(await screen.findByText(/still working on it/i)).toBeInTheDocument();
    await user.type(box(), "Second{Enter}");
    expect(ask).toHaveBeenCalledTimes(1);
    resolve(ANSWER);
    await waitFor(() =>
      expect(
        screen.queryByRole("status", {name: /thinking/i}),
      ).not.toBeInTheDocument(),
    );
    expect(screen.queryByText(/still working/i)).not.toBeInTheDocument();
  });

  it("does not send blank messages", async () => {
    const {user, ask} = setup();
    await openChat(user);
    expect(screen.getByRole("button", {name: "Send"})).toBeDisabled();
    await user.type(box(), "   {Enter}");
    expect(ask).not.toHaveBeenCalled();
  });

  it("New chat clears the conversation and brings the starters back", async () => {
    const {user} = setup();
    await openChat(user);
    expect(
      screen.queryByRole("button", {name: "Start a new chat"}),
    ).not.toBeInTheDocument();
    await user.type(box(), "Hi{Enter}");
    await screen.findByText(/yes, sharpbuild builds/i);
    await user.click(screen.getByRole("button", {name: "Start a new chat"}));
    expect(
      screen.queryByText(/yes, sharpbuild builds/i),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", {name: "Do you build Shopify stores?"}),
    ).toBeInTheDocument();
  });

  it("closes on Escape and on the close button, keeping the conversation", async () => {
    const {user} = setup();
    await openChat(user);
    await user.type(box(), "Hi{Enter}");
    await screen.findByText(/yes, sharpbuild builds/i);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await openChat(user);
    expect(screen.getByText(/yes, sharpbuild builds/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", {name: "Close chat"}));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("opens itself and asks when the page fires the ask event", async () => {
    const {ask} = setup();
    act(() => {
      window.dispatchEvent(
        new CustomEvent(ASK_EVENT, {detail: "Do you build Shopify stores?"}),
      );
    });
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    await waitFor(() =>
      expect(ask).toHaveBeenCalledWith(
        "Do you build Shopify stores?",
        handlers(),
      ),
    );
    await screen.findByText(/yes, sharpbuild builds/i);
    act(() => {
      window.dispatchEvent(new CustomEvent(ASK_EVENT, {detail: 42}));
    }); // malformed events are ignored
    expect(ask).toHaveBeenCalledTimes(1);
  });

  it("renders answer text as plain text, never as HTML", async () => {
    const evil: ChatReply = {
      answer: "<img src=x onerror=alert(1)> Hello",
      sources: [],
      fallback: false,
    };
    const {user} = setup(replyWith(evil));
    await openChat(user);
    await user.type(box(), "Hi{Enter}");
    expect(
      await screen.findByText(/<img src=x onerror=alert\(1\)> Hello/),
    ).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
  });
});
