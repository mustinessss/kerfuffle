import { afterEach, describe, expect, it, vi } from "vitest";
import { createEvent } from "./api";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("createEvent", () => {
  it("uses the cookie session without sending an Authorization header", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          id: 1,
          name: "Test event",
          event_date: "2026-11-18",
        }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      ),
    );

    await createEvent({ name: "Test event", event_date: "2026-11-18" });

    const [, options] = fetchMock.mock.calls[0];
    expect(options?.credentials).toBe("include");
    expect(options?.headers).not.toHaveProperty("Authorization");
  });
});
