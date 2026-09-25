import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderIntl } from "@/test/intl";

import { ChannelsByLevelEditor, effectiveChannels } from "./ChannelsByLevelEditor";

describe("ChannelsByLevelEditor", () => {
  it("prefills the M35 defaults and shows the SMS hint", () => {
    renderIntl(<ChannelsByLevelEditor value={null} canManage onSave={async () => true} />);
    expect(screen.getByLabelText("Stufe 1: Intern")).toBeChecked();
    expect(screen.getByLabelText("Stufe 1: E-Mail")).not.toBeChecked();
    expect(screen.getByLabelText("Stufe 2: E-Mail")).toBeChecked();
    expect(screen.getByLabelText("Stufe 2: SMS")).not.toBeChecked();
    expect(screen.getByLabelText("Stufe 3: SMS")).toBeChecked();
    expect(screen.getByText(/SMS-Gateway aktiv/)).toBeInTheDocument();
  });

  it("saves toggled channels and keeps other configured levels", async () => {
    const onSave = vi.fn(async () => true);
    renderIntl(
      <ChannelsByLevelEditor value={{ "1": ["email"], "0": ["internal"] }} canManage onSave={onSave} />,
    );
    expect(screen.getByLabelText("Stufe 1: E-Mail")).toBeChecked();
    expect(screen.getByLabelText("Stufe 1: Intern")).not.toBeChecked();
    await userEvent.click(screen.getByLabelText("Stufe 1: SMS"));
    await userEvent.click(screen.getByLabelText("Stufe 2: Intern"));
    await userEvent.click(screen.getByRole("button", { name: "Kanäle speichern" }));
    expect(onSave).toHaveBeenCalledWith({
      "0": ["internal"],
      "1": ["email", "sms"],
      "2": ["email"],
      "3": ["internal", "email", "sms"],
    });
    expect(await screen.findByText("Gespeichert")).toBeInTheDocument();
  });

  it("is read only without manage permission", () => {
    renderIntl(<ChannelsByLevelEditor value={null} canManage={false} onSave={async () => true} />);
    expect(screen.getByLabelText("Stufe 1: Intern")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Kanäle speichern" })).toBeNull();
  });

  it("falls back to defaults per level", () => {
    expect(effectiveChannels({ "2": [] })).toEqual({ "1": ["internal"], "2": [], "3": ["internal", "email", "sms"] });
  });
});
