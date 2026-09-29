import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { CreditorContactButton, type CounterpartyContact } from "./CreditorContactButton";

const TX = "0192abcd-0000-7000-8000-000000000002";
const CONTACT = "0192abcd-0000-7000-8000-000000000003";
const PROP = "0192abcd-0000-7000-8000-000000000004";

const unknown: CounterpartyContact = { contact_id: null, display_name: null, basis: null, is_creditor: false, property_id: PROP, linked_to_property: false, counterpart_name: "Rohr frei GmbH", has_counterpart_iban: true };

describe("CreditorContactButton", () => {
  afterEach(() => vi.restoreAllMocks());

  it("creates a creditor contact from the counterparty and reports the pending IBAN", async () => {
    const bodies: unknown[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/counterparty-contact")) return jsonResponse(unknown);
      if (url.endsWith("/creditor-contact")) {
        bodies.push(JSON.parse(String(init?.body)));
        return jsonResponse({ contact_id: CONTACT, display_name: "Rohr frei GmbH", created: true, link_id: "l", bank_account_pending: true }, 201);
      }
      return jsonResponse({}, 404);
    });
    renderIntl(<CreditorContactButton transactionId={TX} outgoing />);
    await userEvent.click(await screen.findByRole("button", { name: "Kreditor anlegen" }));
    expect(screen.getByLabelText("Name des Kreditors")).toHaveValue("Rohr frei GmbH");
    await userEvent.type(screen.getByLabelText("Gewerk"), "Sanitär");
    await userEvent.click(screen.getByRole("button", { name: "Anlegen und verknüpfen" }));
    await waitFor(() => expect(bodies).toEqual([{ name: "Rohr frei GmbH", trade: "Sanitär", link_property: true }]));
    expect(await screen.findByTestId("creditor-created")).toHaveTextContent("Kreditor Rohr frei GmbH angelegt und mit dem Objekt verknüpft. Die IBAN wartet auf die Freigabe durch eine zweite Person.");
    expect(screen.getByRole("link", { name: "Kontakt öffnen" })).toHaveAttribute("href", `/kontakte/${CONTACT}`);
  });

  it("shows the known counterparty instead of the button and offers the property link", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse({ ...unknown, contact_id: CONTACT, display_name: "Rohr frei GmbH", basis: "iban", is_creditor: true }),
    );
    renderIntl(<CreditorContactButton transactionId={TX} outgoing />);
    expect(await screen.findByTestId("creditor-known")).toHaveTextContent("Gegenpartei laut IBAN: Rohr frei GmbH (kein Beweis).");
    expect(screen.queryByRole("button", { name: "Kreditor anlegen" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Als Kreditor mit dem Objekt verknüpfen" })).toBeInTheDocument();
  });

  it("offers nothing for an incoming payment of an unknown counterparty", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse(unknown));
    renderIntl(<CreditorContactButton transactionId={TX} outgoing={false} />);
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
