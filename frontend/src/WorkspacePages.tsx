import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import type { ReactNode } from "react";
import { ApiError } from "./api";
import { CopyLink } from "./CopyLink";
import {
  createAccessCode,
  createEvent,
  createStation,
  createRouteSheet,
  correctScore,
  annulScore,
  getCurrentAccount,
  getAccessCodes,
  getEvents,
  getParticipants,
  getRouteSheets,
  getEventScores,
  inviteStaffAccount,
  getStations,
  lookupParticipant,
  lookupWithAccessCode,
  registerParticipant,
  deleteRouteSheet,
  revokeAccessCode,
  submitScore,
  submitScoreWithAccessCode,
  updateStation,
  updateRouteSheet,
  verifyAccessCode,
} from "./api";
import type {
  AccessCodeSummary,
  CurrentAccount,
  CreatedInvitation,
  EventSummary,
  ParticipantLookup,
  RegisteredParticipant,
  RouteSheetSummary,
  ScoreHistoryEntry,
  StationSummary,
  VerifiedAccess,
} from "./api";
import { useAuth } from "./authContext";

const EMPTY_PARTICIPANTS: RegisteredParticipant[] = [];

function messageFor(error: unknown): string {
  return error instanceof ApiError
    ? error.message
    : "Не удалось связаться с сервером. Проверьте подключение и повторите попытку.";
}

function AuthGate() {
  const { login, user, error: authError } = useAuth();
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setSaving(true);
    setFormError("");
    try {
      await login(String(form.get("email") ?? ""), String(form.get("password") ?? ""));
    } catch (requestError) {
      setFormError(messageFor(requestError));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="workspace-card auth-gate">
      <p className="eyebrow">ЗАЩИЩЁННЫЙ ДОСТУП</p>
      <h2>Войдите в Kerfuffle.</h2>
      <p>Доступ к мероприятиям определяется назначенными ролями.</p>
      {(authError || formError) && <p className="form-error" role="alert">{formError || authError}</p>}
      {!user && (
        <form className="workspace-form login-form" onSubmit={(event) => void submit(event)}>
          <label>Email<input name="email" type="email" autoComplete="username" required maxLength={254} /></label>
          <label>Пароль<input name="password" type="password" autoComplete="current-password" required /></label>
          <button className="primary-button" disabled={saving}>{saving ? "Входим…" : "Войти"}</button>
          <a className="quiet-button" href="/forgot-password">Забыли пароль?</a>
        </form>
      )}
    </section>
  );
}

function AuthLoading() {
  return <div className="state-box" role="status"><span className="spinner" />Проверяем сессию…</div>;
}

function AuthenticatedPage({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  const { user, loading, logout, error, clearError } = useAuth();

  if (loading) return <main className="workspace-page"><AuthLoading /></main>;
  if (!user) {
    return (
      <main className="workspace-page">
        <WorkspaceHeading title={title} description={description} />
        <AuthGate />
      </main>
    );
  }

  return (
    <main className="workspace-page">
      <WorkspaceHeading title={title} description={description} />
      <div className="workspace-account">
        <span>{user.display_name}</span>
        <button className="quiet-button" onClick={() => { clearError(); void logout(); }}>Выйти</button>
      </div>
      {error && <p className="form-error" role="alert">{error}</p>}
      {children}
    </main>
  );
}

function WorkspaceHeading({ title, description }: { title: string; description: string }) {
  return (
    <div className="workspace-heading">
      <p className="eyebrow">KERFUFFLE · РАБОЧЕЕ ПРОСТРАНСТВО</p>
      <h1>{title}<span className="accent-dot">.</span></h1>
      <p>{description}</p>
    </div>
  );
}

export function WorkspacePage() {
  const { user } = useAuth();
  const token = "";
  const [account, setAccount] = useState<CurrentAccount | null>(null);
  const [events, setEvents] = useState<EventSummary[]>([]);
  const [selectedEventId, setSelectedEventId] = useState<number | null>(null);
  const [stations, setStations] = useState<StationSummary[]>([]);
  const [routeSheets, setRouteSheets] = useState<RouteSheetSummary[]>([]);
  const [participants, setParticipants] = useState<RegisteredParticipant[]>([]);
  const [loading, setLoading] = useState(true);
  const [detailsEventId, setDetailsEventId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [participantQuery, setParticipantQuery] = useState("");
  const selectedEvent = events.find((event) => event.id === selectedEventId) ?? null;
  const canManage = account?.is_system_admin === true;
  const canRegister = canManage;
  const detailLoading = selectedEventId !== null && detailsEventId !== selectedEventId;
  const visibleStations = detailsEventId === selectedEventId ? stations : [];
  const visibleRouteSheets = detailsEventId === selectedEventId ? routeSheets : [];
  const visibleParticipants = detailsEventId === selectedEventId ? participants : EMPTY_PARTICIPANTS;
  const filteredParticipants = useMemo(() => {
    const query = participantQuery.trim().toLowerCase();
    return query
      ? visibleParticipants.filter((participant) =>
          `${participant.first_name} ${participant.last_name} ${participant.registration_number}`
            .toLowerCase()
            .includes(query),
        )
      : visibleParticipants;
  }, [participantQuery, visibleParticipants]);

  useEffect(() => {
    if (!user) return;
    const controller = new AbortController();
    let active = true;
    Promise.all([getCurrentAccount(token, controller.signal), getEvents(token, controller.signal)])
      .then(([nextAccount, nextEvents]) => {
        if (!active) return;
        setAccount(nextAccount);
        setEvents(nextEvents);
        setSelectedEventId((current) =>
          current && nextEvents.some((event) => event.id === current)
            ? current
            : nextEvents[0]?.id ?? null,
        );
        setError("");
      })
      .catch((requestError: unknown) => {
        if (active && !controller.signal.aborted) setError(messageFor(requestError));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [token, user]);

  useEffect(() => {
    if (!user || selectedEventId === null) return;
    const controller = new AbortController();
    let active = true;
    const participantRequest = canRegister
      ? getParticipants(selectedEventId, token, controller.signal)
      : Promise.resolve([]);
    const routeSheetRequest = canRegister
      ? getRouteSheets(selectedEventId, token, controller.signal)
      : Promise.resolve([]);
    Promise.all([
      getStations(selectedEventId, token, controller.signal),
      participantRequest,
      routeSheetRequest,
    ])
      .then(([nextStations, nextParticipants, nextRouteSheets]) => {
        if (!active) return;
        setStations(nextStations);
        setParticipants(nextParticipants);
        setRouteSheets(nextRouteSheets);
        setDetailsEventId(selectedEventId);
        setError("");
      })
      .catch((requestError: unknown) => {
        if (active && !controller.signal.aborted) {
          setStations([]);
          setParticipants([]);
          setRouteSheets([]);
          setDetailsEventId(selectedEventId);
          setError(messageFor(requestError));
        }
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [canRegister, refreshKey, selectedEventId, token, user]);

  async function handleCreateEvent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const name = String(form.get("eventName") ?? "").trim();
    const eventDate = String(form.get("eventDate") ?? "");
    try {
      setError("");
      setActionMessage("");
      const created = await createEvent({ name, event_date: eventDate });
      setEvents((current) => [...current, created]);
      setSelectedEventId(created.id);
      setActionMessage("Мероприятие создано.");
      formElement.reset();
    } catch (requestError) {
      setError(messageFor(requestError));
    }
  }

  return (
    <AuthenticatedPage title="Рабочее пространство" description="Управляйте мероприятиями, площадками и участниками.">
      {loading && <AuthLoading />}
      {!loading && error && <p className="form-error" role="alert">{error}</p>}
      {!loading && account && (
        <>
          <section className="workspace-card account-summary">
            <div><span>ПОЛЬЗОВАТЕЛЬ</span><strong>{account.display_name}</strong></div>
            <div><span>ДОСТУП</span><strong>{account.is_system_admin ? "Системный администратор" : "По назначенным ролям"}</strong></div>
          </section>
          <section className="workspace-section">
            <div className="workspace-section-heading">
              <div><p className="eyebrow">ВАШИ СОБЫТИЯ</p><h2>Мероприятия</h2></div>
              {events.length > 0 && (
                <label className="event-select-label">
                  <span className="visually-hidden">Выбрать мероприятие</span>
                  <select value={selectedEventId ?? ""} onChange={(event) => setSelectedEventId(Number(event.target.value))}>
                    {events.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
                  </select>
                </label>
              )}
            </div>
            {selectedEvent && (
              <div className="workspace-card event-summary">
                <div><span>МЕРОПРИЯТИЕ</span><strong>{selectedEvent.name}</strong></div>
                <div><span>ID МЕРОПРИЯТИЯ</span><strong>{selectedEvent.id}</strong></div>
                <div><span>ДАТА</span><strong>{selectedEvent.event_date}</strong></div>
                <div><span>УЧАСТНИКОВ</span><strong>{canRegister ? visibleParticipants.length : "—"}</strong></div>
                <div><span>ПЛОЩАДОК</span><strong>{visibleStations.length}</strong></div>
              </div>
            )}
            {!selectedEvent && (
              <div className="workspace-card empty-workspace">
                <p>{account.is_system_admin ? "Создайте первое мероприятие, чтобы начать настройку." : "Пока нет мероприятий, к которым у вас есть доступ."}</p>
              </div>
            )}
            {account.is_system_admin && (
              <form className="workspace-form event-create-form" onSubmit={(event) => void handleCreateEvent(event)}>
                <h3>Новое мероприятие</h3>
                <label>Название<input name="eventName" required maxLength={200} /></label>
                <label>Дата<input name="eventDate" type="date" required /></label>
                <button className="primary-button" type="submit">Создать мероприятие</button>
              </form>
            )}
          </section>
          {account.is_system_admin && <StaffAccountProvisioningPanel />}
          {actionMessage && <p className="success-message" role="status">{actionMessage}</p>}
          {selectedEvent && (
            <>
              <section className="workspace-section">
                <div className="workspace-section-heading">
                  <div><p className="eyebrow">НАСТРОЙКА И ДОСТУП</p><h2>Площадки</h2></div>
                  {detailLoading && <span className="muted-status">Обновляем…</span>}
                </div>
                {visibleStations.length === 0 && !detailLoading && <div className="workspace-card empty-workspace"><p>Для этого мероприятия пока нет доступных площадок.</p></div>}
                <div className="station-admin-list">
                  {visibleStations.map((station) => (
                    <StationEditor
                      key={station.id}
                      station={station}
                      accessToken={token}
                      editable={canManage}
                      onUpdated={() => setRefreshKey((key) => key + 1)}
                      onError={setError}
                    />
                  ))}
                </div>
                {canManage && <CreateStationForm eventId={selectedEvent.id} accessToken={token} onCreated={() => setRefreshKey((key) => key + 1)} onError={setError} />}
                {canManage && <RouteSheetsPanel eventId={selectedEvent.id} accessToken={token} stations={visibleStations} routeSheets={visibleRouteSheets} onChanged={() => setRefreshKey((key) => key + 1)} />}
                {canManage && <AccessCodesPanel eventId={selectedEvent.id} accessToken={token} stations={visibleStations} />}
              </section>
              {canRegister && (
                <section className="workspace-section">
                  <div className="workspace-section-heading">
                    <div><p className="eyebrow">УЧЁТ УЧАСТИЯ</p><h2>Участники</h2></div>
                    <span className="muted-status">{visibleParticipants.length} в списке</span>
                  </div>
                  <RegisterParticipantForm eventId={selectedEvent.id} accessToken={token} routeSheets={visibleRouteSheets} onRegistered={() => setRefreshKey((key) => key + 1)} onError={setError} />
                  <label className="participant-search">
                    <span className="visually-hidden">Поиск участника</span>
                    <input value={participantQuery} onChange={(event) => setParticipantQuery(event.target.value)} placeholder="Найти по имени или номеру" />
                  </label>
                  <div className="participant-admin-list">
                    {filteredParticipants.map((participant) => (
                      <div className="participant-admin-row" key={participant.id}>
                        <strong>{participant.first_name} {participant.last_name}</strong>
                        <span>№ {participant.registration_number}</span>
                        {participant.route_sheet_name && <span>{participant.route_sheet_name}</span>}
                      </div>
                    ))}
                    {filteredParticipants.length === 0 && !detailLoading && <p className="empty-workspace">{visibleParticipants.length ? "Совпадений нет." : "Участников пока нет."}</p>}
                  </div>
                </section>
              )}
              {canManage && (
                <ScoreHistoryPanel
                  key={`${selectedEvent.id}-${refreshKey}`}
                  eventId={selectedEvent.id}
                  accessToken={token}
                  onError={setError}
                />
              )}
            </>
          )}
        </>
      )}
    </AuthenticatedPage>
  );
}

function StaffAccountProvisioningPanel() {
  const [created, setCreated] = useState<CreatedInvitation | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setSaving(true);
    setError("");
    setCreated(null);
    try {
      const email = String(form.get("email") ?? "").trim();
      const invitation = await inviteStaffAccount(email);
      setCreated(invitation);
      formElement.reset();
    } catch (requestError) {
      setError(messageFor(requestError));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="workspace-section">
      <div className="workspace-section-heading">
        <div><p className="eyebrow">УЧЁТНЫЕ ЗАПИСИ</p><h2>Приглашение держателя площадки</h2></div>
      </div>
      <form className="workspace-form event-create-form" onSubmit={(event) => void handleSubmit(event)}>
        <label>Email держателя площадки<input name="email" type="email" required maxLength={254} autoComplete="email" /></label>
        <button className="primary-button" disabled={saving}>{saving ? "Создаём приглашение…" : "Создать приглашение"}</button>
      </form>
      {error && <p className="form-error" role="alert">{error}</p>}
      {created && (
        <div className="workspace-card credential-card" role="status">
          <strong>Приглашение создано для {created.email}</strong>
          {created.delivery_method === "email"
            ? <p>Приглашение отправлено по email. Ссылка действует 24 часа.</p>
            : <div><p>Ссылка действует 24 часа. Передавайте её по доверенному каналу.</p>{created.invitation_url && <CopyLink url={created.invitation_url} />}</div>}
          <button className="quiet-button" onClick={() => setCreated(null)}>Скрыть данные</button>
        </div>
      )}
    </section>
  );
}

function AccessCodesPanel({
  eventId,
  accessToken,
  stations,
}: {
  eventId: number;
  accessToken: string;
  stations: StationSummary[];
}) {
  const [codes, setCodes] = useState<AccessCodeSummary[]>([]);
  const [createdCode, setCreatedCode] = useState("");
  const role: AccessCodeSummary["role"] = "station_operator";
  const [stationId, setStationId] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    getAccessCodes(eventId, accessToken, controller.signal)
      .then((result) => { if (active) setCodes(result); })
      .catch((requestError: unknown) => {
        if (active && !controller.signal.aborted) setError(messageFor(requestError));
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [accessToken, eventId]);

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!stationId) {
      setError("Выберите площадку для кода сотрудника.");
      return;
    }
    setBusy(true);
    setError("");
    setCreatedCode("");
    try {
      const created = await createAccessCode(eventId, accessToken, {
        role,
        code: code.trim().toUpperCase(),
        station_id: Number(stationId),
      });
      setCodes((current) => [created, ...current]);
      setCreatedCode(created.code ?? "");
      setCode("");
    } catch (requestError) {
      setError(requestError instanceof ApiError && requestError.status === 409
        ? "Этот код уже используется. Выберите другую комбинацию."
        : messageFor(requestError));
    } finally {
      setBusy(false);
    }
  }

  async function handleRevoke(codeId: number) {
    setBusy(true);
    setError("");
    try {
      await revokeAccessCode(codeId, accessToken);
      setCodes((current) => current.map((code) =>
        code.id === codeId ? { ...code, is_active: false } : code,
      ));
      setCreatedCode("");
    } catch (requestError) {
      setError(messageFor(requestError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="access-code-panel">
      <div className="workspace-section-heading">
        <div><p className="eyebrow">ДОСТУП КОМАНДЫ</p><h2>Коды доступа</h2></div>
      </div>
      <form className="workspace-form create-station-form" onSubmit={(event) => void handleCreate(event)}>
        <h3>Выпустить код</h3>
        <label>Площадка
          <select value={stationId} required onChange={(event) => setStationId(event.target.value)}>
            <option value="">Выберите площадку</option>
            {stations.map((station) => <option key={station.id} value={station.id}>{station.name}</option>)}
          </select>
        </label>
        <label>Подпись — она же код для входа
          <input
            value={code}
            onChange={(event) => setCode(event.target.value.toUpperCase().replace(/[^A-HJ-NP-Z2-9]/g, "").slice(0, 16))}
            required
            minLength={8}
            maxLength={16}
            pattern="[A-HJ-NP-Z2-9]{8,16}"
            autoComplete="off"
            placeholder="Введите 8–16 символов"
          />
        </label>
        <p className="access-code-hint">8–16 символов: латинские буквы и цифры 2–9. Буквы I/O и цифры 0/1 исключены, регистр не важен. Не используйте название мероприятия или площадки.</p>
        <button className="primary-button" disabled={busy || code.length < 8 || stations.length === 0}>{busy ? "Сохраняем…" : "Создать код"}</button>
      </form>
      {error && <p className="form-error" role="alert">{error}</p>}
      {createdCode && (
        <div className="workspace-card credential-card" role="status">
          <strong>Сохраните код сейчас</strong>
          <p>Полный код больше не будет показан. Он действует без ограничения по сроку и числу входов, пока вы его не отключите.</p>
          <code className="access-code-value">{createdCode}</code>
          <button className="quiet-button" onClick={() => setCreatedCode("")}>Скрыть код</button>
        </div>
      )}
      <div className="access-code-list">
        {codes.map((code) => (
          <article className="workspace-card access-code-row" key={code.id}>
            <div>
              <strong>{code.label}</strong>
              <span>Площадка: {code.station_name ?? "не указана"}</span>
              <small>{code.is_active ? "Активен" : "Отключён"}</small>
            </div>
            {code.is_active && <button className="quiet-button" disabled={busy} onClick={() => void handleRevoke(code.id)}>Отключить</button>}
          </article>
        ))}
        {codes.length === 0 && <p className="empty-workspace">Кодов доступа пока нет.</p>}
      </div>
    </div>
  );
}

function ScoreHistoryPanel({
  eventId,
  accessToken,
  onError,
}: {
  eventId: number;
  accessToken: string;
  onError: (message: string) => void;
}) {
  const [scores, setScores] = useState<ScoreHistoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    getEventScores(eventId, accessToken, controller.signal)
      .then((result) => {
        if (active) setScores(result);
      })
      .catch((requestError: unknown) => {
        if (active && !controller.signal.aborted) onError(messageFor(requestError));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [accessToken, eventId, onError, refreshKey]);

  return (
    <section className="workspace-section">
      <div className="workspace-section-heading">
        <div><p className="eyebrow">ИЗМЕНЕНИЯ СОХРАНЯЮТСЯ В ЖУРНАЛЕ</p><h2>История начислений</h2></div>
        <span className="muted-status">{scores.length} оценок</span>
      </div>
      {loading && <div className="state-box" role="status"><span className="spinner" />Загружаем историю…</div>}
      {!loading && scores.length === 0 && <div className="workspace-card empty-workspace"><p>Начислений пока нет.</p></div>}
      {!loading && scores.length > 0 && (
        <div className="score-history-list">
          {scores.map((score) => (
            <ScoreHistoryItem
              key={score.id}
              score={score}
              accessToken={accessToken}
              onUpdated={() => setRefreshKey((key) => key + 1)}
              onError={onError}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function ScoreHistoryItem({
  score,
  accessToken,
  onUpdated,
  onError,
}: {
  score: ScoreHistoryEntry;
  accessToken: string;
  onUpdated: () => void;
  onError: (message: string) => void;
}) {
  const [points, setPoints] = useState(String(score.points));
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);

  async function handleCorrection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    onError("");
    try {
      await correctScore(score.id, accessToken, Number(points), reason.trim());
      setReason("");
      onUpdated();
    } catch (requestError) {
      onError(messageFor(requestError));
    } finally {
      setSaving(false);
    }
  }

  async function handleAnnulment() {
    if (saving || score.is_annulled) return;
    setSaving(true);
    onError("");
    try {
      await annulScore(score.id, accessToken, reason.trim());
      setReason("");
      onUpdated();
    } catch (requestError) {
      onError(messageFor(requestError));
    } finally {
      setSaving(false);
    }
  }

  return (
    <article className="workspace-card score-history-card">
      <div className="score-history-summary">
        <strong>{score.first_name} {score.last_name} · № {score.registration_number}</strong>
        <span>{score.station_name}</span>
        <span className={score.is_annulled ? "annulled-score" : ""}>
          {score.is_annulled ? "Аннулировано" : `${score.points} баллов`}
        </span>
      </div>
      {score.history.length > 0 && (
        <ol className="score-audit-list">
          {score.history.map((entry) => (
            <li key={entry.id}>
              {entry.action === "correction" ? `Исправлено: ${entry.points_before} → ${entry.points_after}` : "Аннулировано"}
              {" · "}{entry.reason} · {entry.changed_by} · {new Date(entry.created_at).toLocaleString("ru-RU")}
            </li>
          ))}
        </ol>
      )}
      {!score.is_annulled && (
        <form className="score-admin-form" onSubmit={(event) => void handleCorrection(event)}>
          <label>Баллы<input type="number" min="0" required value={points} onChange={(event) => setPoints(event.target.value)} /></label>
          <label className="score-reason-label">Причина изменения<input required minLength={1} maxLength={1000} value={reason} onChange={(event) => setReason(event.target.value)} /></label>
          <button className="quiet-button" disabled={saving || !reason.trim()} type="submit">{saving ? "Сохраняем…" : "Исправить"}</button>
          <button className="quiet-button annul-score-button" disabled={saving || !reason.trim()} type="button" onClick={() => void handleAnnulment()}>Аннулировать</button>
        </form>
      )}
    </article>
  );
}

function StationEditor({
  station,
  accessToken,
  editable,
  onUpdated,
  onError,
}: {
  station: StationSummary;
  accessToken: string;
  editable: boolean;
  onUpdated: () => void;
  onError: (message: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savedName, setSavedName] = useState(station.name);
  const [savedMin, setSavedMin] = useState(String(station.score_min));
  const [savedMax, setSavedMax] = useState(String(station.score_max));
  const [savedStep, setSavedStep] = useState(String(station.score_step));

  async function handleSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    onError("");
    try {
      await updateStation(station.id, accessToken, {
        name: savedName.trim(),
        score_min: Number(savedMin),
        score_max: Number(savedMax),
        score_step: Number(savedStep),
      });
      setEditing(false);
      onUpdated();
    } catch (requestError) {
      onError(messageFor(requestError));
    } finally {
      setSaving(false);
    }
  }

  return (
    <article className="workspace-card station-admin-card">
      {editing ? (
        <form className="workspace-form station-edit-form" onSubmit={(event) => void handleSave(event)}>
          <label>Название<input required maxLength={200} value={savedName} onChange={(event) => setSavedName(event.target.value)} /></label>
          <label>Минимум<input type="number" min="0" required value={savedMin} onChange={(event) => setSavedMin(event.target.value)} /></label>
          <label>Максимум<input type="number" min="0" required value={savedMax} onChange={(event) => setSavedMax(event.target.value)} /></label>
          <label>Шаг<input type="number" min="1" required value={savedStep} onChange={(event) => setSavedStep(event.target.value)} /></label>
          <div className="form-actions"><button className="primary-button" disabled={saving}>{saving ? "Сохраняем…" : "Сохранить"}</button><button type="button" className="quiet-button" onClick={() => setEditing(false)}>Отмена</button></div>
        </form>
      ) : (
        <>
          <div className="station-admin-info">
            <strong>{station.name}</strong>
            <span>{station.score_min}–{station.score_max} баллов · шаг {station.score_step}</span>
          </div>
          {editable && <button className="quiet-button" onClick={() => setEditing(true)}>Настроить</button>}
        </>
      )}
    </article>
  );
}

function CreateStationForm({
  eventId,
  accessToken,
  onCreated,
  onError,
}: {
  eventId: number;
  accessToken: string;
  onCreated: () => void;
  onError: (message: string) => void;
}) {
  const [saving, setSaving] = useState(false);
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setSaving(true);
    onError("");
    try {
      await createStation(eventId, accessToken, {
        name: String(form.get("stationName") ?? "").trim(),
        score_min: Number(form.get("scoreMin")),
        score_max: Number(form.get("scoreMax")),
        score_step: Number(form.get("scoreStep")),
      });
      formElement.reset();
      onCreated();
    } catch (requestError) {
      onError(messageFor(requestError));
    } finally {
      setSaving(false);
    }
  }
  return (
    <form className="workspace-form create-station-form" onSubmit={(event) => void handleSubmit(event)}>
      <h3>Добавить площадку</h3>
      <label>Название<input name="stationName" required maxLength={200} /></label>
      <label>Минимум<input name="scoreMin" type="number" min="0" defaultValue="0" required /></label>
      <label>Максимум<input name="scoreMax" type="number" min="0" defaultValue="10" required /></label>
      <label>Шаг<input name="scoreStep" type="number" min="1" defaultValue="1" required /></label>
      <button className="primary-button" disabled={saving}>{saving ? "Создаём…" : "Добавить площадку"}</button>
    </form>
  );
}

function RegisterParticipantForm({
  eventId,
  accessToken,
  routeSheets,
  onRegistered,
  onError,
}: {
  eventId: number;
  accessToken: string;
  routeSheets: RouteSheetSummary[];
  onRegistered: () => void;
  onError: (message: string) => void;
}) {
  const [saving, setSaving] = useState(false);
  const [registeredNumber, setRegisteredNumber] = useState("");
  const hasAvailableRouteSheet = routeSheets.length === 0 || routeSheets.some(
    (sheet) => sheet.capacity === null || sheet.registered_count < sheet.capacity,
  );
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setSaving(true);
    setRegisteredNumber("");
    onError("");
    try {
      const participant = await registerParticipant(eventId, accessToken, {
        first_name: String(form.get("firstName") ?? "").trim(),
        last_name: String(form.get("lastName") ?? "").trim(),
        workplace_or_study: String(form.get("workplaceOrStudy") ?? "").trim(),
        phone: String(form.get("phone") ?? "").trim(),
      }, Number(form.get("routeSheetId")) || null, String(form.get("registrationNumber") ?? "").trim());
      setRegisteredNumber(participant.registration_number);
      formElement.reset();
      onRegistered();
    } catch (requestError) {
      onError(messageFor(requestError));
    } finally {
      setSaving(false);
    }
  }
  return (
    <>
      <form className="workspace-form registration-form" onSubmit={(event) => void handleSubmit(event)}>
        <label>Имя<input name="firstName" required maxLength={100} /></label>
        <label>Фамилия<input name="lastName" required maxLength={100} /></label>
        <label>Номер участника
          <input
            name="registrationNumber"
            inputMode="numeric"
            required
            minLength={6}
            maxLength={6}
            pattern="[0-9]{6}"
            placeholder="000001"
          />
        </label>
        <label>Место работы/учёбы<input name="workplaceOrStudy" maxLength={300} /></label>
        <label>Номер телефона<input name="phone" type="tel" maxLength={50} autoComplete="tel" /></label>
        {routeSheets.length > 0 && (
          <label>Маршрутный лист
            <select name="routeSheetId" required defaultValue="">
              <option value="" disabled>Выберите маршрут</option>
              {routeSheets.map((sheet) => (
                <option
                  key={sheet.id}
                  value={sheet.id}
                  disabled={sheet.capacity !== null && sheet.registered_count >= sheet.capacity}
                >
                  {sheet.name} · {sheet.stations.map((station) => station.name).join(", ")}
                  {sheet.capacity === null ? "" : ` (${sheet.registered_count}/${sheet.capacity})`}
                </option>
              ))}
            </select>
          </label>
        )}
        <button className="primary-button" disabled={saving || !hasAvailableRouteSheet}>{saving ? "Регистрируем…" : "Зарегистрировать"}</button>
      </form>
      {!hasAvailableRouteSheet && <p className="backend-gap-note">Свободных мест на маршрутных листах нет.</p>}
      {registeredNumber && <p className="success-message" role="status">Участник зарегистрирован. Номер: <strong>{registeredNumber}</strong></p>}
    </>
  );
}

function RouteSheetsPanel({
  eventId,
  accessToken,
  stations,
  routeSheets,
  onChanged,
}: {
  eventId: number;
  accessToken: string;
  stations: StationSummary[];
  routeSheets: RouteSheetSummary[];
  onChanged: () => void;
}) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [editingSheetId, setEditingSheetId] = useState<number | null>(null);
  async function handleDelete(routeSheetId: number) {
    setSaving(true);
    setError("");
    try {
      await deleteRouteSheet(routeSheetId, accessToken);
      onChanged();
    } catch (requestError) {
      setError(messageFor(requestError));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="workspace-card route-sheets-panel">
      <h3>Маршрутные листы</h3>
      <p className="backend-gap-note">Выберите набор площадок и при необходимости ограничьте число участников.</p>
      {routeSheets.map((sheet) => (
        <div key={sheet.id}>
          <div className="route-sheet-row">
            <strong>{sheet.name}</strong>
            <span>{sheet.stations.map((station) => station.name).join(", ")}</span>
            <span>
              {sheet.capacity === null
                ? `${sheet.registered_count} участников · без лимита`
                : `${sheet.registered_count}/${sheet.capacity} участников`}
            </span>
            <div className="form-actions">
              <button
                className="quiet-button"
                disabled={saving}
                onClick={() => setEditingSheetId((current) => current === sheet.id ? null : sheet.id)}
              >
                {editingSheetId === sheet.id ? "Закрыть" : "Изменить"}
              </button>
              <button
                className="quiet-button"
                disabled={saving || sheet.registered_count > 0}
                onClick={() => void handleDelete(sheet.id)}
                title={sheet.registered_count > 0 ? "Нельзя удалить назначенный участникам маршрут" : undefined}
              >
                Удалить
              </button>
            </div>
          </div>
          {editingSheetId === sheet.id && (
            <RouteSheetForm
              key={sheet.id}
              eventId={eventId}
              accessToken={accessToken}
              stations={stations}
              routeSheet={sheet}
              saving={saving}
              onSaving={setSaving}
              onError={setError}
              onSaved={() => {
                setEditingSheetId(null);
                onChanged();
              }}
            />
          )}
        </div>
      ))}
      <RouteSheetForm
        eventId={eventId}
        accessToken={accessToken}
        stations={stations}
        saving={saving}
        onSaving={setSaving}
        onError={setError}
        onSaved={onChanged}
      />
      {error && <p className="form-error" role="alert">{error}</p>}
    </section>
  );
}

function RouteSheetForm({
  eventId,
  accessToken,
  stations,
  routeSheet,
  saving,
  onSaving,
  onError,
  onSaved,
}: {
  eventId: number;
  accessToken: string;
  stations: StationSummary[];
  routeSheet?: RouteSheetSummary;
  saving: boolean;
  onSaving: (value: boolean) => void;
  onError: (message: string) => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState(routeSheet?.name ?? "");
  const [capacity, setCapacity] = useState(routeSheet?.capacity?.toString() ?? "");
  const [selectedStationIds, setSelectedStationIds] = useState<number[]>(
    routeSheet?.stations.map((station) => station.id) ?? [],
  );

  function setAllStations(checked: boolean) {
    setSelectedStationIds(checked ? stations.map((station) => station.id) : []);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSaving(true);
    onError("");
    const payload = {
      name: name.trim(),
      capacity: capacity.trim() ? Number(capacity) : null,
      station_ids: selectedStationIds,
    };
    try {
      if (routeSheet) {
        await updateRouteSheet(routeSheet.id, accessToken, payload);
      } else {
        await createRouteSheet(eventId, accessToken, payload);
      }
      onSaved();
    } catch (requestError) {
      onError(messageFor(requestError));
    } finally {
      onSaving(false);
    }
  }

  return (
    <form className="workspace-form route-sheet-create-form" onSubmit={(event) => void handleSubmit(event)}>
      <h4>{routeSheet ? "Изменить маршрутный лист" : "Создать маршрутный лист"}</h4>
      <label>Название маршрутного листа<input value={name} onChange={(event) => setName(event.target.value)} required maxLength={100} /></label>
      <label>Вместимость (необязательно)<input value={capacity} onChange={(event) => setCapacity(event.target.value)} type="number" min="1" step="1" /></label>
      <fieldset className="station-checkbox-fieldset">
        <legend>Площадки · выбрано {selectedStationIds.length}</legend>
        <div className="station-checkbox-actions">
          <button type="button" className="quiet-button" onClick={() => setAllStations(true)}>Выбрать все</button>
          <button type="button" className="quiet-button" onClick={() => setAllStations(false)}>Снять все</button>
        </div>
        <div className="station-checkbox-list">
          {stations.map((station) => (
            <label key={station.id}>
              <input
                type="checkbox"
                checked={selectedStationIds.includes(station.id)}
                onChange={(event) => setSelectedStationIds((current) => (
                  event.target.checked
                    ? [...current, station.id]
                    : current.filter((id) => id !== station.id)
                ))}
              />
              {station.name}
            </label>
          ))}
        </div>
      </fieldset>
      <button className="primary-button" disabled={saving || stations.length === 0 || selectedStationIds.length === 0}>
        {saving ? "Сохраняем…" : routeSheet ? "Сохранить маршрутный лист" : "Создать маршрутный лист"}
      </button>
    </form>
  );
}

export function RegistrationPage() {
  const { user } = useAuth();
  const [events, setEvents] = useState<EventSummary[]>([]);
  const [selectedEventId, setSelectedEventId] = useState<number | null>(null);
  const [routeSheets, setRouteSheets] = useState<RouteSheetSummary[]>([]);
  const [loadedEventId, setLoadedEventId] = useState<number | null>(null);
  const [eventsLoaded, setEventsLoaded] = useState(false);
  const [error, setError] = useState("");
  const [routeSheetRefresh, setRouteSheetRefresh] = useState(0);
  useEffect(() => {
    if (!user?.is_system_admin) return;
    const controller = new AbortController();
    getEvents("", controller.signal)
      .then((result) => {
        setEvents(result);
        setSelectedEventId(result[0]?.id ?? null);
      })
      .catch((requestError: unknown) => {
        if (!controller.signal.aborted) setError(messageFor(requestError));
      })
      .finally(() => {
        if (!controller.signal.aborted) setEventsLoaded(true);
      });
    return () => controller.abort();
  }, [user]);

  useEffect(() => {
    if (!user?.is_system_admin || selectedEventId === null) return;
    const controller = new AbortController();
    getRouteSheets(selectedEventId, "", controller.signal)
      .then((result) => {
        setRouteSheets(result);
        setLoadedEventId(selectedEventId);
      })
      .catch((requestError: unknown) => {
        if (!controller.signal.aborted) {
          setRouteSheets([]);
          setLoadedEventId(selectedEventId);
          setError(messageFor(requestError));
        }
      });
    return () => controller.abort();
  }, [routeSheetRefresh, selectedEventId, user]);

  const selectedEvent = events.find((event) => event.id === selectedEventId) ?? null;
  const visibleRouteSheets = loadedEventId === selectedEventId ? routeSheets : [];
  const loading = Boolean(user?.is_system_admin) && !eventsLoaded;

  return (
    <AuthenticatedPage title="Регистрация участника" description="Системный администратор регистрирует участников и задаёт их шестизначные номера.">
      {loading && <AuthLoading />}
      {user && !user.is_system_admin && <p className="form-error" role="alert">Регистрация доступна только системному администратору.</p>}
      {error && <p className="form-error" role="alert">{error}</p>}
      {!loading && user?.is_system_admin && (
        <>
          {selectedEvent && (
            <label className="event-select-label">Мероприятие
              <select value={selectedEventId ?? ""} onChange={(event) => {
                setSelectedEventId(Number(event.target.value));
                setError("");
              }}>
                {events.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
              </select>
            </label>
          )}
          {selectedEvent && loadedEventId === selectedEvent.id && (
            <RegisterParticipantForm
              eventId={selectedEvent.id}
              accessToken=""
              routeSheets={visibleRouteSheets}
              onRegistered={() => setRouteSheetRefresh((value) => value + 1)}
              onError={setError}
            />
          )}
          {!selectedEvent && <p className="empty-workspace">Сначала создайте мероприятие.</p>}
        </>
      )}
    </AuthenticatedPage>
  );
}

export function ScoringPage() {
  const [accountLogin, setAccountLogin] = useState(false);
  return accountLogin
    ? <AccountScoringPage />
    : <CodeScoringPage onUseAccountLogin={() => setAccountLogin(true)} />;
}

function CodeScoringPage({ onUseAccountLogin }: { onUseAccountLogin: () => void }) {
  const [code, setCode] = useState("");
  const [access, setAccess] = useState<VerifiedAccess | null>(null);
  const [registrationNumber, setRegistrationNumber] = useState("");
  const [participant, setParticipant] = useState<ParticipantLookup | null>(null);
  const [points, setPoints] = useState(0);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const station = access?.station ?? null;

  async function handleVerify(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorking(true);
    setError("");
    try {
      const verified = await verifyAccessCode(code.trim());
      if (verified.role !== "station_operator" || !verified.station) {
        setError("Этот код не предназначен для начисления баллов на площадке.");
        return;
      }
      setAccess(verified);
      setPoints(verified.station.score_min);
      setCode("");
    } catch (requestError) {
      setError(messageFor(requestError));
    } finally {
      setWorking(false);
    }
  }

  async function handleLookup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!access) return;
    setWorking(true);
    setError("");
    setSuccess("");
    setParticipant(null);
    try {
      const result = await lookupWithAccessCode(access.access_token, registrationNumber);
      setParticipant(result);
      if (result.already_scored && result.score) {
        setSuccess(result.score.is_annulled
          ? "Результат аннулирован администратором. Повторное начисление запрещено."
          : `Участник уже прошёл эту площадку: ${result.score.points} баллов.`);
      }
    } catch (requestError) {
      setError(messageFor(requestError));
    } finally {
      setWorking(false);
    }
  }

  async function handleSubmitScore() {
    if (!access || !participant || participant.already_scored || !station) return;
    setWorking(true);
    setError("");
    setSuccess("");
    try {
      const score = await submitScoreWithAccessCode(
        access.access_token,
        participant.event_participant_id,
        points,
      );
      setParticipant((current) => current ? { ...current, already_scored: true, score } : current);
      setSuccess(`Начислено ${score.points} баллов. Повторное начисление на этой площадке запрещено.`);
    } catch (requestError) {
      if (requestError instanceof ApiError && requestError.status === 409) {
        try {
          const current = await lookupWithAccessCode(access.access_token, registrationNumber);
          setParticipant(current);
          if (current.already_scored && current.score) {
            setSuccess(`Начисление уже сохранено: ${current.score.points} баллов.`);
            return;
          }
        } catch (lookupError) {
          setError(messageFor(lookupError));
          return;
        }
      }
      setError(messageFor(requestError));
    } finally {
      setWorking(false);
    }
  }

  return (
    <main className="workspace-page">
      <WorkspaceHeading title="Начисление баллов" description="Введите код доступа к площадке. Площадка будет определена автоматически." />
      {!access ? (
        <form className="workspace-card access-entry-form" onSubmit={(event) => void handleVerify(event)}>
          <label htmlFor="station-access-code">Код доступа площадки</label>
          <input id="station-access-code" value={code} onChange={(event) => setCode(event.target.value)} required minLength={8} maxLength={128} autoComplete="off" />
          <button className="primary-button" disabled={working}>{working ? "Проверяем…" : "Войти на площадку"}</button>
        </form>
      ) : (
        <>
          <section className="workspace-card scoring-controls code-scoring-controls">
            <div><span className="eyebrow">ВАША ПЛОЩАДКА</span><strong>{station?.name}</strong></div>
            <p className="scoring-scale">{station?.score_min}–{station?.score_max} баллов · шаг {station?.score_step}</p>
            <button className="quiet-button" disabled={working} onClick={() => { setAccess(null); setParticipant(null); setSuccess(""); }}>Выйти с площадки</button>
          </section>
          <section className="workspace-card scoring-card">
            <form className="lookup-form" onSubmit={(event) => void handleLookup(event)}>
              <label htmlFor="participant-code">Шестизначный номер участника</label>
              <div>
                <input
                  id="participant-code"
                  inputMode="numeric"
                  pattern="[0-9]{6}"
                  maxLength={6}
                  required
                  value={registrationNumber}
                  onChange={(event) => { setRegistrationNumber(event.target.value.replace(/\D/g, "").slice(0, 6)); setParticipant(null); setSuccess(""); }}
                  placeholder="000001"
                />
                <button className="primary-button" disabled={working || registrationNumber.length !== 6}>{working ? "Ищем…" : "Найти"}</button>
              </div>
            </form>
            {participant && (
              <div className="participant-confirmation">
                <p className="eyebrow">УЧАСТНИК НАЙДЕН</p>
                <h2>{participant.first_name} {participant.last_name}</h2>
                <p>Номер {participant.registration_number}</p>
                {participant.already_scored ? (
                  <div className="already-scored-message" role="status">
                    {participant.score?.is_annulled
                      ? "Результат аннулирован администратором. Повторное начисление запрещено."
                      : <>Эта площадка уже пройдена. Ранее начислено <strong>{participant.score?.points ?? 0}</strong> баллов.</>}
                  </div>
                ) : station && (
                  <>
                    <div className="stepper" aria-label="Количество баллов">
                      <button aria-label="Уменьшить баллы" disabled={working || points <= station.score_min} onClick={() => setPoints((value) => Math.max(station.score_min, value - station.score_step))}>−</button>
                      <output aria-live="polite">{points}</output>
                      <button aria-label="Увеличить баллы" disabled={working || points >= station.score_max} onClick={() => setPoints((value) => Math.min(station.score_max, value + station.score_step))}>+</button>
                    </div>
                    <p className="stepper-hint">Шаг {station.score_step} · максимум {station.score_max}</p>
                    <button className="primary-button submit-score-button" disabled={working || points < station.score_min || points > station.score_max || (points - station.score_min) % station.score_step !== 0} onClick={() => void handleSubmitScore()}>
                      {working ? "Сохраняем…" : "Подтвердить баллы"}
                    </button>
                  </>
                )}
              </div>
            )}
            {success && <p className="success-message" role="status">{success}</p>}
          </section>
        </>
      )}
      {error && <p className="form-error" role="alert">{error}</p>}
      <button className="quiet-button staff-account-link" onClick={onUseAccountLogin}>Войти через учётную запись держателя площадки</button>
    </main>
  );
}

function AccountScoringPage() {
  const { user } = useAuth();
  const accessToken = "";
  const [events, setEvents] = useState<EventSummary[]>([]);
  const [selectedEventId, setSelectedEventId] = useState<number | null>(null);
  const [stations, setStations] = useState<StationSummary[]>([]);
  const [stationsEventId, setStationsEventId] = useState<number | null>(null);
  const [selectedStationId, setSelectedStationId] = useState<number | null>(null);
  const [registrationNumber, setRegistrationNumber] = useState("");
  const [participant, setParticipant] = useState<ParticipantLookup | null>(null);
  const [points, setPoints] = useState(0);
  const [eventsLoaded, setEventsLoaded] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const visibleStations = stationsEventId === selectedEventId ? stations : [];
  const selectedStation = visibleStations.find((station) => station.id === selectedStationId) ?? null;
  const loading = !eventsLoaded || (selectedEventId !== null && stationsEventId !== selectedEventId);

  useEffect(() => {
    if (!user) return;
    const controller = new AbortController();
    let active = true;
    getEvents(accessToken, controller.signal)
      .then((nextEvents) => {
        if (!active) return;
        setEvents(nextEvents);
        setSelectedEventId(nextEvents[0]?.id ?? null);
        setError("");
      })
      .catch((requestError: unknown) => {
        if (active && !controller.signal.aborted) setError(messageFor(requestError));
      })
      .finally(() => {
        if (active) setEventsLoaded(true);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [accessToken, user]);

  useEffect(() => {
    if (selectedEventId === null) return;
    const controller = new AbortController();
    let active = true;
    getStations(selectedEventId, accessToken, controller.signal)
      .then((nextStations) => {
        if (!active) return;
        setStations(nextStations);
        setStationsEventId(selectedEventId);
        setSelectedStationId(nextStations[0]?.id ?? null);
        setPoints(nextStations[0]?.score_min ?? 0);
        setError("");
      })
      .catch((requestError: unknown) => {
        if (active && !controller.signal.aborted) {
          setStations([]);
          setStationsEventId(selectedEventId);
          setSelectedStationId(null);
          setError(messageFor(requestError));
        }
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [accessToken, selectedEventId]);

  const stationSummary = selectedStation
    ? `${selectedStation.score_min}–${selectedStation.score_max} баллов · шаг ${selectedStation.score_step}`
    : "";

  async function handleLookup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedStation) return;
    setWorking(true);
    setError("");
    setSuccess("");
    setParticipant(null);
    try {
      const result = await lookupParticipant(selectedStation.id, accessToken, registrationNumber);
      setParticipant(result);
      if (result.already_scored && result.score) {
        setSuccess(result.score.is_annulled
          ? "Начисление аннулировано администратором. Повторно начислить баллы нельзя."
          : `Участник уже прошёл эту площадку: ${result.score.points} баллов.`);
      }
    } catch (requestError) {
      setError(messageFor(requestError));
    } finally {
      setWorking(false);
    }
  }

  async function handleSubmitScore() {
    if (!selectedStation || !participant || participant.already_scored) return;
    setWorking(true);
    setError("");
    setSuccess("");
    try {
      const score = await submitScore(
        selectedStation.id,
        accessToken,
        participant.event_participant_id,
        points,
      );
      setParticipant((current) => current
        ? { ...current, already_scored: true, score }
        : current);
      setSuccess(`Начислено ${score.points} баллов. Повторное начисление на этой площадке запрещено.`);
    } catch (requestError) {
      setError(messageFor(requestError));
    } finally {
      setWorking(false);
    }
  }

  return (
    <AuthenticatedPage title="Начисление баллов" description="Войдите под учётной записью, которой назначена нужная площадка.">
      {loading && <AuthLoading />}
      {error && <p className="form-error" role="alert">{error}</p>}
      <>
        <section className="workspace-card scoring-controls">
          <label>Мероприятие
            <select value={selectedEventId ?? ""} onChange={(event) => {
              setSelectedEventId(Number(event.target.value));
              setSelectedStationId(null);
              setParticipant(null);
              setRegistrationNumber("");
              setPoints(0);
              setSuccess("");
            }}>
              {events.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </label>
          <label>Ваша площадка
            <select value={selectedStationId ?? ""} onChange={(event) => {
              const stationId = Number(event.target.value);
              setSelectedStationId(stationId);
              setParticipant(null);
              setRegistrationNumber("");
              setPoints(visibleStations.find((station) => station.id === stationId)?.score_min ?? 0);
              setSuccess("");
            }}>
              {visibleStations.map((station) => <option key={station.id} value={station.id}>{station.name}</option>)}
            </select>
          </label>
          {selectedStation && <p className="scoring-scale">{stationSummary}</p>}
          {!loading && selectedEventId !== null && visibleStations.length === 0 && <p className="backend-gap-note">Нет доступных площадок. Проверьте назначение роли для мероприятия.</p>}
        </section>
        {selectedStation && (
          <section className="workspace-card scoring-card">
            <form className="lookup-form" onSubmit={(event) => void handleLookup(event)}>
              <label htmlFor="participant-code">Шестизначный номер участника</label>
              <div>
                <input
                  id="participant-code"
                  inputMode="numeric"
                  pattern="[0-9]{6}"
                  maxLength={6}
                  required
                  value={registrationNumber}
                  onChange={(event) => setRegistrationNumber(event.target.value.replace(/\D/g, "").slice(0, 6))}
                  placeholder="000001"
                />
                <button className="primary-button" disabled={working || registrationNumber.length !== 6}>{working ? "Ищем…" : "Найти"}</button>
              </div>
            </form>
            {participant && (
              <div className="participant-confirmation">
                <p className="eyebrow">УЧАСТНИК НАЙДЕН</p>
                <h2>{participant.first_name} {participant.last_name}</h2>
                <p>Номер {participant.registration_number}</p>
                {participant.already_scored ? (
                  <div className="already-scored-message" role="status">
                    {participant.score?.is_annulled
                      ? "Результат аннулирован администратором. Повторное начисление на этой площадке запрещено."
                      : <>Эта площадка уже пройдена. Ранее начислено <strong>{participant.score?.points ?? 0}</strong> баллов.</>}
                  </div>
                ) : (
                  <>
                    <div className="stepper" aria-label="Количество баллов">
                      <button aria-label="Уменьшить баллы" disabled={working || points <= selectedStation.score_min} onClick={() => setPoints((value) => Math.max(selectedStation.score_min, value - selectedStation.score_step))}>−</button>
                      <output aria-live="polite">{points}</output>
                      <button aria-label="Увеличить баллы" disabled={working || points >= selectedStation.score_max} onClick={() => setPoints((value) => Math.min(selectedStation.score_max, value + selectedStation.score_step))}>+</button>
                    </div>
                    <p className="stepper-hint">Шаг {selectedStation.score_step} · максимум {selectedStation.score_max}</p>
                    <button className="primary-button submit-score-button" disabled={working || points < selectedStation.score_min || points > selectedStation.score_max} onClick={() => void handleSubmitScore()}>
                      {working ? "Сохраняем…" : "Подтвердить баллы"}
                    </button>
                  </>
                )}
                {success && <p className="success-message" role="status">{success}</p>}
              </div>
            )}
          </section>
        )}
        <p className="backend-gap-note">Доступ к площадке определяется коротким кодом, привязанным системным администратором. Повторное начисление и допустимая шкала проверяются сервером и базой данных.</p>
      </>
    </AuthenticatedPage>
  );
}
