import { useEffect, useState } from "react";
import {
  ApiError,
  getEventLeaderboard,
  getEvents,
  getRouteSheets,
  getStationLeaderboard,
  getStations,
  type LeaderboardResponse,
  type EventSummary,
  type RouteSheetSummary,
  type StationLeaderboardResponse,
  type StationSummary,
} from "./api";
import { useAuth } from "./authContext";
import { RegistrationPage, ScoringPage, WorkspacePage } from "./WorkspacePages";
import {
  ForgotPasswordPage,
  LoginPage,
  ResetPasswordPage,
} from "./AccountPages";
import "./styles.css";

type Page = "home" | "leaderboard" | "registration" | "scoring" | "workspace" | "login" | "forgot-password" | "reset-password";

function currentPage(): Page {
  const path = window.location.pathname.replace(/\/+$/, "");
  if (path === "/leaderboard") return "leaderboard";
  if (path === "/register") return "registration";
  if (path === "/score") return "scoring";
  if (path === "/workspace") return "workspace";
  if (path === "/login") return "login";
  if (path === "/forgot-password") return "forgot-password";
  if (path === "/reset-password") return "reset-password";
  return "home";
}

function eventIdFromUrl(): string {
  return new URLSearchParams(window.location.search).get("eventId") ?? "";
}

function App() {
  const page = currentPage();
  const { user } = useAuth();

  return (
    <div className="app-shell">
      <header className="site-header">
        <a className="wordmark" href="/" aria-label="Kerfuffle — главная">
          <span className="wordmark-mark" aria-hidden="true">k.</span>
          <span>kerfuffle</span>
        </a>
        <nav className="header-nav" aria-label="Основная навигация">
          <a href="/leaderboard">Рейтинг</a>
          <a href={user ? "/workspace" : "/login"}>{user ? "Кабинет" : "Войти"} <span aria-hidden="true">↗</span></a>
        </nav>
      </header>

      {page === "home" && (
        <main className="home-page">
          <section className="home-intro">
            <p className="eyebrow">ВСТРЕЧАЙТЕСЬ · ИГРАЙТЕ · ОТКРЫВАЙТЕ</p>
            <h1>Сервис для проведения<br /><em>мероприятий</em></h1>
            <p className="intro-copy">Регистрация, задания на площадках и результаты — в одном месте.</p>
          </section>

          <section className="action-list" aria-label="Действия участника">
            <a className="action-card action-register" href="/register">
              <span className="action-number">01</span>
              <span className="action-copy"><strong>Регистрация участника</strong><small>Получите номер для участия в событии</small></span>
              <span className="action-arrow" aria-hidden="true">↗</span>
            </a>
            <a className="action-card action-score" href="/score">
              <span className="action-number">02</span>
              <span className="action-copy"><strong>Ввод баллов</strong><small>Рабочее место сотрудника площадки</small></span>
              <span className="action-arrow" aria-hidden="true">↗</span>
            </a>
            <a className="action-card action-board" href="/leaderboard">
              <span className="action-number">03</span>
              <span className="action-copy"><strong>Рейтинги</strong><small>Общий, по маршрутным листам и площадкам</small></span>
              <span className="action-arrow" aria-hidden="true">↗</span>
            </a>
          </section>

          <p className="home-note">Системный администратор? <a href="/workspace">Рабочее пространство</a></p>
        </main>
      )}

      {page === "leaderboard" && <LeaderboardPage />}
      {page === "registration" && <RegistrationPage />}
      {page === "scoring" && <ScoringPage />}
      {page === "workspace" && <WorkspacePage />}
      {page === "login" && <LoginPage />}
      {page === "forgot-password" && <ForgotPasswordPage />}
      {page === "reset-password" && <ResetPasswordPage />}

      <footer className="site-footer">
        <a className="footer-brand" href="/">mustiness</a>
        <span>СОБЫТИЯ, КОТОРЫЕ ОБЪЕДИНЯЮТ</span>
        <span>© 2026</span>
      </footer>
    </div>
  );
}

function LeaderboardPage() {
  const { user, loading: authLoading } = useAuth();
  const [data, setData] = useState<LeaderboardResponse | StationLeaderboardResponse | null>(null);
  const [events, setEvents] = useState<EventSummary[]>([]);
  const [routeSheets, setRouteSheets] = useState<RouteSheetSummary[]>([]);
  const [stations, setStations] = useState<StationSummary[]>([]);
  const [selectedEventId, setSelectedEventId] = useState(eventIdFromUrl());
  const [selectedMode, setSelectedMode] = useState(modeFromUrl());
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [loadedQuery, setLoadedQuery] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [eventsLoaded, setEventsLoaded] = useState(false);
  const [detailsSettledEventId, setDetailsSettledEventId] = useState<number | null>(null);
  const [loadedEventId, setLoadedEventId] = useState<number | null>(null);
  const currentEvent = events.find((item) => String(item.id) === selectedEventId) ?? null;
  const eventsLoading = authLoading || (user?.is_system_admin === true && !eventsLoaded);
  const detailsLoading = Boolean(
    currentEvent && detailsSettledEventId !== currentEvent.id,
  );
  const modeParts = selectedMode.split(":");
  const selectedRouteSheetId = modeParts[0] === "route" ? Number(modeParts[1]) : undefined;
  const selectedStationId = modeParts[0] === "station" ? Number(modeParts[1]) : undefined;
  const queryKey = `${selectedEventId}:${selectedMode || "all"}`;
  const validSelection = currentEvent !== null
    && loadedEventId === currentEvent.id
    && (selectedRouteSheetId === undefined
      || routeSheets.some((sheet) => sheet.id === selectedRouteSheetId))
    && (selectedStationId === undefined
      || stations.some((station) => (
        station.id === selectedStationId && station.rating_mode === "separate"
      )));

  useEffect(() => {
    if (authLoading) return;
    if (!user?.is_system_admin) {
      return;
    }
    const controller = new AbortController();
    getEvents("", controller.signal)
      .then((result) => {
        setEvents(result);
        const preferredEventId = eventIdFromUrl();
        const activeEventId = result.some((item) => String(item.id) === preferredEventId)
          ? preferredEventId
          : String(result[0]?.id ?? "");
        setSelectedEventId(activeEventId);
      })
      .catch((requestError: unknown) => {
        if (!controller.signal.aborted) {
          setError(requestError instanceof ApiError
            ? requestError.message
            : "Не удалось загрузить список мероприятий.");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setEventsLoaded(true);
      });
    return () => controller.abort();
  }, [authLoading, user]);

  useEffect(() => {
    if (!user?.is_system_admin || !currentEvent) return;
    const controller = new AbortController();
    Promise.all([
      getRouteSheets(currentEvent.id, "", controller.signal),
      getStations(currentEvent.id, "", controller.signal),
    ])
      .then(([nextRouteSheets, nextStations]) => {
        setRouteSheets(nextRouteSheets);
        setStations(nextStations);
        setLoadedEventId(currentEvent.id);
        setSelectedMode((currentMode) => {
          const [kind, id] = currentMode.split(":");
          const selectedId = Number(id);
          if (kind === "route" && nextRouteSheets.some((sheet) => sheet.id === selectedId)) {
            return currentMode;
          }
          if (kind === "station" && nextStations.some((station) => (
            station.id === selectedId && station.rating_mode === "separate"
          ))) {
            return currentMode;
          }
          return "";
        });
      })
      .catch((requestError: unknown) => {
        if (!controller.signal.aborted) {
          setRouteSheets([]);
          setStations([]);
          setError(requestError instanceof ApiError
            ? requestError.message
            : "Не удалось загрузить площадки и маршрутные листы.");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setDetailsSettledEventId(currentEvent.id);
      });
    return () => controller.abort();
  }, [currentEvent, user]);

  useEffect(() => {
    if (!validSelection) return;

    let active = true;
    let controller: AbortController | undefined;
    let pending = false;
    let hasSuccessfulResponse = false;
    const refresh = async (initial: boolean) => {
      if (pending) return;
      pending = true;
      controller = new AbortController();
      if (initial) setLoading(true);
      try {
        const result = selectedStationId === undefined
          ? await getEventLeaderboard(
            Number(selectedEventId),
            selectedRouteSheetId,
            controller.signal,
          )
          : await getStationLeaderboard(
            Number(selectedEventId),
            selectedStationId,
            controller.signal,
          );
        if (!active) return;
        hasSuccessfulResponse = true;
        setData(result);
        setLoadedQuery(queryKey);
        setError("");
        setLastUpdated(new Date());
      } catch (requestError) {
        if (!active || (requestError instanceof DOMException && requestError.name === "AbortError")) return;
        setError(
          requestError instanceof ApiError
            ? requestError.message
            : "Не удалось загрузить рейтинг. Проверьте подключение и попробуйте ещё раз.",
        );
      } finally {
        pending = false;
        if (active && initial) setLoading(false);
      }
    };

    void refresh(true);
    const intervalId = window.setInterval(() => {
      if (hasSuccessfulResponse) void refresh(false);
    }, 5000);
    return () => {
      active = false;
      controller?.abort();
      window.clearInterval(intervalId);
    };
  }, [queryKey, refreshKey, selectedEventId, selectedRouteSheetId, selectedStationId, validSelection]);

  const visibleData = validSelection && loadedQuery === queryKey ? data : null;
  const normalizedQuery = query.trim().toLowerCase();
  const matchesParticipant = (registrationNumber: string) => (
    !normalizedQuery || registrationNumber.toLowerCase().includes(normalizedQuery)
  );
  const filteredParticipantCount = visibleData?.participants.filter(
    (participant) => matchesParticipant(participant.registration_number),
  ).length ?? 0;

  function updateUrl(eventId: string, mode: string) {
    const params = new URLSearchParams(window.location.search);
    params.set("eventId", eventId);
    params.delete("routeSheetId");
    params.delete("stationId");
    if (mode.startsWith("route:")) params.set("routeSheetId", mode.slice("route:".length));
    if (mode.startsWith("station:")) params.set("stationId", mode.slice("station:".length));
    window.history.replaceState(null, "", `/leaderboard?${params.toString()}`);
  }

  if (authLoading) {
    return <main className="board-page"><div className="state-box" role="status">Проверяем сессию…</div></main>;
  }
  if (!user?.is_system_admin) {
    return (
      <main className="board-page">
        <h1>Рейтинги закрыты.</h1>
        <p>Войдите в локальной административной зоне для просмотра результатов.</p>
        <a className="primary-button" href="/login">Войти</a>
      </main>
    );
  }

  const isStationLeaderboard = (
    value: LeaderboardResponse | StationLeaderboardResponse,
  ): value is StationLeaderboardResponse => "station" in value;
  return (
    <main className="board-page">
      <div className="page-kicker"><span className="eyebrow">АДМИНИСТРАТИВНАЯ ЗОНА</span><span className="live-indicator"><i /> АВТООБНОВЛЕНИЕ</span></div>
      <div className="board-heading">
        <div>
          <h1>Рейтинг<span className="accent-dot">.</span></h1>
          <p>{currentEvent?.name ?? "Результаты участников мероприятия"}</p>
        </div>
        <div className="board-event-form">
          <label htmlFor="board-event">Мероприятие</label>
          <select
            id="board-event"
            value={selectedEventId}
            disabled={eventsLoading || detailsLoading || events.length === 0}
            onChange={(event) => {
              const nextId = event.target.value;
              setSelectedEventId(nextId);
              setSelectedMode("");
              setLoadedEventId(null);
              setError("");
              updateUrl(nextId, "");
            }}
          >
            {events.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
          <label htmlFor="board-mode">Режим рейтинга</label>
          <select
            id="board-mode"
            value={selectedMode}
            disabled={!currentEvent || detailsLoading}
            onChange={(event) => {
              setSelectedMode(event.target.value);
              setError("");
              updateUrl(selectedEventId, event.target.value);
            }}
          >
            <option value="">Общий рейтинг</option>
            {routeSheets.length > 0 && (
              <optgroup label="Маршрутные листы">
                {routeSheets.map((sheet) => (
                  <option key={sheet.id} value={`route:${sheet.id}`}>{sheet.name}</option>
                ))}
              </optgroup>
            )}
            {stations.some((station) => station.rating_mode === "separate") && (
              <optgroup label="Отдельные рейтинги площадок">
                {stations.filter((station) => station.rating_mode === "separate").map((station) => (
                  <option key={station.id} value={`station:${station.id}`}>{station.name}</option>
                ))}
              </optgroup>
            )}
          </select>
        </div>
      </div>

      {!eventsLoading && events.length === 0 && !error && <div className="notice-box">Мероприятий пока нет.</div>}
      {eventsLoading && <div className="state-box" role="status"><span className="spinner" />Загружаем мероприятия…</div>}
      {detailsLoading && <div className="state-box" role="status"><span className="spinner" />Загружаем настройки мероприятия…</div>}
      {validSelection && loading && !visibleData && <div className="state-box" role="status"><span className="spinner" />Загружаем результаты…</div>}
      {error && <div className={visibleData ? "inline-error" : "state-box error-box"} role="alert">
        <span>{error}</span>
        {!visibleData && <button className="retry-button" onClick={() => setRefreshKey((key) => key + 1)}>Повторить</button>}
      </div>}

      {visibleData && (
        <>
          <section className="board-summary" aria-label="Сводка рейтинга">
            <div><span>УЧАСТНИКОВ</span><strong>{visibleData.participants.length}</strong></div>
            <div><span>{isStationLeaderboard(visibleData) ? "ПЛОЩАДКА" : "ПЛОЩАДОК"}</span><strong>{isStationLeaderboard(visibleData) ? visibleData.station.name : visibleData.stations_total}</strong></div>
            <div><span>ОБНОВЛЕНО</span><strong className="updated-time">{lastUpdated?.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) ?? "—"}</strong></div>
          </section>
          <div className="table-heading">
            <div><span className="eyebrow">ТЕКУЩИЕ РЕЗУЛЬТАТЫ</span><h2>{isStationLeaderboard(visibleData) ? `Рейтинг площадки · максимум ${visibleData.station.score_max}` : "Участники"}</h2></div>
            <label className="search-control"><span aria-hidden="true">⌕</span><input aria-label="Поиск по номеру участника" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Номер участника" /></label>
          </div>
          <div className="leaderboard-table" role="table" aria-label="Рейтинг участников">
            <div className="table-row table-header" role="row">
              <span role="columnheader">МЕСТО</span><span role="columnheader">НОМЕР УЧАСТНИКА</span>
              {!isStationLeaderboard(visibleData) && <span role="columnheader">ПЛОЩАДКИ</span>}
              <span role="columnheader">БАЛЛЫ</span>
            </div>
            {visibleData && isStationLeaderboard(visibleData) && visibleData.participants
              .filter((participant) => matchesParticipant(participant.registration_number))
              .map((participant) => (
              <div className="table-row" role="row" key={participant.registration_number}>
                <strong className="rank-cell" role="cell">{String(participant.place).padStart(2, "0")}</strong>
                <span className="participant-cell" role="cell">
                  <strong>№ {participant.registration_number}</strong>
                </span>
                <strong className="points-cell" role="cell">{participant.points}<small> БАЛЛОВ</small></strong>
              </div>
            ))}
            {visibleData && !isStationLeaderboard(visibleData) && visibleData.participants
              .filter((participant) => matchesParticipant(participant.registration_number))
              .map((participant) => (
                <div className="table-row" role="row" key={participant.registration_number}>
                  <strong className="rank-cell" role="cell">{String(participant.place).padStart(2, "0")}</strong>
                  <span className="participant-cell" role="cell">
                    <strong>№ {participant.registration_number}</strong>
                  </span>
                  <span className="progress-cell" role="cell" aria-label="Баллы по основным площадкам">
                    {participant.stations.map((station) => (
                      <span className={`station-progress ${station.points === null ? "not-visited" : ""}`} key={station.station_id} title={`${station.name}: ${station.points === null ? "не пройдена" : `${station.points} из ${station.score_max}`}`}>
                        <span>{station.name}</span>
                        <strong>{station.points === null ? "—" : station.points}</strong>
                      </span>
                    ))}
                  </span>
                  <strong className="points-cell" role="cell">{participant.total_points}<small> БАЛЛОВ</small></strong>
                </div>
              ))}
            {filteredParticipantCount === 0 && <div className="empty-state">{visibleData.participants.length ? "Участник с таким номером не найден." : "В этом мероприятии пока нет участников."}</div>}
          </div>
          <p className="privacy-note">Отображаются только номера участников и результаты. Равные результаты занимают одно место.</p>
        </>
      )}
    </main>
  );
}

function modeFromUrl(): string {
  const parameters = new URLSearchParams(window.location.search);
  const stationId = parameters.get("stationId");
  if (stationId) return `station:${stationId}`;
  const routeSheetId = parameters.get("routeSheetId");
  return routeSheetId ? `route:${routeSheetId}` : "";
}

export default App;
