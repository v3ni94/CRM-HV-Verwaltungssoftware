import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { DispatchPanel } from "./DispatchPanel";

const docs = [{ id: "11111111-1111-1111-1111-111111111111", title: "Mahnung 1" }];

describe("DispatchPanel", () => {
  afterEach(() => vi.restoreAllMocks());

  it("prepares a dispatch for the chosen channel and records delivery only with kind and reference", async () => {
    const bodies: unknown[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/api/bff/dispatches") && init?.method === "POST") {
        bodies.push(JSON.parse(String(init.body)));
        return jsonResponse(
          { id: "d1", channel: "registered", status: "prepared", document_id: docs[0]!.id, further_dispatches: [] },
          201,
        );
      }
      if (url.endsWith("/api/bff/dispatches/d1/evidence")) {
        bodies.push(JSON.parse(String(init?.body)));
        return jsonResponse({ id: "d1", channel: "registered", status: "delivered", document_id: docs[0]!.id });
      }
      return jsonResponse({ title: "unerwartet" }, 500);
    });
    renderIntl(<DispatchPanel contactId="c1" documents={docs} canCreate canRecord />);
    await userEvent.selectOptions(screen.getByLabelText("Zustellweg"), "registered");
    await userEvent.click(screen.getByRole("button", { name: "Zustellung vorbereiten" }));
    await waitFor(() => expect(screen.getByText("vorbereitet")).toBeInTheDocument());
    expect(bodies[0]).toEqual({ document_id: docs[0]!.id, contact_id: "c1", channel: "registered" });
    const record = screen.getByRole("button", { name: "Zugang mit Nachweis erfassen" });
    expect(record).toBeDisabled();
    await userEvent.selectOptions(screen.getByLabelText("Nachweisart"), "registered_mail");
    await userEvent.type(screen.getByLabelText("Referenz, zum Beispiel Sendungsnummer"), "RS 123");
    await userEvent.click(record);
    await waitFor(() => expect(screen.getByText("zugegangen")).toBeInTheDocument());
    expect(bodies[1]).toEqual({ status: "delivered", evidence_kind: "registered_mail", evidence_ref: "RS 123" });
  });

  it("creates the postal job automatically and sends submit_postal false only when switched off and hides the form without the right", async () => {
    const bodies: unknown[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (_input, init) => {
      bodies.push(JSON.parse(String(init?.body)));
      return jsonResponse({ id: "d2", channel: "post", status: "prepared", document_id: docs[0]!.id, further_dispatches: [] }, 201);
    });
    const { unmount } = renderIntl(<DispatchPanel contactId="c1" documents={docs} canCreate canRecord={false} />);
    await userEvent.click(screen.getByLabelText("Postauftrag automatisch anlegen"));
    await userEvent.click(screen.getByRole("button", { name: "Zustellung vorbereiten" }));
    await waitFor(() => expect(bodies.length).toBe(1));
    expect(bodies[0]).toMatchObject({ channel: "post", submit_postal: false });
    unmount();
    renderIntl(<DispatchPanel contactId="c1" documents={docs} canCreate={false} canRecord={false} />);
    expect(screen.getByText(/nur mit Recht communication:create/)).toBeInTheDocument();
  });
});
