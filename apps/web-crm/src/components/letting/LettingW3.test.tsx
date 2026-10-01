import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { RentIncreaseLinks } from "@/components/contracts/RentIncreaseLinks";
import { MailHtmlFrame, mailFrameDocument } from "@/components/mail/MailHtmlFrame";
import { jsonResponse, renderIntl } from "@/test/intl";

import { ExposePdf } from "./ExposePdf";
import { ProspectMatches } from "./ProspectMatches";
import { RentIndexAdmin, type RentIndexRow } from "./RentIndexAdmin";
import { RentIndexAdopt } from "./RentIndexAdopt";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push: vi.fn() }) }));

const ID = "0192abcd-0000-7000-8000-000000000001";
const ROW: RentIndexRow = {
  id: ID,
  municipality: "Bernau",
  index_name: "Mietspiegel 2024",
  valid_from: "2024-01-01",
  valid_to: null,
  year_built_from: null,
  year_built_to: null,
  area_from_sqm: null,
  area_to_sqm: null,
  equipment: null,
  rent_min: "6.50",
  rent_mid: "7.20",
  rent_max: "8.10",
  source_note: "Amtsblatt",
};

describe("Letting wave 3", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    refresh.mockClear();
  });

  it("files the exposé PDF and reports the embedded images", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ document_id: ID, filename: "expose.pdf", missing: [], draft: false, images_embedded: 2 }, 201));
    renderIntl(<ExposePdf unitId={ID} canCreate />);
    await userEvent.click(screen.getByRole("button", { name: "Exposé als PDF ablegen" }));
    await waitFor(() => expect(screen.getByTestId("expose-pdf-result").textContent).toContain("mit 2 Bildern"));
  });

  it("ranks the prospect match", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse([{ prospect_id: ID, contact_id: null, unit_id: ID, status: "new", met: ["Zimmer"], unmet: ["Kaltmiete"], unknown: [] }]),
    );
    renderIntl(<ProspectMatches listingId={ID} />);
    await userEvent.click(screen.getByRole("button", { name: "Interessenten abgleichen" }));
    await waitFor(() => expect(screen.getAllByTestId("match-row")).toHaveLength(1));
    expect(screen.getByTestId("match-row").textContent).toContain("nicht erfüllt: Kaltmiete");
  });

  it("previews a CSV import and blocks the import on errors", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse({ dry_run: true, rows: 1, errors: [{ line: 2, error: "Zahl ungültig" }], created: 0, skipped: 0 }));
    renderIntl(<RentIndexAdmin rows={[ROW]} canEdit />);
    expect(screen.getAllByTestId("rent-index-row")).toHaveLength(1);
    await userEvent.type(screen.getByLabelText("CSV Import"), "gemeinde;name;stand;min;max;quelle");
    await userEvent.click(screen.getByRole("button", { name: "Vorschau" }));
    await waitFor(() => expect(screen.getByTestId("import-preview").textContent).toContain("Zeile 2: Zahl ungültig"));
    expect(screen.getByRole("button", { name: "Übernehmen" })).toBeDisabled();
  });

  it("hides the maintenance forms without the right", () => {
    renderIntl(<RentIndexAdmin rows={[ROW]} canEdit={false} />);
    expect(screen.queryByTestId("rent-index-form")).not.toBeInTheDocument();
  });

  it("adopts a chosen position of the range into the case", async () => {
    const calls: { url: string; body: unknown }[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
      const url = String(input);
      calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : null });
      if (url.includes("/rent-index/lookup")) return jsonResponse({ found: true, matches: [{ ...ROW }], notes: [] });
      return jsonResponse({ id: ID });
    });
    renderIntl(<RentIndexAdopt caseId={ID} livingArea="50.00" canEdit />);
    await userEvent.type(screen.getByLabelText("Gemeinde"), "Bernau");
    await userEvent.click(screen.getByRole("button", { name: "Spanne suchen" }));
    await userEvent.click(await screen.findByRole("button", { name: "Mittelwert übernehmen" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(calls[0]!.url).toContain("living_area_sqm=50.00");
    expect(calls[1]!.body).toEqual({ entry_id: ID, position: "mid" });
  });

  it("warns when an open case takes effect inside the rent increase lock", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse([{ id: ID, status: "draft", effective_date: "2026-11-01", target_rent: "500.00" }]));
    renderIntl(<RentIncreaseLinks contractId={ID} blockUntil="2026-12-31" />);
    await waitFor(() => expect(screen.getByTestId("rent-increase-links")).toBeInTheDocument());
    expect(screen.getByRole("alert").textContent).toContain("31.12.2026");
  });
});

describe("MailHtmlFrame", () => {
  it("blocks remote images and scripts by CSP until the clerk loads the images", async () => {
    expect(mailFrameDocument("<p>x</p>", false)).toContain("img-src data: cid:;");
    expect(mailFrameDocument("<p>x</p>", true)).toContain("img-src https: data: cid:;");
    renderIntl(<MailHtmlFrame html='<img src="https://track.example/p.gif">' testId="f" />);
    const frame = screen.getByTestId("f") as HTMLIFrameElement;
    expect(frame.getAttribute("sandbox")).not.toContain("allow-scripts");
    expect(frame.getAttribute("srcdoc")).toContain("img-src data: cid:;");
    await userEvent.click(screen.getByRole("button", { name: "Bilder laden" }));
    expect((screen.getByTestId("f") as HTMLIFrameElement).getAttribute("srcdoc")).toContain("img-src https: data: cid:;");
  });
});
