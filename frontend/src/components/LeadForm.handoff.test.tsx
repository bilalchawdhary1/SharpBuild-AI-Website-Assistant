import {render, screen} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {describe, expect, it, vi} from "vitest";
import LeadForm from "./LeadForm";

const HISTORY = [{role: "user" as const, text: "I want to talk to a human"}];
const consentBox = () => screen.getByRole("checkbox", {name: /agree that sharpbuild may store/i});

function setup(props: Partial<Parameters<typeof LeadForm>[0]> = {}) {
  const submit = vi.fn().mockResolvedValue(undefined);
  const user = userEvent.setup();
  render(<LeadForm history={HISTORY} kind='handoff' submit={submit} {...props} />);
  return {user, submit};
}
const fill = async (user: ReturnType<typeof userEvent.setup>) => {
  await user.type(screen.getByLabelText(/your name/i), "Ali");
  await user.type(screen.getByLabelText(/^email/i), "ali@example.com");
  await user.click(consentBox());
};

describe("LeadForm in handoff mode", () => {
  it("uses handoff wording", () => {
    setup();
    expect(screen.getByText(/a person from the sharpbuild team will get back to you/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/how can we help/i)).toBeInTheDocument();
  });

  it("sends kind=handoff and does not share the chat unless asked", async () => {
    const {user, submit} = setup();
    await fill(user);
    await user.click(screen.getByRole("button", {name: /send my details/i}));
    expect(submit).toHaveBeenCalledWith(expect.objectContaining({kind: "handoff", shareChat: false}));
    expect(await screen.findByRole("status")).toHaveTextContent(/a member of the sharpbuild team/i);
  });

  it("shares the chat only after the separate box is ticked", async () => {
    const {user, submit} = setup();
    await fill(user);
    expect(screen.getByRole("checkbox", {name: /share my recent messages/i})).not.toBeChecked();
    await user.click(screen.getByRole("checkbox", {name: /share my recent messages/i}));
    await user.click(screen.getByRole("button", {name: /send my details/i}));
    expect(submit).toHaveBeenCalledWith(expect.objectContaining({shareChat: true}));
  });

  it("ticking only the share box is not consent to store the details", async () => {
    const {user, submit} = setup();
    await user.type(screen.getByLabelText(/your name/i), "Ali");
    await user.type(screen.getByLabelText(/^email/i), "ali@example.com");
    await user.click(screen.getByRole("checkbox", {name: /share my recent messages/i}));
    await user.click(screen.getByRole("button", {name: /send my details/i}));
    expect(submit).not.toHaveBeenCalled();
    expect(screen.getByText(/tick the box/i)).toBeInTheDocument();
  });

  it("offers no share box when the visitor has said nothing, or in sales mode", () => {
    const {unmount} = render(<LeadForm history={[]} kind='handoff' />);
    expect(screen.queryByRole("checkbox", {name: /share my recent messages/i})).not.toBeInTheDocument();
    unmount();
    render(<LeadForm history={HISTORY} kind='sales' />);
    expect(screen.queryByRole("checkbox", {name: /share my recent messages/i})).not.toBeInTheDocument();
  });
});
