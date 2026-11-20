import {render, screen, within} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {describe, expect, it, vi} from "vitest";
import type {ChatReply, StreamHandlers} from "@/lib/chatApi";
import ChatWidget from "./ChatWidget";

type AskFn = (message: string, handlers?: StreamHandlers) => Promise<ChatReply>;
const handoffReply: ChatReply = {
  answer: "Of course, I'll connect you with the SharpBuild team.",
  sources: [],
  fallback: true,
  handoff: true,
};

async function setup(replies: ChatReply[], submitLead = vi.fn().mockResolvedValue(undefined)) {
  const user = userEvent.setup();
  const queue = [...replies];
  const ask = vi.fn<AskFn>(async () => queue.shift() as ChatReply);
  render(<ChatWidget ask={ask} submitLead={submitLead} tickMs={1} />);
  await user.click(screen.getByRole("button", {name: /ask the assistant/i}));
  const send = async (text: string) =>
    user.type(screen.getByRole("textbox", {name: /your question/i}), `${text}{Enter}`);
  return {user, send, submitLead};
}

describe("ChatWidget human handoff", () => {
  it("opens the contact form by itself when the visitor asks for a person", async () => {
    const {send} = await setup([handoffReply]);
    await send("I want to talk to a human");
    expect(await screen.findByRole("form", {name: /leave your details/i})).toBeInTheDocument();
    expect(screen.getByText(/a person from the sharpbuild team/i)).toBeInTheDocument();
  });

  it("submits it as a handoff, sharing the chat only when ticked", async () => {
    const {user, send, submitLead} = await setup([handoffReply]);
    await send("I want to talk to a human");
    const form = await screen.findByRole("form", {name: /leave your details/i});
    await user.type(within(form).getByLabelText(/your name/i), "Ali");
    await user.type(within(form).getByLabelText(/^email/i), "ali@example.com");
    await user.click(within(form).getByRole("checkbox", {name: /agree that sharpbuild may store/i}));
    await user.click(within(form).getByRole("checkbox", {name: /share my recent messages/i}));
    await user.click(within(form).getByRole("button", {name: /send my details/i}));
    expect(submitLead).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: "handoff",
        shareChat: true,
        history: expect.arrayContaining([expect.objectContaining({role: "user", text: "I want to talk to a human"})]),
      }),
    );
    expect(await screen.findByText(/a member of the sharpbuild team/i)).toBeInTheDocument();
  });

  it("does not reopen the form once details were sent", async () => {
    const {user, send} = await setup([handoffReply, handoffReply]);
    await send("I want to talk to a human");
    const form = await screen.findByRole("form", {name: /leave your details/i});
    await user.type(within(form).getByLabelText(/your name/i), "Ali");
    await user.type(within(form).getByLabelText(/^email/i), "ali@example.com");
    await user.click(within(form).getByRole("checkbox", {name: /agree that sharpbuild may store/i}));
    await user.click(within(form).getByRole("button", {name: /send my details/i}));
    await screen.findByText(/a member of the sharpbuild team/i);

    await send("can I speak with a person again?");
    await screen.findAllByText(/connect you with the sharpbuild team/i);
    expect(screen.queryByRole("form")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", {name: /leave your details/i})).not.toBeInTheDocument();
  });

  it("a normal fallback still waits for the visitor to ask for the form", async () => {
    const {send} = await setup([{answer: "No info.", sources: [], fallback: true}]);
    await send("weather in Paris?");
    expect(await screen.findByRole("button", {name: /leave your details/i})).toBeInTheDocument();
    expect(screen.queryByRole("form", {name: /leave your details/i})).not.toBeInTheDocument();
  });
});
