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
});
