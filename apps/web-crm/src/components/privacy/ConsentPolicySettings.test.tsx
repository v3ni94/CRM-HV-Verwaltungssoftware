import { fireEvent, screen, waitFor } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ConsentPolicySettings } from "./ConsentPolicySettings";

const POLICY = { email_delivery: "consent_only", data_sharing: "consent_only", portal_terms_version: null };

describe("ConsentPolicySettings", () => {
  afterEach(() => vi.restoreAllMocks());

  it("is read only without the approve right", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse(POLICY));
    renderIntl(<ConsentPolicySettings canEdit={false} />);
    expect(await screen.findByLabelText("Zustellung per E-Mail")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Speichern" })).not.toBeInTheDocument();
  });

  it("saves the changed policy", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse(POLICY));
    renderIntl(<ConsentPolicySettings canEdit />);
    fireEvent.change(await screen.findByLabelText("Datenweitergabe an Dritte"), { target: { value: "consent_or_contract" } });
    fireEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => {
      const put = fetchMock.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === "PUT");
      expect(JSON.parse(String((put![1] as RequestInit).body))).toEqual({
        email_delivery: "consent_only",
        data_sharing: "consent_or_contract",
        portal_terms_version: null,
      });
    });
  });
});
