import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CopyLink } from "./CopyLink";

const writeText = vi.fn<(_: string) => Promise<void>>();

beforeEach(() => {
  writeText.mockReset();
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText },
  });
});

afterEach(() => {
  cleanup();
});

describe("CopyLink", () => {
  it("copies the link and confirms success", async () => {
    writeText.mockResolvedValue(undefined);
    render(<CopyLink url="https://example.test/accept?token=secret" />);

    fireEvent.click(screen.getByRole("button", { name: "Скопировать ссылку" }));

    await waitFor(() => expect(writeText).toHaveBeenCalledWith(
      "https://example.test/accept?token=secret",
    ));
    expect(await screen.findByRole("button", { name: "Скопировано" })).toBeTruthy();
  });

  it("shows a manual-copy fallback when clipboard access fails", async () => {
    writeText.mockRejectedValue(new Error("clipboard unavailable"));
    render(<CopyLink url="https://example.test/reset?token=secret" />);

    fireEvent.click(screen.getByRole("button", { name: "Скопировать ссылку" }));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Выделите ссылку и скопируйте её вручную.",
    );
  });
});
