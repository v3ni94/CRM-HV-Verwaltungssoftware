import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { ProtocolDraft } from "./ProtocolDraft";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const MEETING = "0192abcd-0000-7000-8000-000000000025";

describe("ProtocolDraft", () => {
  afterEach(() => vi.restoreAllMocks());

  it("creates the draft, lists missing values and offers the download", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse({ document_id: "doc-1", title: "Protokollentwurf", missing: ["Versammlungsleitung"], note: "Entwurf" }, 201),
    );
    renderIntl(<ProtocolDraft meetingId={MEETING} draftDocumentId={null} minutesDocumentId={null} />);
    expect(screen.queryByText("Entwurf herunterladen")).not.toBeInTheDocument();
    await userEvent.click(screen.getByText("Protokollentwurf erzeugen"));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(String(fetchMock.mock.calls[0]?.[0])).toBe(`/api/bff/hoa/meetings/${MEETING}/protocol-draft`);
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("POST");
    expect(screen.getByText(/Nicht erfasst: Versammlungsleitung/)).toBeInTheDocument();
    expect(screen.getByText("Entwurf herunterladen")).toHaveAttribute("href", "/api/handover-files/documents/doc-1/content");
    expect(screen.getByText("Protokollentwurf neu erzeugen")).toBeInTheDocument();
  });

  it("shows the existing draft and keeps the signed minutes note", () => {
    renderIntl(<ProtocolDraft meetingId={MEETING} draftDocumentId="doc-0" minutesDocumentId="doc-signed" />);
    expect(screen.getByText("Entwurf herunterladen")).toHaveAttribute("href", "/api/handover-files/documents/doc-0/content");
    expect(screen.getByText(/unterschriebene Protokoll bleibt verknüpft/)).toBeInTheDocument();
  });

  it("reports an error of the API", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async () =>
      jsonResponse({ title: "Fehlende Firmendaten", detail: "Fehlende Firmendaten des Mandanten: name." }, 422),
    );
    renderIntl(<ProtocolDraft meetingId={MEETING} draftDocumentId={null} minutesDocumentId={null} />);
    await userEvent.click(screen.getByText("Protokollentwurf erzeugen"));
    expect(await screen.findByRole("alert")).toHaveTextContent(/Firmendaten/);
  });
});
