import { screen } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { ContactActions } from "./ContactActions";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh: vi.fn(), back: vi.fn() }) }));

const ID = "01920000-0000-7000-8000-00000000000a";

describe("ContactActions delete gating (rule Löschen nur Administrator, docs/rules/M2-07.md)", () => {
  it("shows the delete button when the user holds contacts:delete", () => {
    renderIntl(<ContactActions id={ID} name="Erika Mustermann" canDelete={true} />);
    expect(screen.getByRole("button", { name: /löschen/i })).toBeInTheDocument();
  });

  it("hides the delete button when the user lacks contacts:delete", () => {
    renderIntl(<ContactActions id={ID} name="Erika Mustermann" canDelete={false} />);
    expect(screen.queryByRole("button", { name: /löschen/i })).not.toBeInTheDocument();
  });
});
