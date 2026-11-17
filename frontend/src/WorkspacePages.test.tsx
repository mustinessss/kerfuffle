import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createEvent, getCurrentAccount, getEvents, getParticipants, getStations } from "./api";
import { useAuth } from "./authContext";
import { OrganizerPage, ScoringPage } from "./WorkspacePages";

vi.mock("./authContext", () => ({
  useAuth: vi.fn(),
}));

vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  return {
    ...actual,
    createEvent: vi.fn(),
    getCurrentAccount: vi.fn(),
    getEvents: vi.fn(),
    getParticipants: vi.fn(),
    getStations: vi.fn(),
  };
});

const admin = {
  id: 1,
  email: "admin@example.test",
  display_name: "Admin",
  is_system_admin: true,
  is_organizer: true,
  access: [],
};

const event = {
  id: 17,
  name: "Test event",
  event_date: "2026-11-18",
};

const station = {
  id: 23,
  event_id: event.id,
  name: "Main stage",
  score_min: 0,
  score_max: 10,
  score_step: 2,
};

const mockCreateEvent = vi.mocked(createEvent);
const mockGetCurrentAccount = vi.mocked(getCurrentAccount);
const mockGetEvents = vi.mocked(getEvents);
const mockGetParticipants = vi.mocked(getParticipants);
const mockGetStations = vi.mocked(getStations);
const mockUseAuth = vi.mocked(useAuth);

afterEach(cleanup);

beforeEach(() => {
  vi.clearAllMocks();
  mockUseAuth.mockReturnValue({
    user: admin,
    loading: false,
    error: "",
    login: vi.fn(),
    logout: vi.fn(),
    clearError: vi.fn(),
  });
  mockGetCurrentAccount.mockResolvedValue(admin);
  mockGetEvents.mockResolvedValue([]);
  mockGetParticipants.mockResolvedValue([]);
  mockGetStations.mockResolvedValue([]);
  mockCreateEvent.mockResolvedValue(event);
});

describe("OrganizerPage", () => {
  it("creates an event using the cookie-authenticated API", async () => {
    render(<OrganizerPage />);
    await screen.findByRole("heading", { name: /Новое мероприятие/ });

    fireEvent.change(screen.getByLabelText("Название"), {
      target: { value: event.name },
    });
    fireEvent.change(screen.getByLabelText("Дата"), {
      target: { value: event.event_date },
    });
    fireEvent.submit(
      screen.getByRole("button", { name: "Создать мероприятие" }).closest("form")!,
    );

    await waitFor(() => {
      expect(mockCreateEvent).toHaveBeenCalledWith({
        name: event.name,
        event_date: event.event_date,
      });
    });
    expect(await screen.findByText("Мероприятие создано.")).toBeTruthy();
  });

  it("does not render event creation for an unauthenticated user", () => {
    mockUseAuth.mockReturnValue({
      user: null,
      loading: false,
      error: "",
      login: vi.fn(),
      logout: vi.fn(),
      clearError: vi.fn(),
    });

    render(<OrganizerPage />);

    expect(screen.queryByRole("button", { name: "Создать мероприятие" })).toBeNull();
    expect(mockCreateEvent).not.toHaveBeenCalled();
  });
});

it("loads assigned stations in account-based scoring without a bearer token", async () => {
  mockGetEvents.mockResolvedValue([event]);
  mockGetStations.mockResolvedValue([station]);

  render(<ScoringPage />);
  fireEvent.click(
    screen.getByRole("button", {
      name: "Войти через учётную запись организации",
    }),
  );

  expect(await screen.findByRole("option", { name: "Main stage" })).toBeTruthy();
  expect(mockGetStations).toHaveBeenCalledWith(
    event.id,
    "",
    expect.any(AbortSignal),
  );
});
