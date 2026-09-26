import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderIntl } from "@/test/intl";

import { daysUntil, FinApiConsentBanner } from "./FinApiConsentBanner";

const TODAY = new Date(2026, 8, 26); // 26.09.2026 local

describe("FinApiConsentBanner", () => {
  it("computes the day difference on calendar days", () => {
    expect(daysUntil("2026-10-06", TODAY)).toBe(10);
    expect(daysUntil("2026-09-26", TODAY)).toBe(0);
    expect(daysUntil("2026-09-25", TODAY)).toBe(-1);
  });

  it("renders nothing when the consent is valid for more than 10 days", () => {
    renderIntl(
      <FinApiConsentBanner status="active" consentValidUntil="2026-10-07" busy={false} onRenew={() => {}} today={TODAY} />,
    );
    expect(screen.queryByTestId("consent-banner")).not.toBeInTheDocument();
  });

  it("renders nothing without a known expiry date and an active status", () => {
    renderIntl(
      <FinApiConsentBanner status="active" consentValidUntil={null} busy={false} onRenew={() => {}} today={TODAY} />,
    );
    expect(screen.queryByTestId("consent-banner")).not.toBeInTheDocument();
  });

  it("warns 10 days before expiry with the date and starts the renewal on click", async () => {
    const onRenew = vi.fn();
    renderIntl(
      <FinApiConsentBanner status="active" consentValidUntil="2026-10-06" busy={false} onRenew={onRenew} today={TODAY} />,
    );
    const banner = screen.getByTestId("consent-banner");
    expect(banner).toHaveTextContent("06.10.2026");
    expect(banner).toHaveTextContent("10 Tagen");
    expect(banner).toHaveAttribute("role", "status");
    await userEvent.click(screen.getByRole("button", { name: "Zustimmung erneuern" }));
    expect(onRenew).toHaveBeenCalledTimes(1);
  });

  it("marks an expired consent clearly as expired", () => {
    renderIntl(
      <FinApiConsentBanner status="active" consentValidUntil="2026-09-20" busy={false} onRenew={() => {}} today={TODAY} />,
    );
    const banner = screen.getByRole("alert");
    expect(banner).toHaveTextContent("abgelaufen");
    expect(banner).toHaveTextContent("20.09.2026");
  });

  it("marks status consent_expired as expired even without a date", () => {
    renderIntl(
      <FinApiConsentBanner status="consent_expired" consentValidUntil={null} busy={true} onRenew={() => {}} today={TODAY} />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("abgelaufen");
    expect(screen.getByRole("button", { name: "Zustimmung erneuern" })).toBeDisabled();
  });
});
