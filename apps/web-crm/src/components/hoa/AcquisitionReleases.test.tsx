import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { AcquisitionReleases, type AcquisitionItem } from "./AcquisitionReleases";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

const item = (status: AcquisitionItem["status"]): AcquisitionItem => ({
  contract_id: "k1",
  unit_number: "WE 01",
  acquisition_kind: null,
  special_succession_liability: false,
  allocation_proposal: "Vorschlag A",
  status,
});

describe("AcquisitionReleases", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    refresh.mockClear();
  });

  it("renders nothing without items", () => {
    renderIntl(<AcquisitionReleases statementId="s1" items={[]} note="n" />);
    expect(screen.queryByTestId("acquisition-releases")).toBeNull();
  });

  it("posts the request for an open item", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({}));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<AcquisitionReleases statementId="s1" items={[item("open")]} note="n" />);
    await act(async () => {
      await userEvent.click(screen.getByRole("button"));
    });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/hoa/statements/s1/acquisitions/k1/request");
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({ note: null });
    expect(refresh).toHaveBeenCalled();
  });

  it("requires a release note of 3 characters and shows 403", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ title: "Forbidden", status: 403, detail: "x" }, 403));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<AcquisitionReleases statementId="s1" items={[item("requested")]} note="n" />);
    const button = screen.getByRole("button");
    expect(button).toBeDisabled();
    await userEvent.type(screen.getByRole("textbox"), "ok!");
    await act(async () => {
      await userEvent.click(button);
    });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/hoa/statements/s1/acquisitions/k1/release");
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(refresh).not.toHaveBeenCalled();
  });

  it("offers no action once released", () => {
    renderIntl(<AcquisitionReleases statementId="s1" items={[item("released")]} note="n" />);
    expect(screen.queryByRole("button")).toBeNull();
  });
});
