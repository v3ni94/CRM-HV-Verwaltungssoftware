import { screen, waitFor } from "@testing-library/react";

import { renderIntl } from "@/test/intl";

import { InvitationQr } from "./InvitationQr";

vi.mock("qrcode", () => ({
  default: { toDataURL: vi.fn(async () => "data:image/png;base64,QUJD") },
}));

describe("InvitationQr", () => {
  it("renders the link text and the QR image for an invitation link", async () => {
    const url = "https://portal.example.test/einladung?code=abc.def";
    renderIntl(<InvitationQr url={url} title="Einladungslink" alt="QR-Code des Einladungslinks" />);
    expect(screen.getByRole("link", { name: url })).toHaveAttribute("href", url);
    await waitFor(() => expect(screen.getByRole("img", { name: "QR-Code des Einladungslinks" })).toHaveAttribute("src", "data:image/png;base64,QUJD"));
  });

  it("renders nothing without a portal address", () => {
    renderIntl(<InvitationQr url={null} title="Einladungslink" alt="QR-Code" />);
    expect(screen.queryByTestId("invitation-qr")).toBeNull();
  });
});
