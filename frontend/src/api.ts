const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "/api/v1").replace(/\/+$/, "");
const REQUEST_TIMEOUT_MS = 10_000;

export interface LeaderboardParticipant {
  first_name: string;
  last_name: string;
  registration_number: string;
  place: number;
  total_points: number;
  stations_completed: number;
  stations_total: number;
  stations: Array<{
    station_id: number;
    name: string;
    points: number | null;
    score_max: number;
  }>;
}

export interface LeaderboardResponse {
  event: {
    id: number;
    name: string;
    event_date: string;
  };
  stations_total: number;
  stations: Array<{
    id: number;
    name: string;
    score_max: number;
  }>;
  participants: LeaderboardParticipant[];
}

export interface CurrentAccount {
  id: number;
  email: string | null;
  display_name: string;
  is_system_admin: boolean;
  is_organizer: boolean;
  access: Array<{
    event_id: number;
    role: "organizer" | "registrar" | "station_operator";
    station_id: number | null;
  }>;
}

export interface EventSummary {
  id: number;
  name: string;
  event_date: string;
}

export interface StationSummary {
  id: number;
  event_id: number;
  name: string;
  score_min: number;
  score_max: number;
  score_step: number;
}

export interface AccessCodeSummary {
  id: number;
  event_id: number;
  station_id: number | null;
  station_name: string | null;
  role: "registrar" | "station_operator";
  label: string;
  is_active: boolean;
  created_at: string;
  revoked_at: string | null;
  code?: string;
}

export interface VerifiedAccess {
  access_token: string;
  token_type: "bearer";
  expires_at: string;
  role: "registrar" | "station_operator";
  event_id: number;
  station: {
    id: number;
    name: string;
    score_min: number;
    score_max: number;
    score_step: number;
  } | null;
}

export interface CreatedOrganizer {
  id: number;
  username: string;
  display_name: string;
  email: string | null;
  temporary_password: string;
  must_change_password: true;
}

export interface RegisteredParticipant {
  id: number;
  event_id: number;
  person_id: number;
  first_name: string;
  last_name: string;
  registration_number: string;
  qr_token: string;
  registered_at: string;
}

export interface ParticipantLookup {
  event_participant_id: number;
  registration_number: string;
  first_name: string;
  last_name: string;
  already_scored: boolean;
  score: ScoreRecord | null;
}

export interface ScoreRecord {
  id: number;
  event_participant_id: number;
  station_id: number;
  points: number;
  is_annulled: boolean;
}

export interface ScoreHistoryEntry extends ScoreRecord {
  registration_number: string;
  first_name: string;
  last_name: string;
  station_name: string;
  created_at: string;
  history: Array<{
    id: number;
    action: "correction" | "annulment";
    points_before: number;
    points_after: number;
    reason: string;
    changed_by: string;
    created_at: string;
  }>;
}

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

interface RequestOptions {
  signal?: AbortSignal;
  accessToken?: string;
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
}

async function requestJson<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const abortRequest = () => controller.abort();
  options.signal?.addEventListener("abort", abortRequest, { once: true });

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: options.method ?? "GET",
      headers: {
        Accept: "application/json",
        ...(options.body === undefined ? {} : { "Content-Type": "application/json" }),
        ...(options.accessToken ? { Authorization: `Bearer ${options.accessToken}` } : {}),
      },
      ...(options.body === undefined ? {} : { body: JSON.stringify(options.body) }),
      signal: controller.signal,
    });

    if (!response.ok) {
      const message = response.status === 401
          ? "Сессия завершилась. Войдите снова."
          : response.status === 400
            ? "Код доступа неверен или отключён."
          : response.status === 403
            ? "У вашей учётной записи нет доступа к этому действию."
            : response.status === 404
              ? "Мероприятие, площадка или участник не найдены."
              : response.status === 409
                ? "Действие уже выполнено или конфликтует с существующими данными."
                : response.status === 422
                  ? "Проверьте введённые данные и ограничения площадки."
        : response.status === 429
          ? "Слишком много попыток. Подождите и попробуйте снова."
        : response.status >= 500
          ? "Сервис временно недоступен. Попробуйте позже."
          : "Не удалось загрузить данные мероприятия.";
      throw new ApiError(response.status, message);
    }
    return await response.json() as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (controller.signal.aborted) {
      throw new ApiError(0, options.signal?.aborted ? "Запрос отменён." : "Сервис не ответил вовремя. Попробуйте ещё раз.");
    }
    throw new ApiError(0, "Не удалось связаться с сервером. Проверьте подключение.");
  } finally {
    window.clearTimeout(timeoutId);
    options.signal?.removeEventListener("abort", abortRequest);
  }
}

export function getPublicLeaderboard(eventId: number, signal?: AbortSignal) {
  return requestJson<LeaderboardResponse>(
    `/public/events/${encodeURIComponent(eventId)}/leaderboard`,
    { signal },
  );
}

export function getCurrentAccount(accessToken: string, signal?: AbortSignal) {
  return requestJson<CurrentAccount>("/me", { accessToken, signal });
}

export function getEvents(accessToken: string, signal?: AbortSignal) {
  return requestJson<EventSummary[]>("/events", { accessToken, signal });
}

export function createEvent(
  accessToken: string,
  payload: Pick<EventSummary, "name" | "event_date">,
) {
  return requestJson<EventSummary>("/events", {
    accessToken,
    method: "POST",
    body: payload,
  });
}

export function getStations(eventId: number, accessToken: string, signal?: AbortSignal) {
  return requestJson<StationSummary[]>(`/events/${eventId}/stations`, { accessToken, signal });
}

export function createStation(
  eventId: number,
  accessToken: string,
  payload: Pick<StationSummary, "name" | "score_min" | "score_max" | "score_step">,
) {
  return requestJson<StationSummary>(`/events/${eventId}/stations`, {
    accessToken,
    method: "POST",
    body: payload,
  });
}

export function createOrganizer(
  accessToken: string,
  payload: { username: string; display_name: string; email?: string },
) {
  return requestJson<CreatedOrganizer>("/system-admin/organizers", {
    accessToken,
    method: "POST",
    body: payload,
  });
}

export function getAccessCodes(eventId: number, accessToken: string, signal?: AbortSignal) {
  return requestJson<AccessCodeSummary[]>(`/events/${eventId}/access-codes`, {
    accessToken,
    signal,
  });
}

export function createAccessCode(
  eventId: number,
  accessToken: string,
  payload: { role: AccessCodeSummary["role"]; code: string; station_id: number | null },
) {
  return requestJson<AccessCodeSummary>(`/events/${eventId}/access-codes`, {
    accessToken,
    method: "POST",
    body: payload,
  });
}

export function revokeAccessCode(codeId: number, accessToken: string) {
  return requestJson<AccessCodeSummary>(`/access-codes/${codeId}`, {
    accessToken,
    method: "DELETE",
  });
}

export function verifyAccessCode(code: string) {
  return requestJson<VerifiedAccess>("/public/access/verify", {
    method: "POST",
    body: { code },
  });
}

export function registerWithAccessCode(
  accessToken: string,
  person: { first_name: string; last_name: string },
) {
  return requestJson<RegisteredParticipant>("/public/access/register", {
    accessToken,
    method: "POST",
    body: { person },
  });
}

export function lookupWithAccessCode(accessToken: string, registrationNumber: string) {
  return requestJson<ParticipantLookup>("/public/access/participant-lookup", {
    accessToken,
    method: "POST",
    body: { registration_number: registrationNumber },
  });
}

export function submitScoreWithAccessCode(
  accessToken: string,
  eventParticipantId: number,
  points: number,
) {
  return requestJson<ScoreRecord>("/public/access/scores", {
    accessToken,
    method: "POST",
    body: { event_participant_id: eventParticipantId, points },
  });
}

export function updateStation(
  stationId: number,
  accessToken: string,
  payload: Partial<Pick<StationSummary, "name" | "score_min" | "score_max" | "score_step">>,
) {
  return requestJson<StationSummary>(`/stations/${stationId}`, {
    accessToken,
    method: "PATCH",
    body: payload,
  });
}

export async function getParticipants(
  eventId: number,
  accessToken: string,
  signal?: AbortSignal,
) {
  const participants: RegisteredParticipant[] = [];
  const pageSize = 200;
  for (let offset = 0; ; offset += pageSize) {
    const page = await requestJson<RegisteredParticipant[]>(
      `/events/${eventId}/participants?limit=${pageSize}&offset=${offset}`,
      { accessToken, signal },
    );
    participants.push(...page);
    if (page.length < pageSize) return participants;
  }
}

export function registerParticipant(
  eventId: number,
  accessToken: string,
  person: { first_name: string; last_name: string },
) {
  return requestJson<RegisteredParticipant>(`/events/${eventId}/participants`, {
    accessToken,
    method: "POST",
    body: { person },
  });
}

export function lookupParticipant(
  stationId: number,
  accessToken: string,
  registrationNumber: string,
) {
  return requestJson<ParticipantLookup>(`/stations/${stationId}/participants/lookup`, {
    accessToken,
    method: "POST",
    body: { registration_number: registrationNumber },
  });
}

export function submitScore(
  stationId: number,
  accessToken: string,
  eventParticipantId: number,
  points: number,
) {
  return requestJson<ScoreRecord>(`/stations/${stationId}/scores`, {
    accessToken,
    method: "POST",
    body: { event_participant_id: eventParticipantId, points },
  });
}

export function getEventScores(
  eventId: number,
  accessToken: string,
  signal?: AbortSignal,
) {
  return requestJson<ScoreHistoryEntry[]>(`/events/${eventId}/scores`, {
    accessToken,
    signal,
  });
}

export function correctScore(
  scoreId: number,
  accessToken: string,
  points: number,
  reason: string,
) {
  return requestJson<ScoreRecord>(`/scores/${scoreId}`, {
    accessToken,
    method: "PATCH",
    body: { points, reason },
  });
}

export function annulScore(scoreId: number, accessToken: string, reason: string) {
  return requestJson<ScoreRecord>(`/scores/${scoreId}/annul`, {
    accessToken,
    method: "POST",
    body: { reason },
  });
}
