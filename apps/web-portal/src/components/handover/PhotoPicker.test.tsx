import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { renderIntl } from "@/test/intl";

import { ACCEPT, PhotoPicker, type PhotoJob } from "./PhotoPicker";

const jobs: PhotoJob[] = [
  { key: "a", name: "a.jpg", status: "done" },
  { key: "b", name: "b.png", status: "failed", message: "Zu groß" },
  { key: "c", name: "c.heic", status: "uploading" },
  { key: "d", name: "d.jpg", status: "queued" },
];

describe("PhotoPicker", () => {
  it("offers camera and gallery inputs with the accepted image types", () => {
    renderIntl(<PhotoPicker onFiles={vi.fn()} />);
    const camera = screen.getByTestId("photo-input-camera");
    const gallery = screen.getByTestId("photo-input-gallery");
    expect(camera).toHaveAttribute("capture", "environment");
    expect(camera).toHaveAttribute("accept", ACCEPT);
    expect(gallery).toHaveAttribute("multiple");
    expect(screen.getByLabelText("Foto aufnehmen")).toBe(camera);
    expect(screen.getByLabelText("Aus Galerie wählen")).toBe(gallery);
  });

  it("hands the chosen files over", async () => {
    const onFiles = vi.fn();
    renderIntl(<PhotoPicker onFiles={onFiles} />);
    const file = new File(["x"], "foto.jpg", { type: "image/jpeg" });
    await userEvent.upload(screen.getByTestId("photo-input-gallery"), [file]);
    expect(onFiles).toHaveBeenCalledWith([file]);
  });

  it("passes nothing on when the selection is empty", () => {
    const onFiles = vi.fn();
    renderIntl(<PhotoPicker onFiles={onFiles} />);
    const input = screen.getByTestId("photo-input-gallery");
    input.dispatchEvent(new Event("change", { bubbles: true }));
    expect(onFiles).not.toHaveBeenCalled();
  });

  it("disables both inputs", () => {
    renderIntl(<PhotoPicker onFiles={vi.fn()} disabled />);
    expect(screen.getByTestId("photo-input-camera")).toBeDisabled();
    expect(screen.getByTestId("photo-input-gallery")).toBeDisabled();
  });

  it("shows the state of each upload and retries only failed ones", async () => {
    const onRetry = vi.fn();
    renderIntl(<PhotoPicker onFiles={vi.fn()} jobs={jobs} onRetry={onRetry} />);
    const items = screen.getAllByRole("listitem");
    expect(items.map((li) => li.getAttribute("data-status"))).toEqual(["done", "failed", "uploading", "queued"]);
    expect(screen.getByText("Zu groß")).toBeInTheDocument();
    const retry = screen.getAllByRole("button", { name: "Erneut versuchen" });
    expect(retry).toHaveLength(1);
    await userEvent.click(retry[0]!);
    expect(onRetry).toHaveBeenCalledWith(jobs[1]);
  });

  it("shows no retry button without a handler", () => {
    renderIntl(<PhotoPicker onFiles={vi.fn()} jobs={jobs} />);
    expect(screen.queryByRole("button", { name: "Erneut versuchen" })).toBeNull();
  });
});
