import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";

import { renderIntl } from "@/test/intl";

import { PhotoPicker } from "./PhotoPicker";

function Harness({ single = false }: { single?: boolean }) {
  const [files, setFiles] = useState<File[]>([]);
  return (
    <>
      <PhotoPicker files={files} onChange={setFiles} single={single} />
      <output data-testid="count">{files.length}</output>
    </>
  );
}

describe("PhotoPicker", () => {
  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => "blob:preview");
    URL.revokeObjectURL = vi.fn();
  });

  it("offers a camera input and a gallery input with the fixed accept lists", () => {
    renderIntl(<Harness />);
    const capture = screen.getByTestId("photo-capture");
    expect(capture).toHaveAttribute("accept", "image/*");
    expect(capture).toHaveAttribute("capture", "environment");
    expect(capture).not.toHaveAttribute("multiple");
    const pick = screen.getByTestId("photo-pick");
    expect(pick).toHaveAttribute("accept", "image/jpeg,image/png,image/heic,image/heif");
    expect(pick).not.toHaveAttribute("capture");
    expect(pick).toHaveAttribute("multiple");
  });

  it("keeps picked files in state, removes one with a 44 px target and revokes URLs on unmount", async () => {
    const { unmount } = renderIntl(<Harness />);
    const a = new File(["a"], "a.jpg", { type: "image/jpeg" });
    const b = new File(["b"], "b.jpg", { type: "image/jpeg" });
    await userEvent.upload(screen.getByTestId("photo-pick"), [a, b]);
    expect(screen.getByTestId("count")).toHaveTextContent("2");
    expect(screen.getAllByRole("img")).toHaveLength(2);
    const remove = screen.getByLabelText("Datei entfernen: a.jpg");
    expect(remove.className).toContain("h-11");
    expect(remove.className).toContain("w-11");
    await userEvent.click(remove);
    expect(screen.getByTestId("count")).toHaveTextContent("1");
    expect(screen.getByRole("img")).toHaveAttribute("alt", "b.jpg");
    unmount();
    expect(URL.revokeObjectURL).toHaveBeenCalled();
  });

  it("keeps only one file in single mode", async () => {
    renderIntl(<Harness single />);
    await userEvent.upload(screen.getByTestId("photo-capture"), new File(["a"], "a.jpg", { type: "image/jpeg" }));
    await userEvent.upload(screen.getByTestId("photo-capture"), new File(["b"], "b.jpg", { type: "image/jpeg" }));
    expect(screen.getByTestId("count")).toHaveTextContent("1");
    expect(screen.getByTestId("photo-pick")).not.toHaveAttribute("multiple");
  });
});
