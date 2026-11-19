import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import {
  createRouteSheet,
  createEvent,
  getCurrentAccount,
  getEvents,
  getParticipants,
  getRouteSheets,
  getStations,
  registerParticipant,
  updateEvent,
  verifyAccessCode,
} from "./api";
import { useAuth } from "./authContext";
import { RegistrationPage, ScoringPage, WorkspacePage } from "./WorkspacePages";

vi.mock("./authContext", () => ({
  useAuth: vi.fn(),
}));

vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  return {
    ...actual,
    createEvent: vi.fn(),
    createRouteSheet: vi.fn(),
    getCurrentAccount: vi.fn(),
    getEvents: vi.fn(),
    getParticipants: vi.fn(),
    getRouteSheets: vi.fn(),
    getStations: vi.fn(),
    registerParticipant: vi.fn(),
    updateEvent: vi.fn(),
    verifyAccessCode: vi.fn(),
  };
});

const admin = {
  id: 1,
  email: "admin@example.test",
  display_name: "Admin",
  is_system_admin: true,
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
const mockCreateRouteSheet = vi.mocked(createRouteSheet);
const mockGetCurrentAccount = vi.mocked(getCurrentAccount);
const mockGetEvents = vi.mocked(getEvents);
const mockGetParticipants = vi.mocked(getParticipants);
const mockGetRouteSheets = vi.mocked(getRouteSheets);
const mockGetStations = vi.mocked(getStations);
const mockRegisterParticipant = vi.mocked(registerParticipant);
const mockVerifyAccessCode = vi.mocked(verifyAccessCode);
const mockUpdateEvent = vi.mocked(updateEvent);
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
  mockGetStations.mockResolvedValue([]);
  mockCreateEvent.mockResolvedValue(event);
  mockCreateRouteSheet.mockResolvedValue({
    id: 31,
    event_id: event.id,
    name: "North route",
    capacity: null,
    registered_count: 0,
    stations: [{ id: station.id, name: station.name }],
  });
  mockVerifyAccessCode.mockResolvedValue({
    access_token: "station-holder-token",
    token_type: "bearer",
    expires_at: "2026-11-18T12:00:00+00:00",
    role: "station_operator",
    event_id: event.id,
    station: null,
  });
  mockUpdateEvent.mockResolvedValue(event);
  mockRegisterParticipant.mockResolvedValue({
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

describe("WorkspacePage", () => {
  it("creates an event using the cookie-authenticated API", async () => {
    render(<WorkspacePage />);
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

  it("allows a system administrator to update the selected event", async () => {
    mockGetEvents.mockResolvedValue([event]);
    render(<WorkspacePage />);
    fireEvent.change(await screen.findByLabelText("Название мероприятия"), {
      target: { value: "Updated event" },
    });
    fireEvent.submit(
      screen.getByRole("button", { name: "Сохранить мероприятие" }).closest("form")!,
    );

    await waitFor(() => {
      expect(mockUpdateEvent).toHaveBeenCalledWith(event.id, {
        name: "Updated event",
        event_date: event.event_date,
      });
    });
    expect(await screen.findByText("Мероприятие обновлено.")).toBeTruthy();
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

    render(<WorkspacePage />);

    expect(screen.queryByRole("button", { name: "Создать мероприятие" })).toBeNull();
    expect(mockCreateEvent).not.toHaveBeenCalled();
  });

  it("selects only checked stations when creating a route sheet", async () => {
    const secondStation = { ...station, id: 24, name: "Side stage" };
    mockGetEvents.mockResolvedValue([event]);
    mockGetStations.mockResolvedValue([station, secondStation]);

    render(<WorkspacePage />);
    await screen.findByRole("checkbox", { name: "Main stage" });

    fireEvent.click(screen.getByRole("button", { name: "Выбрать все" }));
    expect(screen.getByText("Площадки · выбрано 2")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Снять все" }));
    expect(screen.getByText("Площадки · выбрано 0")).toBeTruthy();
    fireEvent.click(screen.getByRole("checkbox", { name: "Side stage" }));
    fireEvent.change(screen.getByLabelText("Название маршрутного листа"), {
      target: { value: "Only side" },
    });
    fireEvent.submit(
      screen.getByRole("button", { name: "Создать маршрутный лист" }).closest("form")!,
    );

    await waitFor(() => {
      expect(mockCreateRouteSheet).toHaveBeenCalledWith(event.id, "", {
        name: "Only side",
        capacity: null,
        station_ids: [secondStation.id],
      });
    });
  });
});

it("loads assigned stations in account-based scoring without a bearer token", async () => {
  mockGetEvents.mockResolvedValue([event]);
  mockGetStations.mockResolvedValue([station]);

  render(<ScoringPage />);
  fireEvent.click(
    screen.getByRole("button", {
      name: "Войти через учётную запись держателя площадки",
    }),
  );

  expect(await screen.findByRole("option", { name: "Main stage" })).toBeTruthy();
  expect(mockGetStations).toHaveBeenCalledWith(
    event.id,
    "",
    expect.any(AbortSignal),
  );
});

it("registers a participant with a manual six-digit number and personal fields", async () => {
  const routeSheet = {
    id: 31,
    event_id: event.id,
    name: "North route",
    capacity: 2,
    registered_count: 0,
    stations: [{ id: station.id, name: station.name }],
  };
  mockGetEvents.mockResolvedValue([event]);
  mockGetRouteSheets.mockResolvedValue([routeSheet]);

  render(<RegistrationPage />);
  expect(await screen.findByRole("option", { name: /North route.*0\/2/ })).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Имя"), { target: { value: "Alex" } });
  fireEvent.change(screen.getByLabelText("Фамилия"), { target: { value: "Example" } });
  fireEvent.change(screen.getByLabelText("Номер участника"), { target: { value: "482019" } });
  fireEvent.change(screen.getByLabelText("Место работы/учёбы"), { target: { value: "Example school" } });
  fireEvent.change(screen.getByLabelText("Номер телефона"), { target: { value: "+70000000000" } });
  fireEvent.change(screen.getByLabelText("Маршрутный лист"), {
    target: { value: String(routeSheet.id) },
  });
  fireEvent.submit(
    screen.getByRole("button", { name: "Зарегистрировать" }).closest("form")!,
  );

  await waitFor(() => {
    expect(mockRegisterParticipant).toHaveBeenCalledWith(
      event.id,
      "",
      {
        first_name: "Alex",
        last_name: "Example",
        workplace_or_study: "Example school",
        phone: "+70000000000",
      },
      routeSheet.id,
      "482019",
    );
  });
  const status = await screen.findByRole("status");
  expect(status.textContent).toContain("000001");
});
