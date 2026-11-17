import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import {
  createEvent,
  getCurrentAccount,
  getEvents,
  getParticipants,
  getRouteSheets,
  getRouteSheetsWithAccessCode,
  getStations,
  registerWithAccessCode,
  verifyAccessCode,
} from "./api";
import { useAuth } from "./authContext";
import { OrganizerPage, RegistrationPage, ScoringPage } from "./WorkspacePages";

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
    getRouteSheets: vi.fn(),
    getRouteSheetsWithAccessCode: vi.fn(),
    getStations: vi.fn(),
    registerWithAccessCode: vi.fn(),
    verifyAccessCode: vi.fn(),
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
const mockGetRouteSheets = vi.mocked(getRouteSheets);
const mockGetRouteSheetsWithAccessCode = vi.mocked(getRouteSheetsWithAccessCode);
const mockGetStations = vi.mocked(getStations);
const mockRegisterWithAccessCode = vi.mocked(registerWithAccessCode);
const mockVerifyAccessCode = vi.mocked(verifyAccessCode);
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
  mockGetRouteSheets.mockResolvedValue([]);
  mockGetRouteSheetsWithAccessCode.mockResolvedValue([]);
  mockGetStations.mockResolvedValue([]);
  mockCreateEvent.mockResolvedValue(event);
  mockVerifyAccessCode.mockResolvedValue({
    access_token: "registrar-token",
    token_type: "bearer",
    expires_at: "2026-11-18T12:00:00+00:00",
    role: "registrar",
    event_id: event.id,
    station: null,
  });
  mockRegisterWithAccessCode.mockResolvedValue({
    id: 41,
    event_id: event.id,
    person_id: 42,
    first_name: "Alex",
    last_name: "Example",
    registration_number: "000001",
    route_sheet_id: 31,
    route_sheet_name: "North route",
    registered_at: "2026-11-18T12:00:00+00:00",
  });
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

it("assigns the route sheet selected by a registrar during registration", async () => {
  const routeSheet = {
    id: 31,
    event_id: event.id,
    name: "North route",
    capacity: 2,
    registered_count: 0,
    stations: [{ id: station.id, name: station.name }],
  };
  mockGetRouteSheetsWithAccessCode.mockResolvedValue([routeSheet]);

  render(<RegistrationPage />);
  fireEvent.change(screen.getByLabelText("Код регистрации"), {
    target: { value: "REGISTRAR1" },
  });
  fireEvent.submit(screen.getByRole("button", { name: "Продолжить" }).closest("form")!);

  expect(await screen.findByRole("option", { name: "North route (0/2)" })).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Имя"), { target: { value: "Alex" } });
  fireEvent.change(screen.getByLabelText("Фамилия"), { target: { value: "Example" } });
  fireEvent.change(screen.getByLabelText("Маршрутный лист"), {
    target: { value: String(routeSheet.id) },
  });
  fireEvent.submit(
    screen.getByRole("button", { name: "Зарегистрировать" }).closest("form")!,
  );

  await waitFor(() => {
    expect(mockRegisterWithAccessCode).toHaveBeenCalledWith(
      "registrar-token",
      { first_name: "Alex", last_name: "Example" },
      routeSheet.id,
    );
  });
  expect(await screen.findByText("Маршрутный лист: North route")).toBeTruthy();
});
