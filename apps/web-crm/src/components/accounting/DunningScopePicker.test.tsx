import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderIntl } from "@/test/intl";

import { DunningScopePicker } from "./DunningScopePicker";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

const props = [{ id: "p 1", number: "100", name: "Musterstraße" }];

describe("DunningScopePicker", () => {
  beforeEach(() => push.mockClear());

  it("routes to the property scope with an encoded id", async () => {
    renderIntl(<DunningScopePicker properties={props} selected={null} />);
    await userEvent.selectOptions(screen.getByRole("combobox"), "p 1");
    expect(push).toHaveBeenCalledWith("/buchhaltung/mahnwesen/einstellungen?objekt=p%201");
  });

  it("routes back to the tenant default", async () => {
    renderIntl(<DunningScopePicker properties={props} selected="p 1" />);
    await userEvent.selectOptions(screen.getByRole("combobox"), "");
    expect(push).toHaveBeenCalledWith("/buchhaltung/mahnwesen/einstellungen");
  });
});
