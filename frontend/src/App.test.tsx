import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import {
  getPublicEvents,
  getPublicLeaderboard,
  type LeaderboardResponse,
} from "./api";
import App from "./App";
import { useAuth } from "./authContext";

vi.mock("./authContext", () => ({
  useAuth: vi.fn(),
}));

vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  return {
    ...actual,
    getPublicEvents: vi.fn(),
    getPublicLeaderboard: vi.fn(),
  };
});

const publicEvent = {
  id: 17,
  name: "Kerfuffle",
  event_date: "2026-11-18",
  route_sheets: [{ id: 31, name: "North route" }],
};

const leaderboard: LeaderboardResponse = {
  event: {
    id: publicEvent.id,
    name: publicEvent.name,
    event_date: publicEvent.event_date,
  },
  route_sheet_id: null,
  stations_total: 1,
  stations: [{ id: 23, name: "Main stage", score_max: 10 }],
  participants: [{
    registration_number: "000001",
    place: 1,
    total_points: 0,
    stations_completed: 0,
    stations_total: 1,
    stations: [{ station_id: 23, name: "Main stage", points: null, score_max: 10 }],
  }],
};

const mockGetPublicEvents = vi.mocked(getPublicEvents);
const mockGetPublicLeaderboard = vi.mocked(getPublicLeaderboard);
const mockUseAuth = vi.mocked(useAuth);

beforeEach(() => {
  vi.clearAllMocks();
  window.history.pushState({}, "", "/leaderboard?eventId=17");
  mockUseAuth.mockReturnValue({
    user: null,
    loading: false,
    error: "",
    login: vi.fn(),
    logout: vi.fn(),
    clearError: vi.fn(),
  });
  mockGetPublicEvents.mockResolvedValue([publicEvent]);
  mockGetPublicLeaderboard.mockResolvedValue(leaderboard);
});

afterEach(cleanup);

describe("public leaderboard", () => {
  it("uses event names, supports route-sheet ranking, and displays only participant numbers", async () => {
    render(<App />);

    expect(await screen.findByText("№ 000001")).toBeTruthy();
    expect(screen.getByRole("option", { name: "Kerfuffle" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "North route" })).toBeTruthy();
    expect(screen.queryByText("Ada Lovelace")).toBeNull();
    expect(screen.queryByText("17")).toBeNull();

    fireEvent.change(screen.getByLabelText("Режим рейтинга"), {
      target: { value: "31" },
    });

    await waitFor(() => {
      expect(mockGetPublicLeaderboard).toHaveBeenLastCalledWith(
        17,
        31,
        expect.any(AbortSignal),
      );
    });
  });
});
