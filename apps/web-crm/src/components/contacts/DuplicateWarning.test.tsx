import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderIntl } from "@/test/intl";

import { DuplicateWarning, type DuplicateCandidate } from "./DuplicateWarning";

const candidate: DuplicateCandidate = {
  contact: {
    id: "01920000-0000-7000-8000-000000000001",
    kind: "person",
    display_name: "Erika Mustermann",
    city: "Hilden",
    primary_email: "erika@example.org",
    primary_phone: null,
    tags: [],
    types: [],
    roles: [],
    blocked: false,
    deleted: false,
    completeness: "complete",
  },
  score: 0.95,
  reasons: ["gleiche E-Mail-Adresse", "ähnlicher Name"],
};

describe("DuplicateWarning", () => {
  it("lists candidates with score, reasons and a link to open them", () => {
    renderIntl(
      <DuplicateWarning
        candidates={[candidate]}
        onSaveAnyway={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(
      screen.getByRole("heading", { name: "Mögliche Dubletten" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Erika Mustermann")).toBeInTheDocument();
    expect(screen.getByText("95 %")).toBeInTheDocument();
    expect(
      screen.getByText("gleiche E-Mail-Adresse, ähnlicher Name"),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Öffnen" })).toHaveAttribute(
      "href",
      "/kontakte/01920000-0000-7000-8000-000000000001",
    );
  });

  it("offers save anyway and cancel", async () => {
    const save = vi.fn();
    const cancel = vi.fn();
    renderIntl(
      <DuplicateWarning
        candidates={[candidate]}
        onSaveAnyway={save}
        onCancel={cancel}
      />,
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Trotzdem speichern" }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Abbrechen" }));
    expect(save).toHaveBeenCalledOnce();
    expect(cancel).toHaveBeenCalledOnce();
  });
});
