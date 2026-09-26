import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { InspectionPanel, type InspectionRequest } from "./InspectionPanel";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh, push: vi.fn() }),
}));

const ID = "01920000-0000-7000-8000-00000000a610";
const request: InspectionRequest = {
  id: ID,
  status: "released",
  delivery_kind: null,
  package_document_id: null,
  package_sha256: null,
  package_created_at: null,
  events: [
    { id: "e1", kind: "status", from_status: null, to_status: "requested", note: null, occurred_at: "2026-09-20T08:00:00Z" },
    { id: "e2", kind: "note", from_status: null, to_status: null, note: "Welches Jahr?", occurred_at: "2026-09-21T08:00:00Z" },
    { id: "e3", kind: "status", from_status: "requested", to_status: "released", note: null, occurred_at: "2026-09-22T08:00:00Z" },
  ],
};
const documents = [
  { id: "d1", filename: "abrechnung-2025.pdf", title: "Abrechnung", released: true, created_at: "2026-03-01T10:00:00Z" },
  { id: "d2", filename: "intern.pdf", title: "Intern", released: false, created_at: "2026-03-02T10:00:00Z" },
];

describe("InspectionPanel", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("offers only the released documents, builds the package and shows the checksums", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ request_id: ID, document_id: "p1", sha256: "ab".repeat(32), entries: [{ file: "abrechnung-2025.pdf", sha256: "cd".repeat(32) }] }),
    );
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<InspectionPanel request={request} documents={documents} />);
    expect(screen.getByTestId("inspection-status")).toHaveTextContent("freigegeben");
    expect(screen.getByText("nicht freigegeben")).toBeInTheDocument();
    const boxes = screen.getAllByRole("checkbox");
    expect(boxes[0]).toBeEnabled();
    expect(boxes[1]).toBeDisabled();
    const build = screen.getByRole("button", { name: "Paket erzeugen" });
    expect(build).toBeDisabled();
    await userEvent.click(boxes[0]!);
    expect(build).toBeEnabled();
    await userEvent.click(build);
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe(`/api/bff/hoa/inspection-requests/${ID}/package`);
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({ document_ids: ["d1"] });
    expect(await screen.findByTestId("package-entries")).toHaveTextContent(`abrechnung-2025.pdf ${"cd".repeat(32)}`);
    expect(refresh).toHaveBeenCalled();
    expect(screen.getByTestId("inspection-trail")).toHaveTextContent("Rückfrage · Welches Jahr?");
  });

  it("requires a note for a rejection and sends the delivery kind with provided", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ...request, status: "provided" }));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<InspectionPanel request={{ ...request, package_document_id: "p1", package_sha256: "ef".repeat(32), package_created_at: "2026-09-23T08:00:00Z" }} documents={documents} />);
    expect(screen.getByTestId("package-download")).toHaveAttribute("href", `/api/bff/hoa/inspection-requests/${ID}/package`);
    expect(screen.getByTestId("package-sha")).toHaveTextContent("ef".repeat(32));
    expect(screen.getByRole("button", { name: "Ablehnen" })).toBeDisabled();
    await userEvent.selectOptions(screen.getByRole("combobox"), "on_site");
    await userEvent.click(screen.getByRole("button", { name: "Bereitstellen" }));
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe(`/api/bff/hoa/inspection-requests/${ID}/transition`);
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({ status: "provided", note: null, delivery_kind: "on_site" });
  });
});
