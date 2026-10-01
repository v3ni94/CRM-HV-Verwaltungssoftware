import { screen, fireEvent, waitFor } from "@testing-library/react";

import { PortalSettings } from "./PortalSettings";
import { renderIntl } from "@/test/intl";

const bff = vi.fn();
vi.mock("@/lib/bff", () => ({ bff: (...args: unknown[]) => bff(...args) }));

describe("PortalSettings", () => {
  beforeEach(() => bff.mockReset());

  it("keeps existing branding values when saving and sends the policy", async () => {
    bff.mockResolvedValue({ ok: true, data: {}, status: 200, etag: null });
    renderIntl(<PortalSettings branding={{ primary_color: "#112233", logo_light_document_id: "abc" }} secondFactor="account_choice" canUpdate />);
    fireEvent.change(screen.getByLabelText(/Link zum Impressum/), { target: { value: "https://example.test/impressum" } });
    fireEvent.change(screen.getByLabelText(/Anmeldestrenge/), { target: { value: "required" } });
    fireEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(bff).toHaveBeenCalled());
    const body = JSON.parse((bff.mock.calls[0]![1] as RequestInit).body as string);
    expect(body.portal_second_factor).toBe("required");
    expect(body.branding).toMatchObject({ primary_color: "#112233", logo_light_document_id: "abc", imprint_url: "https://example.test/impressum", privacy_url: null });
  });

  it("refuses links without https", () => {
    renderIntl(<PortalSettings branding={{}} secondFactor="account_choice" canUpdate />);
    fireEvent.change(screen.getByLabelText(/Link zum Impressum/), { target: { value: "http://x.test" } });
    expect(screen.getByRole("button", { name: "Speichern" })).toBeDisabled();
  });

  it("uploads a logo through the document upload and saves its id", async () => {
    bff.mockResolvedValueOnce({ ok: true, data: { id: "doc-1" }, status: 201, etag: null });
    bff.mockResolvedValueOnce({ ok: true, data: {}, status: 200, etag: null });
    renderIntl(<PortalSettings branding={{ primary_color: "#112233" }} secondFactor="account_choice" canUpdate />);
    const file = new File(["x"], "logo.png", { type: "image/png" });
    fireEvent.change(screen.getByLabelText(/Logo für das Portal/), { target: { files: [file] } });
    await waitFor(() => expect(bff).toHaveBeenCalledTimes(1));
    expect(bff.mock.calls[0]![0]).toBe("/api/bff/documents");
    await screen.findByText(/Logo gesetzt/);
    fireEvent.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(bff).toHaveBeenCalledTimes(2));
    const body = JSON.parse((bff.mock.calls[1]![1] as RequestInit).body as string);
    expect(body.branding).toMatchObject({ primary_color: "#112233", logo_light_document_id: "doc-1" });
  });

  it("rejects non image files", async () => {
    renderIntl(<PortalSettings branding={{}} secondFactor="account_choice" canUpdate />);
    const file = new File(["x"], "a.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByLabelText(/Logo für das Portal/), { target: { files: [file] } });
    await screen.findByText(/Nur PNG oder JPEG/);
    expect(bff).not.toHaveBeenCalled();
  });
});
