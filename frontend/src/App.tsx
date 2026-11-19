import { useEffect, useState } from "react";
import {
  ApiError,
  getPublicEvents,
  getPublicLeaderboard,
  type LeaderboardResponse,
  type PublicEventSummary,
} from "./api";
import { useAuth } from "./authContext";
import { RegistrationPage, ScoringPage, WorkspacePage } from "./WorkspacePages";
import {
  AdminUsersPage,
  ForgotPasswordPage,
  InvitationPage,
  LoginPage,
  ResetPasswordPage,
} from "./AccountPages";
import "./styles.css";

type Page = "home" | "leaderboard" | "registration" | "scoring" | "workspace" | "login" | "accept-invitation" | "forgot-password" | "reset-password" | "admin-users";

function currentPage(): Page {
  const path = window.location.pathname.replace(/\/+$/, "");
  if (path === "/leaderboard") return "leaderboard";
  if (path === "/register") return "registration";
  if (path === "/score") return "scoring";
  if (path === "/workspace") return "workspace";
  if (path === "/login") return "login";
  if (path === "/accept-invitation") return "accept-invitation";
  if (path === "/forgot-password") return "forgot-password";
  if (path === "/reset-password") return "reset-password";
  if (path === "/admin/users") return "admin-users";
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
          {user?.is_system_admin && <a href="/admin/users">Пользователи</a>}
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
            <div className="action-card action-board">
              <span className="action-number">03</span>
              <span className="action-copy"><strong>Таблица участников</strong><small>Посмотрите текущий рейтинг события</small></span>
              <HomeLeaderboardPicker />
            </div>
          </section>

          <p className="home-note">Нужен доступ сотрудника? <a href="/workspace">Рабочее пространство</a></p>
        </main>
      )}

      {page === "leaderboard" && <LeaderboardPage />}
      {page === "registration" && <RegistrationPage />}
      {page === "scoring" && <ScoringPage />}
      {page === "workspace" && <WorkspacePage />}
      {page === "login" && <LoginPage />}
      {page === "accept-invitation" && <InvitationPage />}
      {page === "forgot-password" && <ForgotPasswordPage />}
      {page === "reset-password" && <ResetPasswordPage />}
      {page === "admin-users" && <AdminUsersPage />}

      <footer className="site-footer">
        <a className="footer-brand" href="/">mustiness</a>
        <span>СОБЫТИЯ, КОТОРЫЕ ОБЪЕДИНЯЮТ</span>
        <span>© 2026</span>
      </footer>
    </div>
  );
}

function HomeLeaderboardPicker() {
  const [events, setEvents] = useState<PublicEventSummary[]>([]);
  const [eventId, setEventId] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    getPublicEvents(controller.signal)
      .then((result) => {
        setEvents(result);
        setEventId(result[0] ? String(result[0].id) : "");
      })
      .catch((requestError: unknown) => {
        if (!controller.signal.aborted) {
          setError(requestError instanceof ApiError
            ? requestError.message
            : "Не удалось загрузить список мероприятий.");
        }
      });
    return () => controller.abort();
  }, []);

  return (
    <form className="event-form" onSubmit={(event) => {
      event.preventDefault();
      if (eventId) window.location.href = `/leaderboard?eventId=${encodeURIComponent(eventId)}`;
    }}>
      <label className="visually-hidden" htmlFor="home-event">Мероприятие</label>
      <select id="home-event" value={eventId} onChange={(event) => setEventId(event.target.value)} required>
        <option value="" disabled>Выберите мероприятие</option>
        {events.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
      </select>
      <button type="submit" disabled={!eventId}>Открыть ↗</button>
      {error && <span className="form-error" role="alert">{error}</span>}
    </form>
  );
}

function LeaderboardPage() {
  const [data, setData] = useState<LeaderboardResponse | null>(null);
  const [events, setEvents] = useState<PublicEventSummary[]>([]);
  const [selectedEventId, setSelectedEventId] = useState(eventIdFromUrl());
  const [selectedMode, setSelectedMode] = useState(
    new URLSearchParams(window.location.search).get("routeSheetId") ?? "",
  );
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [loadedQuery, setLoadedQuery] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [eventsLoading, setEventsLoading] = useState(true);
  const currentEvent = events.find((item) => String(item.id) === selectedEventId) ?? null;
  const selectedRouteSheetId = selectedMode ? Number(selectedMode) : undefined;
  const queryKey = `${selectedEventId}:${selectedMode || "all"}`;
  const validSelection = currentEvent !== null && (
    selectedRouteSheetId === undefined
    || currentEvent.route_sheets.some((sheet) => sheet.id === selectedRouteSheetId)
  );

  useEffect(() => {
    const controller = new AbortController();
    getPublicEvents(controller.signal)
      .then((result) => {
        setEvents(result);
        const preferredEventId = eventIdFromUrl();
        const activeEventId = result.some((item) => String(item.id) === preferredEventId)
          ? preferredEventId
          : String(result[0]?.id ?? "");
        setSelectedEventId(activeEventId);
        setSelectedMode((currentMode) => {
          const event = result.find((item) => String(item.id) === activeEventId);
          return event?.route_sheets.some((sheet) => String(sheet.id) === currentMode)
            ? currentMode
            : "";
        });
      })
      .catch((requestError: unknown) => {
        if (!controller.signal.aborted) {
          setError(requestError instanceof ApiError
            ? requestError.message
            : "Не удалось загрузить список мероприятий.");
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setEventsLoading(false);
      });
    return () => controller.abort();
  }, []);

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
        const result = await getPublicLeaderboard(
          Number(selectedEventId),
          selectedRouteSheetId,
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
  }, [queryKey, refreshKey, selectedEventId, selectedRouteSheetId, validSelection]);

  const visibleData = validSelection && loadedQuery === queryKey ? data : null;
  const normalizedQuery = query.trim().toLowerCase();
  const participants = !visibleData || !normalizedQuery
    ? visibleData?.participants ?? []
    : visibleData.participants.filter((participant) =>
      participant.registration_number.toLowerCase().includes(normalizedQuery),
    );

  function updateUrl(eventId: string, mode: string) {
    const params = new URLSearchParams(window.location.search);
    params.set("eventId", eventId);
    if (mode) params.set("routeSheetId", mode);
    else params.delete("routeSheetId");
    window.history.replaceState(null, "", `/leaderboard?${params.toString()}`);
  }

  return (
    <main className="board-page">
      <div className="page-kicker"><span className="eyebrow">ОТКРЫТЫЕ РЕЗУЛЬТАТЫ</span><span className="live-indicator"><i /> АВТООБНОВЛЕНИЕ</span></div>
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
            disabled={eventsLoading || events.length === 0}
            onChange={(event) => {
              const nextId = event.target.value;
              setSelectedEventId(nextId);
              setSelectedMode("");
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
            disabled={!currentEvent}
            onChange={(event) => {
              setSelectedMode(event.target.value);
              setError("");
              updateUrl(selectedEventId, event.target.value);
            }}
          >
            <option value="">Общий рейтинг</option>
            {currentEvent?.route_sheets.map((sheet) => (
              <option key={sheet.id} value={sheet.id}>{sheet.name}</option>
            ))}
          </select>
        </div>
      </div>

      {!eventsLoading && events.length === 0 && !error && <div className="notice-box">Мероприятий пока нет.</div>}
      {eventsLoading && <div className="state-box" role="status"><span className="spinner" />Загружаем мероприятия…</div>}
      {validSelection && loading && !visibleData && <div className="state-box" role="status"><span className="spinner" />Загружаем результаты…</div>}
      {error && <div className={visibleData ? "inline-error" : "state-box error-box"} role="alert">
        <span>{error}</span>
        {!visibleData && <button className="retry-button" onClick={() => setRefreshKey((key) => key + 1)}>Повторить</button>}
      </div>}

      {visibleData && (
        <>
          <section className="board-summary" aria-label="Сводка рейтинга">
            <div><span>УЧАСТНИКОВ</span><strong>{visibleData.participants.length}</strong></div>
            <div><span>ПЛОЩАДОК</span><strong>{visibleData.stations_total}</strong></div>
            <div><span>ОБНОВЛЕНО</span><strong className="updated-time">{lastUpdated?.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) ?? "—"}</strong></div>
          </section>
          <div className="table-heading">
            <div><span className="eyebrow">ТЕКУЩИЕ РЕЗУЛЬТАТЫ</span><h2>Участники</h2></div>
            <label className="search-control"><span aria-hidden="true">⌕</span><input aria-label="Поиск по номеру участника" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Номер участника" /></label>
          </div>
          <div className="leaderboard-table" role="table" aria-label="Рейтинг участников">
            <div className="table-row table-header" role="row">
              <span role="columnheader">МЕСТО</span><span role="columnheader">НОМЕР УЧАСТНИКА</span><span role="columnheader">ПЛОЩАДКИ</span><span role="columnheader">БАЛЛЫ</span>
            </div>
            {participants.map((participant) => (
              <div className="table-row" role="row" key={participant.registration_number}>
                <strong className="rank-cell" role="cell">{String(participant.place).padStart(2, "0")}</strong>
                <span className="participant-cell" role="cell">
                  <strong>№ {participant.registration_number}</strong>
                </span>
                <span className="progress-cell" role="cell" aria-label="Баллы по площадкам">
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
            {participants.length === 0 && <div className="empty-state">{visibleData.participants.length ? "Участник с таким номером не найден." : "В этом мероприятии пока нет участников."}</div>}
          </div>
          <p className="privacy-note">Публично отображаются только номера участников и результаты. Равные результаты занимают одно место.</p>
        </>
      )}
    </main>
  );
}

export default App;
