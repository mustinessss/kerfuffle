import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import {
  createAccessCode,
  createRouteSheet,
  createEvent,
  createStation,
  getCurrentAccount,
  getAccessCodes,
  getEvents,
  getParticipants,
  getRouteSheetsWithAccessCode,
  getRouteSheets,
  getStations,
  lookupWithAccessCode,
  registerParticipant,
  registerParticipantWithAccessCode,
  updateEvent,
  updateStation,
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
    createAccessCode: vi.fn(),
    createRouteSheet: vi.fn(),
    createStation: vi.fn(),
    getCurrentAccount: vi.fn(),
    getAccessCodes: vi.fn(),
    getEvents: vi.fn(),
    getParticipants: vi.fn(),
    getRouteSheetsWithAccessCode: vi.fn(),
    getRouteSheets: vi.fn(),
    getStations: vi.fn(),
    lookupWithAccessCode: vi.fn(),
    registerParticipant: vi.fn(),
    registerParticipantWithAccessCode: vi.fn(),
    updateEvent: vi.fn(),
    updateStation: vi.fn(),
    verifyAccessCode: vi.fn(),
  };
});

const admin = {
  id: 1,
  email: "admin@example.test",
  display_name: "Admin",
  is_system_admin: true,
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
  rating_mode: "main" as const,
};

const mockCreateEvent = vi.mocked(createEvent);
const mockCreateAccessCode = vi.mocked(createAccessCode);
const mockCreateRouteSheet = vi.mocked(createRouteSheet);
const mockCreateStation = vi.mocked(createStation);
const mockGetCurrentAccount = vi.mocked(getCurrentAccount);
const mockGetAccessCodes = vi.mocked(getAccessCodes);
const mockGetEvents = vi.mocked(getEvents);
const mockGetParticipants = vi.mocked(getParticipants);
const mockGetRouteSheetsWithAccessCode = vi.mocked(getRouteSheetsWithAccessCode);
const mockGetRouteSheets = vi.mocked(getRouteSheets);
const mockGetStations = vi.mocked(getStations);
const mockLookupWithAccessCode = vi.mocked(lookupWithAccessCode);
const mockRegisterParticipant = vi.mocked(registerParticipant);
const mockRegisterParticipantWithAccessCode = vi.mocked(registerParticipantWithAccessCode);
const mockVerifyAccessCode = vi.mocked(verifyAccessCode);
const mockUpdateEvent = vi.mocked(updateEvent);
const mockUpdateStation = vi.mocked(updateStation);
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
  mockGetAccessCodes.mockResolvedValue([]);
  mockGetEvents.mockResolvedValue([]);
  mockGetParticipants.mockResolvedValue([]);
  mockGetRouteSheetsWithAccessCode.mockResolvedValue([]);
  mockGetRouteSheets.mockResolvedValue([]);
  mockGetStations.mockResolvedValue([]);
  mockCreateEvent.mockResolvedValue(event);
  mockCreateStation.mockResolvedValue(station);
  mockCreateAccessCode.mockResolvedValue({
    id: 51,
    event_id: event.id,
    station_id: null,
    station_name: null,
    role: "registrar",
    label: "Код регистратора",
    is_active: true,
    created_at: "2026-11-18T12:00:00+00:00",
    revoked_at: null,
    code: "REG2STR8",
  });
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
  mockUpdateStation.mockResolvedValue(station);
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
  mockRegisterParticipantWithAccessCode.mockResolvedValue({
    registration_number: "000001",
  });
});

describe("WorkspacePage", () => {
  it("does not show email invitations for staff accounts", async () => {
    mockGetEvents.mockResolvedValue([event]);
    render(<WorkspacePage />);

    await screen.findByRole("heading", { name: "Мероприятия" });
    expect(screen.queryByRole("heading", { name: "Приглашение сотрудника" })).toBeNull();
    expect(screen.queryByLabelText("Email сотрудника")).toBeNull();
  });

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

  it("creates a station with a separate rating mode", async () => {
    mockGetEvents.mockResolvedValue([event]);
    mockGetStations.mockResolvedValue([station]);
    render(<WorkspacePage />);

    fireEvent.change(await screen.findByLabelText("Режим рейтинга"), {
      target: { value: "separate" },
    });
    fireEvent.change(
      screen.getByLabelText("Название", { selector: 'input[name="stationName"]' }),
      { target: { value: "Bonus" } },
    );
    fireEvent.change(screen.getByLabelText("Максимум"), {
      target: { value: "12" },
    });
    fireEvent.change(screen.getByLabelText("Шаг"), {
      target: { value: "2" },
    });
    fireEvent.submit(
      screen.getByRole("button", { name: "Добавить площадку" }).closest("form")!,
    );

    await waitFor(() => {
      expect(mockCreateStation).toHaveBeenCalledWith(event.id, "", {
        name: "Bonus",
        score_min: 0,
        score_max: 12,
        score_step: 2,
        rating_mode: "separate",
      });
    });
  });

  it("allows a system administrator to change a station rating mode", async () => {
    mockGetEvents.mockResolvedValue([event]);
    mockGetStations.mockResolvedValue([station]);
    render(<WorkspacePage />);

    fireEvent.click(await screen.findByRole("button", { name: "Настроить" }));
    fireEvent.change(screen.getAllByLabelText("Режим рейтинга")[0], {
      target: { value: "separate" },
    });
    fireEvent.submit(
      screen.getByRole("button", { name: "Сохранить" }).closest("form")!,
    );

    await waitFor(() => {
      expect(mockUpdateStation).toHaveBeenCalledWith(station.id, "", {
        name: station.name,
        score_min: station.score_min,
        score_max: station.score_max,
        score_step: station.score_step,
        rating_mode: "separate",
      });
    });
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

  it("shows stored station and registrar codes in their access cards", async () => {
    mockGetEvents.mockResolvedValue([event]);
    mockGetStations.mockResolvedValue([station]);
    mockGetAccessCodes.mockResolvedValue([
      {
        id: 52,
        event_id: event.id,
        station_id: station.id,
        station_name: station.name,
        role: "station_operator",
        label: "Код площадки",
        is_active: true,
        created_at: "2026-11-18T12:00:00+00:00",
        revoked_at: null,
        code: "STAGE2X8",
      },
      {
        id: 53,
        event_id: event.id,
        station_id: null,
        station_name: null,
        role: "registrar",
        label: "Код регистратора",
        is_active: true,
        created_at: "2026-11-18T12:00:00+00:00",
        revoked_at: null,
        code: "REG2STR8",
      },
    ]);

    render(<WorkspacePage />);

    expect(await screen.findByText("STAGE2X8", { selector: "code" })).toBeTruthy();
    expect(await screen.findByText("REG2STR8", { selector: "code" })).toBeTruthy();
    expect(screen.getByText("Площадка: Main stage")).toBeTruthy();
    expect(screen.getByText("Доступ: регистрация участников мероприятия")).toBeTruthy();
  });

  it("creates an event-scoped registrar access code", async () => {
    mockGetEvents.mockResolvedValue([event]);
    mockGetStations.mockResolvedValue([station]);

    render(<WorkspacePage />);
    fireEvent.change(await screen.findByLabelText("Тип доступа"), {
      target: { value: "registrar" },
    });
    expect(screen.queryByLabelText("Площадка")).toBeNull();
    fireEvent.change(screen.getByLabelText("Код доступа"), {
      target: { value: "REG2STR8" },
    });
    fireEvent.submit(
      screen.getByRole("button", { name: "Создать код" }).closest("form")!,
    );

    await waitFor(() => {
      expect(mockCreateAccessCode).toHaveBeenCalledWith(event.id, "", {
        role: "registrar",
        code: "REG2STR8",
        station_id: null,
      });
    });
    expect(await screen.findByText("REG2STR8", { selector: "code" })).toBeTruthy();
    expect(screen.queryByText("Сохраните код сейчас")).toBeNull();
  });
});

it("uses only short-code access for station scoring", () => {
  render(<ScoringPage />);

  expect(screen.getByLabelText("Код доступа площадки")).toBeTruthy();
  expect(screen.queryByRole("button", {
    name: "Войти через учётную запись держателя площадки",
  })).toBeNull();
});

it("shows only the participant number in station lookup results", async () => {
  mockVerifyAccessCode.mockResolvedValue({
    access_token: "station-holder-token",
    token_type: "bearer",
    expires_at: "2026-11-18T12:00:00+00:00",
    role: "station_operator",
    event_id: event.id,
    station,
  });
  mockLookupWithAccessCode.mockResolvedValue({
    event_participant_id: 41,
    registration_number: "000001",
    already_scored: false,
    score: null,
  });
  render(<ScoringPage />);

  fireEvent.change(screen.getByLabelText("Код доступа площадки"), {
    target: { value: "STAGE2X8" },
  });
  fireEvent.submit(screen.getByRole("button", { name: "Войти на площадку" }).closest("form")!);
  fireEvent.change(await screen.findByLabelText("Шестизначный номер участника"), {
    target: { value: "000001" },
  });
  fireEvent.submit(screen.getByRole("button", { name: "Найти" }).closest("form")!);

  expect(
    await screen.findByRole("heading", { name: "Номер участника 000001" }),
  ).toBeTruthy();
  expect(screen.queryByText("Alex Example")).toBeNull();
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

it("registers through an event-scoped registrar access code", async () => {
  const routeSheet = {
    id: 31,
    event_id: event.id,
    name: "North route",
    capacity: 2,
    registered_count: 0,
    stations: [{ id: station.id, name: station.name }],
  };
  mockUseAuth.mockReturnValue({
    user: null,
    loading: false,
    error: "",
    login: vi.fn(),
    logout: vi.fn(),
    clearError: vi.fn(),
  });
  mockVerifyAccessCode.mockResolvedValue({
    access_token: "registrar-access-token",
    token_type: "bearer",
    expires_at: "2026-11-18T12:00:00+00:00",
    role: "registrar",
    event_id: event.id,
    station: null,
  });
  mockGetRouteSheetsWithAccessCode.mockResolvedValue([routeSheet]);

  render(<RegistrationPage />);
  fireEvent.change(screen.getByLabelText("Код регистратора"), {
    target: { value: "REGI2TR8" },
  });
  fireEvent.submit(screen.getByRole("button", { name: "Войти как регистратор" }).closest("form")!);

  expect(await screen.findByText("North route · Main stage (0/2)")).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Имя"), { target: { value: "Alex" } });
  fireEvent.change(screen.getByLabelText("Фамилия"), { target: { value: "Example" } });
  fireEvent.change(screen.getByLabelText("Номер участника"), { target: { value: "482019" } });
  fireEvent.change(screen.getByLabelText("Маршрутный лист"), {
    target: { value: String(routeSheet.id) },
  });
  fireEvent.submit(
    screen.getByRole("button", { name: "Зарегистрировать" }).closest("form")!,
  );

  await waitFor(() => {
    expect(mockRegisterParticipantWithAccessCode).toHaveBeenCalledWith(
      "registrar-access-token",
      {
        first_name: "Alex",
        last_name: "Example",
        workplace_or_study: "",
        phone: "",
      },
      routeSheet.id,
      "482019",
    );
  });
});
