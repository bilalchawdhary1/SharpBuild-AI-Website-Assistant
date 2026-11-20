import {fireEvent, render, screen, waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {describe, expect, it, vi} from "vitest";
import type {ChatReply, StreamHandlers} from "@/lib/chatApi";
import ChatWidget from "./ChatWidget";

type AskFn = (message: string, handlers?: StreamHandlers) => Promise<ChatReply>;
const reply = (extra: Partial<ChatReply> = {}): ChatReply => ({
  answer: "SharpBuild builds apps.",
  sources: [],
  fallback: false,
  ...extra,
});
const launcher = () => screen.getByRole("button", {name: /ask the assistant|hide chat/i});
const questionBox = () => screen.getByRole("textbox", {name: /your question/i});

function setup(ask: AskFn = async () => reply()) {
  const user = userEvent.setup();
  render(<ChatWidget ask={vi.fn<AskFn>(ask)} submitLead={vi.fn()} tickMs={1} defaultOpen />);
  return user;
}

describe("focus management", () => {
  it("Escape closes the chat and puts focus back on the launcher", async () => {
    const user = setup();
    await user.click(questionBox());
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(launcher()).toHaveFocus();
  });

  it("the Close button does the same", async () => {
    const user = setup();
    await user.click(screen.getByRole("button", {name: /close chat/i}));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(launcher()).toHaveFocus();
  });

  it("reopening focuses the question box", async () => {
    const user = setup();
    await user.keyboard("{Escape}");
    await user.click(launcher());
    expect(questionBox()).toHaveFocus();
  });
});

describe("contact form accessibility", () => {
  async function openForm(user: ReturnType<typeof userEvent.setup>) {
    await user.type(questionBox(), "weather in Paris?{Enter}");
    await user.click(await screen.findByRole("button", {name: /leave your details/i}));
  }
  const fallback = () => setup(async () => reply({fallback: true}));

  it("moves focus to the first field when the form opens", async () => {
    const user = fallback();
    await openForm(user);
    expect(screen.getByLabelText(/your name/i)).toHaveFocus();
  });

  it("an invalid submit focuses the first problem and links it to its message", async () => {
    const user = fallback();
    await openForm(user);
    const send = () => user.click(screen.getByRole("button", {name: /send my details/i}));

    await send();
    const name = screen.getByLabelText(/your name/i);
    expect(name).toHaveFocus();
    expect(name).toHaveAttribute("aria-invalid", "true");
    expect(name.getAttribute("aria-describedby")).toBe(screen.getByText(/enter your name/i).id);

    await user.type(name, "Ali");
    await send();
    expect(screen.getByLabelText(/^email/i)).toHaveFocus();

    await user.type(screen.getByLabelText(/^email/i), "ali@example.com");
    await send();
    expect(screen.getByRole("checkbox", {name: /agree that sharpbuild may store/i})).toHaveFocus();
  });

  it("Escape does not close the chat while the form holds typed details", async () => {
    const user = fallback();
    await openForm(user);
    await user.type(screen.getByLabelText(/your name/i), "Al");
    await user.keyboard("{Escape}");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByLabelText(/your name/i)).toHaveValue("Al");
  });

  it("Escape still closes the chat when the form is untouched", async () => {
    const user = fallback();
    await openForm(user);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("Cancel returns focus to the question box", async () => {
    const user = fallback();
    await openForm(user);
    await user.click(screen.getByRole("button", {name: /cancel/i}));
    expect(questionBox()).toHaveFocus();
  });
});

describe("conversation scrolling", () => {
  const define = (el: HTMLElement, props: Record<string, number>) =>
    Object.entries(props).forEach(([key, value]) =>
      Object.defineProperty(el, key, {configurable: true, writable: true, value}),
    );

  async function streamWhileScrolled(scrollTop: number) {
    let release: () => void = () => {};
    const gate = new Promise<void>(resolve => (release = resolve));
    const user = setup(async (_q, handlers) => {
      handlers?.onDelta?.("First part. ");
      await gate;
      handlers?.onDelta?.("Second part.");
      return reply({answer: "First part. Second part."});
    });
    await user.type(questionBox(), "tell me more{Enter}");
    await screen.findByText(/first part/i);

    const log = screen.getByRole("log");
    define(log, {scrollHeight: 1000, clientHeight: 300, scrollTop});
    fireEvent.scroll(log); // the visitor moves the scrollbar while the answer is still being written
    release();
    await screen.findByText(/second part/i);
    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
    return log;
  }

  it("does not pull the visitor down while they read earlier messages", async () => {
    const log = await streamWhileScrolled(0);
    expect(log.scrollTop).toBe(0);
  });

  it("keeps following the answer when they are at the bottom", async () => {
    const log = await streamWhileScrolled(700);
    expect(log.scrollTop).toBe(1000);
  });
});
