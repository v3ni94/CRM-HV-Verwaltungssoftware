import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { InspectionRequestCreate } from "./InspectionRequests";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push }) }));
const ID = "0192abcd-0000-7000-8000-000000000061";

describe("InspectionRequestCreate (A61, review 26.09.2026)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("tells the user step by step what is missing before the request can be recorded", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input) =>
      String(input).startsWith("/api/bff/contacts?") ? jsonResponse({ items: [{ id: ID, display_name: "Erika Mustermann" }] }) : jsonResponse({ id: ID }, 201),
    );
    renderIntl(<InspectionRequestCreate legalEntityId="le1" basePath="/weg/p" />);
    expect(screen.getByText("Bitte einen Antragsteller aus der Suche wählen.")).toBeInTheDocument();
    expect(screen.getByText("Einsichtsanfrage erfassen")).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Antragsteller"), "Erika");
    await userEvent.click(await screen.findByRole("button", { name: "Erika Mustermann" }));
    expect(screen.getByText("Bitte das Antragsdatum eingeben.")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Datum Antrag"), "2026-09-10");
    expect(screen.getByText("Bitte mindestens einen Umfang wählen oder als Freitext angeben.")).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText("Belege"));
    expect(screen.getByText("Einsichtsanfrage erfassen")).toBeEnabled();
    await userEvent.click(screen.getByText("Einsichtsanfrage erfassen"));
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/weg/p/einsicht/${ID}`));
  });
});
