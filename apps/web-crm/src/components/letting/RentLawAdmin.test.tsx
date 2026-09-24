import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { CapAreas, RentLawRules, type RentLawRule } from "./RentLawAdmin";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const rule = (over: Partial<RentLawRule> = {}): RentLawRule => ({
  code: "cap_percent",
  label: "Kappungsgrenze",
  norm: "§ 558 Abs. 3 BGB",
  value: "20",
  unit: "%",
  status: "draft",
  source_verified: false,
  source_url: null,
  note: null,
  released_at: null,
  ...over,
});

describe("RentLawRules", () => {
  afterEach(() => vi.restoreAllMocks());

  it("blocks release while the source is unchecked", () => {
    renderIntl(<RentLawRules rules={[rule()]} />);
    expect(screen.getByText("Freigeben")).toBeDisabled();
  });

  it("saves the source check, then releases", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({}));
    const { unmount } = renderIntl(<RentLawRules rules={[rule()]} />);
    await userEvent.click(screen.getByLabelText("am Originaltext geprüft"));
    expect(screen.getByText("Freigeben")).toBeDisabled();
    await userEvent.click(screen.getByText("Speichern"));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/platform/rent-law/rules/cap_percent");
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({ value: "20", source_verified: true });
    unmount();
    renderIntl(<RentLawRules rules={[rule({ source_verified: true })]} />);
    await userEvent.click(screen.getByText("Freigeben"));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(JSON.parse(fetchMock.mock.calls[1]?.[1]?.body as string)).toEqual({ status: "released" });
  });
});

describe("CapAreas", () => {
  afterEach(() => vi.restoreAllMocks());

  it("creates an area with source and decimal point", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => jsonResponse({}, 201));
    renderIntl(<CapAreas areas={[]} />);
    expect(screen.getByText(/Keine Gebiete erfasst/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Gemeinde"), "Musterstadt");
    await userEvent.clear(screen.getByLabelText("Kappungsgrenze in %"));
    await userEvent.type(screen.getByLabelText("Kappungsgrenze in %"), "15,0");
    await userEvent.type(screen.getByLabelText("Gültig ab"), "2025-01-01");
    await userEvent.type(screen.getByLabelText("Quelle (Verordnung)"), "Testverordnung");
    await userEvent.click(screen.getByText("Gebiet anlegen"));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({
      state: "NW",
      municipality: "Musterstadt",
      municipality_code: null,
      cap_percent: "15.0",
      valid_from: "2025-01-01",
      source: "Testverordnung",
    });
  });
});
