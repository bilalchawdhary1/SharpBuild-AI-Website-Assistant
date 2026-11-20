import {render, screen, within} from "@testing-library/react";
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

async function ask(r: ChatReply, submitLead = vi.fn().mockResolvedValue(undefined)) {
  const user = userEvent.setup();
  const fn = vi.fn<AskFn>(async () => r);
  render(<ChatWidget ask={fn} submitLead={submitLead} tickMs={1} />);
  await user.click(screen.getByRole("button", {name: /ask the assistant/i}));
  await user.type(screen.getByRole("textbox", {name: /your question/i}), "I need an app{Enter}");
  return {user, submitLead};
}

describe("ChatWidget lead form", () => {
  it("offers the form when the backend says contact details are the next step", async () => {
    await ask(reply({lead: {score: "warm", nextField: "contact"}}));
    expect(await screen.findByRole("button", {name: /leave your details/i})).toBeInTheDocument();
  });

  it("offers the form after a fallback answer too", async () => {
    await ask(reply({fallback: true}));
    expect(await screen.findByRole("button", {name: /leave your details/i})).toBeInTheDocument();
  });

  it("does not offer it for a plain answer or while another detail is still missing", async () => {
    await ask(reply({lead: {score: "cold", nextField: "need"}}));
    await screen.findByText(/builds apps/i);
    expect(screen.queryByRole("button", {name: /leave your details/i})).not.toBeInTheDocument();
    expect(screen.queryByText("Talk to a human")).not.toBeInTheDocument();
  });

  it("opens the form, sends it with the conversation, and stops offering it afterwards", async () => {
    const {user, submitLead} = await ask(reply({lead: {score: "warm", nextField: "contact"}}));
    await user.click(await screen.findByRole("button", {name: /leave your details/i}));
    const form = screen.getByRole("form", {name: /leave your details/i});
    await user.type(within(form).getByLabelText(/your name/i), "Ali");
    await user.type(within(form).getByLabelText(/^email/i), "ali@example.com");
    await user.click(within(form).getByRole("checkbox"));
    await user.click(within(form).getByRole("button", {name: /send my details/i}));
    expect(submitLead).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "Ali",
        consent: true,
        history: expect.arrayContaining([expect.objectContaining({role: "user", text: "I need an app"})]),
      }),
    );
    expect(await screen.findByText(/team will contact you/i)).toBeInTheDocument();
  });

  it("the footnote says contact details go only through the form", async () => {
    await ask(reply());
    expect(await screen.findByText(/only through the optional form/i)).toBeInTheDocument();
  });
});
