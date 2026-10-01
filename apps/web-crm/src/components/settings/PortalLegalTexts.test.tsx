import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PortalLegalTexts, type LegalTextsConfig } from "./PortalLegalTexts";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }));

const config: LegalTextsConfig = {
  terms_version_mode: "manual",
  policy_terms_version: null,
  approved_text_version: 2,
  suggested_label: "NB-2",
  in_sync: false,
  items: [
    { code: "impressum", label: "Portal: Impressum", released: true, version: 1, external_url: null },
    { code: "datenschutz", label: "Portal: Datenschutzerklärung", released: false, version: null, external_url: "https://example.test/dsgvo" },
    { code: "nutzungsbedingungen", label: "Portal: Nutzungsbedingungen", released: true, version: 2, external_url: null },
  ],
};

describe("PortalLegalTexts", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows release status per text and the difference to the terms version", () => {
    renderIntl(<PortalLegalTexts config={config} canChange={false} />);
    expect(screen.getByTestId("legal-item-impressum")).toHaveTextContent("freigegeben, Version 1");
    expect(screen.getByTestId("legal-item-datenschutz")).toHaveTextContent("Text nicht freigegeben");
    expect(screen.getByTestId("legal-item-datenschutz")).toHaveTextContent("Externer Link hinterlegt");
    expect(screen.getByText("Fassung weicht vom freigegebenen Text ab")).toBeInTheDocument();
    // Without contacts:approve neither switch nor apply is offered.
    expect(screen.queryByRole("button", { name: "Fassung jetzt übernehmen" })).toBeNull();
  });

  it("applies the suggested version only after confirmation", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({ ...config, in_sync: true }));
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    renderIntl(<PortalLegalTexts config={config} canChange />);
    await userEvent.click(screen.getByRole("button", { name: "Fassung jetzt übernehmen" }));
    expect(fetchMock).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Fassung jetzt übernehmen" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(confirm).toHaveBeenCalledWith(expect.stringContaining("NB-2"));
    expect(String(fetchMock.mock.calls[0]![0])).toContain("/tenant/legal-texts-config/apply-terms-version");
    expect(JSON.parse(String(fetchMock.mock.calls[0]![1]?.body))).toEqual({ confirm: true });
  });

  it("saves the switch", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse(config));
    renderIntl(<PortalLegalTexts config={config} canChange />);
    expect(screen.getByRole("button", { name: "Schalter speichern" })).toBeDisabled();
    await userEvent.click(screen.getByRole("radio", { name: /Dem freigegebenen Text folgen/ }));
    await userEvent.click(screen.getByRole("button", { name: "Schalter speichern" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(fetchMock.mock.calls[0]![1]?.method).toBe("PUT");
    expect(JSON.parse(String(fetchMock.mock.calls[0]![1]?.body))).toEqual({ terms_version_mode: "follow_text" });
  });
});
