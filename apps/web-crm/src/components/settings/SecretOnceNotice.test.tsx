import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderIntl } from "@/test/intl";

import { SecretOnceNotice } from "./SecretOnceNotice";

describe("SecretOnceNotice (GAH-407)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders title, secret and hint and calls onDismiss", async () => {
    const onDismiss = vi.fn();
    renderIntl(<SecretOnceNotice title="Neues Geheimnis" secret="s3cret-value" onDismiss={onDismiss} />);
    expect(screen.getByTestId("secret-once")).toHaveTextContent("s3cret-value");
    expect(screen.getByRole("heading", { name: "Neues Geheimnis" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Ich habe den Wert gesichert" }));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it("confirms the copy when the clipboard accepts the value", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    renderIntl(<SecretOnceNotice title="T" secret="abc" onDismiss={() => undefined} />);
    await userEvent.click(screen.getByRole("button", { name: "In die Zwischenablage kopieren" }));
    await waitFor(() => expect(screen.getByText("Kopiert.")).toBeInTheDocument());
    expect(writeText).toHaveBeenCalledWith("abc");
  });

  it("shows no confirmation when the clipboard is refused", async () => {
    const writeText = vi.fn().mockRejectedValue(new Error("denied"));
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    renderIntl(<SecretOnceNotice title="T" secret="abc" onDismiss={() => undefined} />);
    await userEvent.click(screen.getByRole("button", { name: "In die Zwischenablage kopieren" }));
    await waitFor(() => expect(writeText).toHaveBeenCalled());
    expect(screen.queryByText("Kopiert.")).not.toBeInTheDocument();
  });
});
