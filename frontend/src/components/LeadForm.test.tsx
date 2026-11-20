import {render, screen, waitFor} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {describe, expect, it, vi} from "vitest";
import {ChatApiError} from "@/lib/chatApi";
import LeadForm from "./LeadForm";

const HISTORY = [{role: "user" as const, text: "I need an app"}];

function setup(submit = vi.fn().mockResolvedValue(undefined)) {
  const onSent = vi.fn();
  const onCancel = vi.fn();
  const user = userEvent.setup();
  const view = render(<LeadForm history={HISTORY} submit={submit} onSent={onSent} onCancel={onCancel} />);
  return {user, submit, onSent, onCancel, view};
}
const fill = async (user: ReturnType<typeof userEvent.setup>) => {
  await user.type(screen.getByLabelText(/your name/i), "Ali Khan");
  await user.type(screen.getByLabelText(/^email/i), "ali@example.com");
};
const consentBox = () => screen.getByRole("checkbox");

describe("LeadForm", () => {
  it("does not submit without name, a valid email and consent, and says what is missing", async () => {
    const {user, submit} = setup();
    await user.click(screen.getByRole("button", {name: /send my details/i}));
    expect(submit).not.toHaveBeenCalled();
    expect(screen.getByText(/enter your name/i)).toBeInTheDocument();
    expect(screen.getByText(/valid email/i)).toBeInTheDocument();
    expect(screen.getByText(/tick the box/i)).toBeInTheDocument();
  });

  it("rejects an email without consent even when the rest is valid", async () => {
    const {user, submit} = setup();
    await fill(user);
    await user.click(screen.getByRole("button", {name: /send my details/i}));
    expect(submit).not.toHaveBeenCalled();
    expect(screen.getByText(/tick the box/i)).toBeInTheDocument();
  });

  it("submits the details with consent and history, then shows a thank-you", async () => {
    const {user, submit, onSent} = setup();
    await fill(user);
    await user.type(screen.getByLabelText(/phone/i), "0300-1234567");
    await user.click(consentBox());
    await user.click(screen.getByRole("button", {name: /send my details/i}));
    expect(submit).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "Ali Khan",
        email: "ali@example.com",
        phone: "0300-1234567",
        consent: true,
        history: HISTORY,
        website: "",
      }),
    );
    expect(await screen.findByRole("status")).toHaveTextContent(/thanks/i);
    expect(onSent).toHaveBeenCalledTimes(1);
  });

  it("forwards a filled honeypot so the server can drop the submission", async () => {
    const {user, submit, view} = setup();
    await fill(user);
    await user.click(consentBox());
    const trap = view.container.querySelector('input[name="website"]') as HTMLInputElement;
    expect(trap).toHaveAttribute("aria-hidden", "true");
    await user.type(trap, "http://spam.example");
    await user.click(screen.getByRole("button", {name: /send my details/i}));
    expect(submit).toHaveBeenCalledWith(expect.objectContaining({website: "http://spam.example"}));
  });

  it("shows a friendly error and keeps the form when saving fails", async () => {
    const submit = vi.fn().mockRejectedValue(new ChatApiError("rate_limited", "x", 30));
    const {user, onSent} = setup(submit);
    await fill(user);
    await user.click(consentBox());
    await user.click(screen.getByRole("button", {name: /send my details/i}));
    expect(await screen.findByText(/too many attempts/i)).toBeInTheDocument();
    expect(onSent).not.toHaveBeenCalled();
    expect(screen.getByRole("button", {name: /send my details/i})).toBeEnabled(); // can retry
  });

  it("falls back to the contact email for an unexpected failure", async () => {
    const {user} = setup(vi.fn().mockRejectedValue(new Error("boom")));
    await fill(user);
    await user.click(consentBox());
    await user.click(screen.getByRole("button", {name: /send my details/i}));
    expect(await screen.findByText(/hello@sharpbuild\.io/i)).toBeInTheDocument();
  });

  it("blocks a second click while sending", async () => {
    let finish: () => void = () => {};
    const submit = vi.fn(() => new Promise<void>(resolve => (finish = resolve)));
    const {user} = setup(submit);
    await fill(user);
    await user.click(consentBox());
    const send = screen.getByRole("button", {name: /send my details/i});
    await user.click(send);
    await waitFor(() => expect(screen.getByRole("button", {name: /sending/i})).toBeDisabled());
    await user.click(screen.getByRole("button", {name: /sending/i}));
    expect(submit).toHaveBeenCalledTimes(1);
    finish();
  });

  it("cancel calls onCancel", async () => {
    const {user, onCancel} = setup();
    await user.click(screen.getByRole("button", {name: /cancel/i}));
    expect(onCancel).toHaveBeenCalled();
  });
});
