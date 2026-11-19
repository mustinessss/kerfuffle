import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import {
  getEventLeaderboard,
  getEvents,
  getRouteSheets,
  getStationLeaderboard,
  getStations,
  type LeaderboardResponse,
  type StationLeaderboardResponse,
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
    getEventLeaderboard: vi.fn(),
    getEvents: vi.fn(),
    getRouteSheets: vi.fn(),
    getStationLeaderboard: vi.fn(),
    getStations: vi.fn(),
  };
});

const event = {
  id: 17,
  name: "Kerfuffle",
  event_date: "2026-11-18",
};
const routeSheet = {
  id: 31,
  event_id: event.id,
  name: "North route",
  capacity: null,
  registered_count: 1,
  stations: [],
};
const mainStation = {
  id: 23,
  event_id: event.id,
  name: "Main stage",
  score_min: 0,
  score_max: 10,
  score_step: 2,
  rating_mode: "main" as const,
};
const separateStation = {
  id: 24,
  event_id: event.id,
  name: "Bonus",
  score_min: 0,
  score_max: 8,
  score_step: 2,
  rating_mode: "separate" as const,
};

const leaderboard: LeaderboardResponse = {
  event,
  route_sheet_id: null,
  stations_total: 1,
  stations: [{ id: mainStation.id, name: mainStation.name, score_max: 10 }],
  participants: [{
    registration_number: "000001",
    place: 1,
    total_points: 0,
    stations_completed: 0,
    stations_total: 1,
    stations: [{ station_id: mainStation.id, name: mainStation.name, points: null, score_max: 10 }],
  }],
};

const separateLeaderboard: StationLeaderboardResponse = {
  event,
  station: {
    id: separateStation.id,
    name: separateStation.name,
    score_max: separateStation.score_max,
  },
  participants: [{
    registration_number: "000001",
    place: 1,
    points: 6,
    has_score: true,
  }],
};

const mockGetEventLeaderboard = vi.mocked(getEventLeaderboard);
const mockGetEvents = vi.mocked(getEvents);
const mockGetRouteSheets = vi.mocked(getRouteSheets);
const mockGetStationLeaderboard = vi.mocked(getStationLeaderboard);
const mockGetStations = vi.mocked(getStations);
const mockUseAuth = vi.mocked(useAuth);

beforeEach(() => {
  vi.clearAllMocks();
  window.history.pushState({}, "", "/leaderboard?eventId=17");
  mockUseAuth.mockReturnValue({
    user: {
      id: 1,
      email: "admin@example.test",
      display_name: "Admin",
      is_system_admin: true,
    },
    loading: false,
    error: "",
    login: vi.fn(),
    logout: vi.fn(),
    clearError: vi.fn(),
  });
  mockGetEvents.mockResolvedValue([event]);
  mockGetRouteSheets.mockResolvedValue([routeSheet]);
  mockGetStations.mockResolvedValue([mainStation, separateStation]);
  mockGetEventLeaderboard.mockResolvedValue(leaderboard);
  mockGetStationLeaderboard.mockResolvedValue(separateLeaderboard);
});

afterEach(cleanup);

describe("administrative leaderboards", () => {
  it("uses event names, supports route sheets, and displays participant numbers only", async () => {
    render(<App />);

    expect(await screen.findByText("№ 000001")).toBeTruthy();
    expect(screen.getByRole("option", { name: "Kerfuffle" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "North route" })).toBeTruthy();
    expect(screen.queryByText("Ada Lovelace")).toBeNull();
    expect(screen.queryByText("17")).toBeNull();

    fireEvent.change(screen.getByLabelText("Режим рейтинга"), {
      target: { value: `route:${routeSheet.id}` },
    });

    await waitFor(() => {
      expect(mockGetEventLeaderboard).toHaveBeenLastCalledWith(
        event.id,
        routeSheet.id,
        expect.any(AbortSignal),
      );
    });
  });

  it("loads the separate leaderboard for a separate-rating station", async () => {
    window.history.pushState({}, "", "/leaderboard?eventId=17&stationId=24");
    render(<App />);

    expect(await screen.findByText("Рейтинг площадки · максимум 8")).toBeTruthy();
    expect(screen.getByText("№ 000001")).toBeTruthy();
    await waitFor(() => {
      expect(mockGetStationLeaderboard).toHaveBeenLastCalledWith(
        event.id,
        separateStation.id,
        expect.any(AbortSignal),
      );
    });
  });

  it("does not fetch or display ratings for a signed-out visitor", () => {
    mockUseAuth.mockReturnValue({
      user: null,
      loading: false,
      error: "",
      login: vi.fn(),
      logout: vi.fn(),
      clearError: vi.fn(),
    });
    render(<App />);

    expect(screen.getByText("Рейтинги закрыты.")).toBeTruthy();
    expect(mockGetEvents).not.toHaveBeenCalled();
  });
});
