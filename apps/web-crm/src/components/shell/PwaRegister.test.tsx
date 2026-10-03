import { render } from "@testing-library/react";

import { PwaRegister } from "./PwaRegister";

describe("PwaRegister", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    Reflect.deleteProperty(navigator, "serviceWorker");
  });

  it("registers /sw.js with root scope and renders nothing", () => {
    const register = vi.fn().mockResolvedValue({});
    Object.defineProperty(navigator, "serviceWorker", { value: { register }, configurable: true });
    const { container } = render(<PwaRegister />);
    expect(container).toBeEmptyDOMElement();
    expect(register).toHaveBeenCalledWith("/sw.js", { scope: "/" });
  });

  it("swallows a failed registration", async () => {
    const register = vi.fn().mockRejectedValue(new Error("blocked"));
    Object.defineProperty(navigator, "serviceWorker", { value: { register }, configurable: true });
    expect(() => render(<PwaRegister />)).not.toThrow();
    await Promise.resolve();
  });

  it("does nothing without service worker support", () => {
    expect(() => render(<PwaRegister />)).not.toThrow();
  });
});
