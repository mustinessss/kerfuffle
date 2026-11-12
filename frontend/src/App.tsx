import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { ApiError, getPublicLeaderboard, type LeaderboardResponse } from "./api";
import { useAuth } from "./authContext";
import { OrganizerPage, RegistrationPage, ScoringPage } from "./WorkspacePages";
import "./styles.css";

type Page = "home" | "leaderboard" | "registration" | "scoring" | "organizer" | "callback";

function currentPage(): Page {
  const path = window.location.pathname.replace(/\/+$/, "");
  if (path === "/leaderboard") return "leaderboard";
  if (path === "/register") return "registration";
  if (path === "/score") return "scoring";
  if (path === "/organizer") return "organizer";
  if (path === "/auth/callback") return "callback";
  return "home";
}

function eventIdFromUrl(): string {
  return new URLSearchParams(window.location.search).get("eventId") ?? "";
}

function App() {
  const page = currentPage();
  const [eventId, setEventId] = useState(eventIdFromUrl);
  const { loading: authLoading, error: authError } = useAuth();

  function openLeaderboard(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const id = eventId.trim();
    if (!/^[1-9]\d*$/.test(id)) return;
    window.location.href = `/leaderboard?eventId=${encodeURIComponent(id)}`;
  }

  return (
    <div className="app-shell">
      <header className="site-header">
        <a className="wordmark" href="/" aria-label="Kerfuffle — главная">
          <span className="wordmark-mark" aria-hidden="true">k.</span>
          <span>kerfuffle</span>
        </a>
        <nav className="header-nav" aria-label="Основная навигация">
          <a href="/leaderboard">Рейтинг</a>
          <a href="/organizer">Организатору <span aria-hidden="true">↗</span></a>
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
              <form className="event-form" onSubmit={openLeaderboard}>
                <label className="visually-hidden" htmlFor="event-id">Номер мероприятия</label>
                <input
                  id="event-id"
                  inputMode="numeric"
                  pattern="[1-9][0-9]*"
                  required
                  value={eventId}
                  onChange={(event) => setEventId(event.target.value)}
                  placeholder="ID события"
                />
                <button type="submit" aria-label="Открыть рейтинг">Открыть ↗</button>
              </form>
            </div>
          </section>

          <p className="home-note">Нужен доступ сотрудника? <a href="/organizer">Кабинет организатора</a></p>
        </main>
      )}

      {page === "leaderboard" && <LeaderboardPage eventId={eventId} onEventIdChange={setEventId} />}
      {page === "registration" && <RegistrationPage />}
      {page === "scoring" && <ScoringPage />}
      {page === "organizer" && <OrganizerPage />}
      {page === "callback" && (
        <main className="workspace-page">
          {authLoading
            ? <div className="state-box" role="status"><span className="spinner" />Завершаем вход через Keycloak…</div>
            : <div className="state-box error-box" role="alert">{authError || "Вход не настроен. Проверьте конфигурацию Keycloak."}<a className="back-link" href="/organizer">Перейти в кабинет</a></div>}
        </main>
      )}

      <footer className="site-footer">
        <a className="footer-brand" href="/">mustiness</a>
        <span>СОБЫТИЯ, КОТОРЫЕ ОБЪЕДИНЯЮТ</span>
        <span>© 2026</span>
      </footer>
    </div>
  );
}

function LeaderboardPage({
  eventId,
  onEventIdChange,
}: {
  eventId: string;
  onEventIdChange: (value: string) => void;
}) {
  const [data, setData] = useState<LeaderboardResponse | null>(null);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [errorEventId, setErrorEventId] = useState("");
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [loadedEventId, setLoadedEventId] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const validEventId = /^[1-9]\d*$/.test(eventId.trim());

  useEffect(() => {
    if (!validEventId) return;

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
        const result = await getPublicLeaderboard(Number(eventId), controller.signal);
        if (!active) return;
        hasSuccessfulResponse = true;
        setData(result);
        setLoadedEventId(eventId.trim());
        setError("");
        setErrorEventId("");
        setLastUpdated(new Date());
      } catch (requestError) {
        if (!active || (requestError instanceof DOMException && requestError.name === "AbortError")) return;
        setErrorEventId(eventId.trim());
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
  }, [eventId, validEventId, refreshKey]);

  const participants = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    const visibleData = validEventId && loadedEventId === eventId.trim() ? data : null;
    if (!visibleData || !normalizedQuery) return visibleData?.participants ?? [];
    return visibleData.participants.filter((participant) =>
      participant.registration_number.toLowerCase().includes(normalizedQuery),
    );
  }, [data, eventId, loadedEventId, query, validEventId]);

  const visibleData = validEventId && loadedEventId === eventId.trim() ? data : null;
  const visibleError = validEventId && errorEventId === eventId.trim() ? error : "";

  function loadEvent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!validEventId) return;
    const params = new URLSearchParams(window.location.search);
    params.set("eventId", eventId.trim());
    window.history.replaceState(null, "", `/leaderboard?${params.toString()}`);
    setRefreshKey((key) => key + 1);
  }

  return (
    <main className="board-page">
      <div className="page-kicker"><span className="eyebrow">ОТКРЫТЫЕ РЕЗУЛЬТАТЫ</span><span className="live-indicator"><i /> АВТООБНОВЛЕНИЕ</span></div>
      <div className="board-heading">
        <div>
          <h1>Рейтинг<span className="accent-dot">.</span></h1>
          <p>{visibleData ? visibleData.event.name : "Результаты участников мероприятия"}</p>
        </div>
        <form className="board-event-form" onSubmit={loadEvent}>
          <label htmlFor="board-event-id">Мероприятие</label>
          <div>
            <input id="board-event-id" inputMode="numeric" pattern="[1-9][0-9]*" required value={eventId} onChange={(event) => onEventIdChange(event.target.value)} placeholder="ID события" />
            <button type="submit">Показать</button>
          </div>
        </form>
      </div>

      {!validEventId && <div className="notice-box">Введите ID мероприятия, чтобы загрузить публичный рейтинг.</div>}
      {validEventId && loading && !visibleData && <div className="state-box" role="status"><span className="spinner" />Загружаем результаты…</div>}
      {visibleError && <div className={visibleData ? "inline-error" : "state-box error-box"} role="alert">
        <span>{visibleError}</span>
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
              <span role="columnheader">МЕСТО</span><span role="columnheader">УЧАСТНИК</span><span role="columnheader">ПЛОЩАДКИ</span><span role="columnheader">БАЛЛЫ</span>
            </div>
            {participants.map((participant) => (
              <div className="table-row" role="row" key={participant.registration_number}>
                <strong className="rank-cell" role="cell">{String(participant.place).padStart(2, "0")}</strong>
                <span className="participant-cell" role="cell">
                  <strong>{participant.first_name} {participant.last_name}</strong>
                  <small>№ {participant.registration_number}</small>
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
          <p className="privacy-note">Публично отображаются имя, номер и результаты; контакты не раскрываются. Равные результаты занимают одно место.</p>
        </>
      )}
    </main>
  );
}

export default App;
