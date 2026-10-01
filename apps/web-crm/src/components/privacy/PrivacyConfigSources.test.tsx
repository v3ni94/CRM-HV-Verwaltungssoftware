import { fireEvent, screen, waitFor } from "@testing-library/react";

import { jsonResponse, renderIntl } from "@/test/intl";

import { PrivacyConfigSources } from "./PrivacyConfigSources";

const SOURCES = [
  { key: "gmail", name: "Google Gmail", service: "E-Mail", active: true, scope: "tenant", detail: "1 Postfach verbunden.", entry_id: null },
  { key: "s3:store.example", name: "Objektspeicher S3-API (store.example)", service: "Dateien", active: true, scope: "platform", detail: "Host store.example.", entry_id: "e1" },
];

function route() {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.endsWith("/config-sources/sync")) return jsonResponse({ created: [{}], updated: [], skipped_inactive: 2 });
    if (url.endsWith("/config-sources")) return jsonResponse(SOURCES);
    return jsonResponse({});
  });
}

describe("PrivacyConfigSources", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists detected services with register state", async () => {
    route();
    renderIntl(<PrivacyConfigSources canManage onSynced={() => undefined} />);
    const rows = await screen.findAllByTestId("privacy-source-row");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent("Fehlt");
    expect(rows[1]).toHaveTextContent("Erfasst");
    expect(rows[1]).toHaveTextContent("Plattform");
  });

  it("takes services over including inactive ones on request", async () => {
    const fetchMock = route();
    const onSynced = vi.fn();
    renderIntl(<PrivacyConfigSources canManage onSynced={onSynced} />);
    await screen.findAllByTestId("privacy-source-row");
    fireEvent.click(screen.getByLabelText("Auch konfigurierte, derzeit nicht aktive Dienste übernehmen"));
    fireEvent.click(screen.getByRole("button", { name: "Erkannte Dienste ins Register übernehmen" }));
    expect(await screen.findByRole("status")).toHaveTextContent("1 Einträge übernommen, 2 nicht aktive Dienste übersprungen.");
    const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/config-sources/sync"));
    expect(JSON.parse(String((call?.[1] as RequestInit).body))).toEqual({ include_inactive: true });
    await waitFor(() => expect(onSynced).toHaveBeenCalled());
  });

  it("hides the takeover without manage right", async () => {
    route();
    renderIntl(<PrivacyConfigSources canManage={false} onSynced={() => undefined} />);
    await screen.findAllByTestId("privacy-source-row");
    expect(screen.queryByRole("button", { name: "Erkannte Dienste ins Register übernehmen" })).not.toBeInTheDocument();
  });
});
