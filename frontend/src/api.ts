const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "/api/v1").replace(/\/+$/, "");
const REQUEST_TIMEOUT_MS = 10_000;

export interface LeaderboardParticipant {
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
  route_sheet_id: number | null;
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
  access: Array<{
    event_id: number;
    role: "station_operator";
    station_id: number | null;
  }>;
}

export interface EventSummary {
  id: number;
  name: string;
  event_date: string;
}

export interface PublicEventSummary extends EventSummary {
  route_sheets: Array<{ id: number; name: string }>;
}

export interface StationSummary {
  id: number;
  event_id: number;
  name: string;
  score_min: number;
  score_max: number;
  score_step: number;
}

export interface RouteSheetSummary {
  id: number;
  event_id: number;
  name: string;
  capacity: number | null;
  registered_count: number;
  stations: Array<{ id: number; name: string }>;
}

export interface AccessCodeSummary {
  id: number;
  event_id: number;
  station_id: number | null;
  station_name: string | null;
  role: "station_operator";
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
  role: "station_operator";
  event_id: number;
  station: {
    id: number;
    name: string;
    score_min: number;
    score_max: number;
    score_step: number;
  } | null;
}

export interface CreatedInvitation {
  id: number;
  email: string;
  status: "sent" | "pending";
  expires_at: string;
  invitation_url: string | null;
  delivery_method: "email" | "manual";
}

export interface AdminUser extends CurrentAccount {
  is_active: boolean;
  last_login_at: string | null;
  events: Array<{ event_id: number; role: "station_operator"; station_id: number }>;
}

export interface AdminInvitation {
  id: number;
  email: string;
  status: "sent" | "pending" | "expired" | "used" | "revoked";
  created_at: string;
  expires_at: string;
  sent_at: string | null;
}

export interface RegisteredParticipant {
  id: number;
  event_id: number;
  person_id: number;
  first_name: string;
  last_name: string;
  registration_number: string;
  route_sheet_id: number | null;
  route_sheet_name: string | null;
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
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
}

async function requestJson<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const abortRequest = () => controller.abort();
  options.signal?.addEventListener("abort", abortRequest, { once: true });

  try {
    const csrfToken = document.cookie
      .split("; ")
      .find((cookie) => cookie.startsWith("kerfuffle_csrf="))
      ?.slice("kerfuffle_csrf=".length);
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: options.method ?? "GET",
      headers: {
        Accept: "application/json",
        ...(options.body === undefined ? {} : { "Content-Type": "application/json" }),
        ...(options.accessToken ? { Authorization: `Bearer ${options.accessToken}` } : {}),
        ...(options.method && options.method !== "GET" && csrfToken ? { "X-CSRF-Token": decodeURIComponent(csrfToken) } : {}),
      },
      ...(options.body === undefined ? {} : { body: JSON.stringify(options.body) }),
      credentials: "include",
      signal: controller.signal,
    });

    if (!response.ok) {
      const message = response.status === 401 && path.endsWith("/auth/login")
          ? "Проверьте email и пароль."
        : response.status === 401
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
    if (response.status === 204 || response.headers.get("content-length") === "0") {
      return undefined as T;
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

export function getPublicEvents(signal?: AbortSignal) {
  return requestJson<PublicEventSummary[]>("/public/events", { signal });
}

export function getPublicLeaderboard(
  eventId: number,
  routeSheetId?: number,
  signal?: AbortSignal,
) {
  const query = routeSheetId === undefined
    ? ""
    : `?route_sheet_id=${encodeURIComponent(routeSheetId)}`;
  return requestJson<LeaderboardResponse>(
    `/public/events/${encodeURIComponent(eventId)}/leaderboard${query}`,
    { signal },
  );
}

export function getCurrentAccount(accessToken = "", signal?: AbortSignal) {
  return requestJson<CurrentAccount>("/auth/me", { accessToken, signal });
}

export function loginWithPassword(email: string, password: string) {
  return requestJson<CurrentAccount>("/auth/login", {
    method: "POST",
    body: { email, password },
  });
}

export function logoutFromAccount() {
  return requestJson<{ ok: boolean }>("/auth/logout", { method: "POST", body: {} });
}

export function acceptAccountInvitation(payload: { token: string; display_name: string; password: string }) {
  return requestJson<{ ok: boolean; email: string }>("/public/invitations/accept", {
    method: "POST",
    body: payload,
  });
}

export function requestPasswordReset(email: string) {
  return requestJson<{ ok: boolean }>("/public/password-reset/request", {
    method: "POST",
    body: { email },
  });
}

export function completePasswordReset(payload: { token: string; password: string }) {
  return requestJson<{ ok: boolean }>("/public/password-reset/complete", {
    method: "POST",
    body: payload,
  });
}

export function getAdminUsers(signal?: AbortSignal) {
  return requestJson<AdminUser[]>("/system-admin/users", { signal });
}

export function getAdminInvitations(signal?: AbortSignal) {
  return requestJson<AdminInvitation[]>("/system-admin/invitations", { signal });
}

export function inviteStaffAccount(email: string) {
  return requestJson<CreatedInvitation>("/system-admin/invitations", {
    method: "POST",
    body: { email },
  });
}

export function revokeInvitation(invitationId: number) {
  return requestJson<{ ok: boolean }>(`/system-admin/invitations/${invitationId}/revoke`, {
    method: "POST",
    body: {},
  });
}

export function resendInvitation(invitationId: number) {
  return requestJson<CreatedInvitation>(`/system-admin/invitations/${invitationId}/resend`, {
    method: "POST",
    body: {},
  });
}

export function setUserBlocked(userId: number, blocked: boolean) {
  return requestJson<{ ok: boolean }>(`/system-admin/users/${userId}/${blocked ? "block" : "unblock"}`, {
    method: "POST",
    body: {},
  });
}

export function createManualPasswordResetLink(userId: number) {
  return requestJson<{ reset_url: string; expires_in_minutes: number }>(
    `/system-admin/users/${userId}/password-reset-link`,
    { method: "POST", body: {} },
  );
}

export function setUserStationAccess(
  userId: number,
  eventId: number,
  stationId: number,
  assigned: boolean,
) {
  return requestJson<{ ok: boolean }>(
    `/system-admin/users/${userId}/events/${eventId}/stations/${stationId}`,
    {
      method: assigned ? "PUT" : "DELETE",
      body: assigned ? {} : undefined,
    },
  );
}

export function getEvents(accessToken = "", signal?: AbortSignal) {
  return requestJson<EventSummary[]>("/events", { accessToken, signal });
}

export function createEvent(
  payload: Pick<EventSummary, "name" | "event_date">,
) {
  return requestJson<EventSummary>("/events", {
    method: "POST",
    body: payload,
  });
}

export function updateEvent(
  eventId: number,
  payload: Pick<EventSummary, "name" | "event_date">,
) {
  return requestJson<EventSummary>(`/events/${eventId}`, {
    method: "PATCH",
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

export function getRouteSheets(
  eventId: number,
  accessToken: string,
  signal?: AbortSignal,
) {
  return requestJson<RouteSheetSummary[]>(`/events/${eventId}/route-sheets`, {
    accessToken,
    signal,
  });
}

export function createRouteSheet(
  eventId: number,
  accessToken: string,
  payload: { name: string; capacity: number | null; station_ids: number[] },
) {
  return requestJson<RouteSheetSummary>(`/events/${eventId}/route-sheets`, {
    accessToken,
    method: "POST",
    body: payload,
  });
}

export function updateRouteSheet(
  routeSheetId: number,
  accessToken: string,
  payload: { name: string; capacity: number | null; station_ids: number[] },
) {
  return requestJson<RouteSheetSummary>(`/route-sheets/${routeSheetId}`, {
    accessToken,
    method: "PATCH",
    body: payload,
  });
}

export function deleteRouteSheet(routeSheetId: number, accessToken: string) {
  return requestJson<{ ok: boolean }>(`/route-sheets/${routeSheetId}`, {
    accessToken,
    method: "DELETE",
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
  person: {
    first_name: string;
    last_name: string;
    workplace_or_study: string;
    phone: string;
  },
  routeSheetId: number | null,
  registrationNumber: string,
) {
  return requestJson<RegisteredParticipant>(`/events/${eventId}/participants`, {
    accessToken,
    method: "POST",
    body: {
      person,
      route_sheet_id: routeSheetId,
      registration_number: registrationNumber,
    },
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
