import { act, fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { jsonResponse, renderIntl } from "@/test/intl";

import { MeterReadingForm } from "./MeterReadingForm";

function fill(meter: string, value: string, date: string) {
  if (meter) fireEvent.change(document.getElementById("meter-id")!, { target: { value: meter } });
  if (value) fireEvent.change(document.getElementById("meter-value")!, { target: { value } });
  if (date) fireEvent.change(document.getElementById("meter-date")!, { target: { value: date } });
}

describe("MeterReadingForm", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("validates the required fields without a request", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<MeterReadingForm />);
    await userEvent.click(screen.getByRole("button"));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    fill("M-1", "", "");
    await userEvent.click(screen.getByRole("button"));
    expect(screen.getByRole("alert")).toBeInTheDocument();
    fill("", "12,5", "");
    await userEvent.click(screen.getByRole("button"));
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("posts the reading with a decimal point to the portal path", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: "mr1" }));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<MeterReadingForm />);
    fill(" M-1 ", "12,5", "2026-10-01");
    await act(async () => {
      await userEvent.click(screen.getByRole("button"));
    });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/portal/meter-readings");
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({ meter_id: "M-1", value: "12.5", read_at: "2026-10-01", document_ids: [] });
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows the API error (403)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ title: "Forbidden", status: 403, detail: "x" }, 403)));
    renderIntl(<MeterReadingForm />);
    fill("M-1", "1", "2026-10-01");
    await act(async () => {
      await userEvent.click(screen.getByRole("button"));
    });
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
  it("uploads the meter photo first and sends its id (AM06, GAJ-401)", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ id: "doc1" }, 201))
      .mockResolvedValueOnce(jsonResponse({ id: "mr2", photo_missing: false }, 201));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<MeterReadingForm />);
    expect(screen.getByTestId("meter-photo-missing")).toBeInTheDocument();
    const camera = screen.getByTestId("meter-photo-camera");
    expect(camera).toHaveAttribute("capture", "environment");
    fireEvent.change(camera, { target: { files: [new File(["x"], "zaehler.jpg", { type: "image/jpeg" })] } });
    expect(screen.queryByTestId("meter-photo-missing")).toBeNull();
    fill("M-1", "7", "2026-10-01");
    await act(async () => {
      await userEvent.click(screen.getByRole("button"));
    });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/bff/portal/uploads");
    expect(JSON.parse(fetchMock.mock.calls[1]?.[1]?.body as string).document_ids).toEqual(["doc1"]);
  });

  it("notes a reading sent without photo", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ id: "mr3", photo_missing: true }, 201)));
    renderIntl(<MeterReadingForm />);
    fill("M-1", "7", "2026-10-01");
    await act(async () => {
      await userEvent.click(screen.getByRole("button"));
    });
    expect(await screen.findByText(/ohne Foto übermittelt/)).toBeInTheDocument();
  });

  it("stops when the photo upload fails", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ title: "x", status: 422, detail: "Datei zu groß" }, 422));
    vi.stubGlobal("fetch", fetchMock);
    renderIntl(<MeterReadingForm />);
    fireEvent.change(document.getElementById("meter-photo")!, {
      target: { files: [new File(["x"], "a.jpg", { type: "image/jpeg" })] },
    });
    fill("M-1", "7", "2026-10-01");
    await act(async () => {
      await userEvent.click(screen.getByRole("button"));
    });
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
