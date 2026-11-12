import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import type { ReactNode } from "react";
import { ApiError } from "./api";
import {
  createAccessCode,
  createEvent,
  createOrganizer,
  createStation,
  correctScore,
  annulScore,
  getCurrentAccount,
  getAccessCodes,
  getEvents,
  getParticipants,
  getEventScores,
  getStations,
  lookupParticipant,
  lookupWithAccessCode,
  registerParticipant,
  registerWithAccessCode,
  revokeAccessCode,
  submitScore,
  submitScoreWithAccessCode,
  updateStation,
  verifyAccessCode,
} from "./api";
import type {
  AccessCodeSummary,
  CurrentAccount,
  CreatedOrganizer,
  EventSummary,
  ParticipantLookup,
  RegisteredParticipant,
  ScoreHistoryEntry,
  StationSummary,
  VerifiedAccess,
} from "./api";
import { oidcConfigured } from "./authClient";
import { useAuth } from "./authContext";

const EMPTY_PARTICIPANTS: RegisteredParticipant[] = [];

function messageFor(error: unknown): string {
  return error instanceof ApiError
    ? error.message
    : "Не удалось связаться с сервером. Проверьте подключение и повторите попытку.";
}

function AuthGate() {
  const { login, user, error: authError } = useAuth();
  return (
    <section className="workspace-card auth-gate">
      <p className="eyebrow">ЗАЩИЩЁННЫЙ ДОСТУП</p>
      <h2>{oidcConfigured ? "Войдите через Keycloak." : "Вход пока не настроен."}</h2>
      <p>
        {oidcConfigured
          ? "Доступ к действиям определяется назначенными ролями в мероприятии."
          : "Для входа задайте VITE_OIDC_AUTHORITY и VITE_OIDC_CLIENT_ID во frontend/.env.local, затем настройте OIDC-параметры backend."}
      </p>
      {authError && <p className="form-error" role="alert">{authError}</p>}
      {!user && (
        <button className="primary-button" disabled={!oidcConfigured} onClick={() => void login()}>
          Войти через Keycloak ↗
        </button>
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
        <span>{user.profile.name ?? user.profile.preferred_username ?? user.profile.email ?? "Авторизованный пользователь"}</span>
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

export function OrganizerPage() {
  const { user } = useAuth();
  const token = user?.access_token ?? "";
  const [account, setAccount] = useState<CurrentAccount | null>(null);
  const [events, setEvents] = useState<EventSummary[]>([]);
  const [selectedEventId, setSelectedEventId] = useState<number | null>(null);
  const [stations, setStations] = useState<StationSummary[]>([]);
  const [participants, setParticipants] = useState<RegisteredParticipant[]>([]);
  const [loading, setLoading] = useState(true);
  const [detailsEventId, setDetailsEventId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const [participantQuery, setParticipantQuery] = useState("");
  const selectedEvent = events.find((event) => event.id === selectedEventId) ?? null;
  const selectedAccess = account?.access.filter((access) => access.event_id === selectedEventId) ?? [];
  const canManage = selectedAccess.some((access) => access.role === "organizer");
  const canRegister = canManage || selectedAccess.some((access) => access.role === "registrar");
  const detailLoading = selectedEventId !== null && detailsEventId !== selectedEventId;
  const visibleStations = detailsEventId === selectedEventId ? stations : [];
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
    if (!token) return;
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
  }, [token]);

  useEffect(() => {
    if (!token || selectedEventId === null) return;
    const controller = new AbortController();
    let active = true;
    const participantRequest = canRegister
      ? getParticipants(selectedEventId, token, controller.signal)
      : Promise.resolve([]);
    Promise.all([
      getStations(selectedEventId, token, controller.signal),
      participantRequest,
    ])
      .then(([nextStations, nextParticipants]) => {
        if (!active) return;
        setStations(nextStations);
        setParticipants(nextParticipants);
        setDetailsEventId(selectedEventId);
        setError("");
      })
      .catch((requestError: unknown) => {
        if (active && !controller.signal.aborted) {
          setDetailsEventId(selectedEventId);
          setError(messageFor(requestError));
        }
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [canRegister, refreshKey, selectedEventId, token]);

  async function handleCreateEvent(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const name = String(form.get("eventName") ?? "").trim();
    const eventDate = String(form.get("eventDate") ?? "");
    try {
      setError("");
      setActionMessage("");
      const created = await createEvent(token, { name, event_date: eventDate });
      setEvents((current) => [...current, created]);
      setSelectedEventId(created.id);
      setActionMessage("Мероприятие создано.");
      formElement.reset();
    } catch (requestError) {
      setError(messageFor(requestError));
    }
  }

  return (
    <AuthenticatedPage title="Кабинет организатора" description="Управляйте мероприятиями, площадками и регистрациями.">
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
            {(account.is_system_admin || account.is_organizer) && (
              <form className="workspace-form event-create-form" onSubmit={(event) => void handleCreateEvent(event)}>
                <h3>Новое мероприятие</h3>
                <label>Название<input name="eventName" required maxLength={200} /></label>
                <label>Дата<input name="eventDate" type="date" required /></label>
                <button className="primary-button" type="submit">Создать мероприятие</button>
              </form>
            )}
          </section>
          {account.is_system_admin && <OrganizerProvisioningPanel accessToken={token} />}
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
                {canManage && <AccessCodesPanel eventId={selectedEvent.id} accessToken={token} stations={visibleStations} />}
              </section>
              {canRegister && (
                <section className="workspace-section">
                  <div className="workspace-section-heading">
                    <div><p className="eyebrow">УЧЁТ УЧАСТИЯ</p><h2>Участники</h2></div>
                    <span className="muted-status">{visibleParticipants.length} в списке</span>
                  </div>
                  <RegisterParticipantForm eventId={selectedEvent.id} accessToken={token} onRegistered={() => setRefreshKey((key) => key + 1)} onError={setError} />
                  <label className="participant-search">
                    <span className="visually-hidden">Поиск участника</span>
                    <input value={participantQuery} onChange={(event) => setParticipantQuery(event.target.value)} placeholder="Найти по имени или номеру" />
                  </label>
                  <div className="participant-admin-list">
                    {filteredParticipants.map((participant) => (
                      <div className="participant-admin-row" key={participant.id}>
                        <strong>{participant.first_name} {participant.last_name}</strong>
                        <span>№ {participant.registration_number}</span>
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

function OrganizerProvisioningPanel({ accessToken }: { accessToken: string }) {
  const [created, setCreated] = useState<CreatedOrganizer | null>(null);
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
      const organizer = await createOrganizer(accessToken, {
        username: String(form.get("username") ?? "").trim(),
        display_name: String(form.get("displayName") ?? "").trim(),
        email: String(form.get("email") ?? "").trim(),
      });
      setCreated(organizer);
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
        <div><p className="eyebrow">СИСТЕМНЫЙ ДОСТУП</p><h2>Учётные записи организаторов</h2></div>
      </div>
      <form className="workspace-form event-create-form" onSubmit={(event) => void handleSubmit(event)}>
        <label>Логин<input name="username" required minLength={3} maxLength={64} pattern="[a-zA-Z0-9._-]+" autoComplete="off" /></label>
        <label>Имя организатора<input name="displayName" required maxLength={200} /></label>
        <label>Email<input name="email" type="email" maxLength={254} /></label>
        <button className="primary-button" disabled={saving}>{saving ? "Создаём…" : "Создать организатора"}</button>
      </form>
      {error && <p className="form-error" role="alert">{error}</p>}
      {created && (
        <div className="workspace-card credential-card" role="status">
          <strong>Учётная запись создана</strong>
          <p>Передайте эти данные организатору безопасным способом. Временный пароль показывается только сейчас; при первом входе его нужно заменить.</p>
          <dl>
            <div><dt>Логин</dt><dd>{created.username}</dd></div>
            <div><dt>Временный пароль</dt><dd><code>{created.temporary_password}</code></dd></div>
          </dl>
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
  const [role, setRole] = useState<AccessCodeSummary["role"]>("registrar");
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
    if (role === "station_operator" && !stationId) {
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
        station_id: role === "station_operator" ? Number(stationId) : null,
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
        <label>Кому
          <select value={role} onChange={(event) => setRole(event.target.value as AccessCodeSummary["role"])}>
            <option value="registrar">Регистратору</option>
            <option value="station_operator">Сотруднику площадки</option>
          </select>
        </label>
        {role === "station_operator" && (
          <label>Площадка
            <select value={stationId} required onChange={(event) => setStationId(event.target.value)}>
              <option value="">Выберите площадку</option>
              {stations.map((station) => <option key={station.id} value={station.id}>{station.name}</option>)}
            </select>
          </label>
        )}
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
        <button className="primary-button" disabled={busy || code.length < 8 || (role === "station_operator" && stations.length === 0)}>{busy ? "Сохраняем…" : "Создать код"}</button>
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
              <span>{code.role === "registrar" ? "Регистратор" : `Площадка: ${code.station_name ?? "не указана"}`}</span>
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
  onRegistered,
  onError,
}: {
  eventId: number;
  accessToken: string;
  onRegistered: () => void;
  onError: (message: string) => void;
}) {
  const [saving, setSaving] = useState(false);
  const [registeredNumber, setRegisteredNumber] = useState("");
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
      });
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
        <button className="primary-button" disabled={saving}>{saving ? "Регистрируем…" : "Зарегистрировать"}</button>
      </form>
      {registeredNumber && <p className="success-message" role="status">Участник зарегистрирован. Номер: <strong>{registeredNumber}</strong></p>}
    </>
  );
}

export function RegistrationPage() {
  const [code, setCode] = useState("");
  const [access, setAccess] = useState<VerifiedAccess | null>(null);
  const [registeredNumber, setRegisteredNumber] = useState("");
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");

  async function handleVerify(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorking(true);
    setError("");
    try {
      const verified = await verifyAccessCode(code.trim());
      if (verified.role !== "registrar") {
        setError("Этот код не предназначен для регистрации участников.");
        return;
      }
      setAccess(verified);
      setCode("");
    } catch (requestError) {
      setError(messageFor(requestError));
    } finally {
      setWorking(false);
    }
  }

  async function handleRegister(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!access) return;
    const formElement = event.currentTarget;
    const formData = new FormData(formElement);
    setWorking(true);
    setError("");
    try {
      const participant = await registerWithAccessCode(access.access_token, {
        first_name: String(formData.get("firstName") ?? "").trim(),
        last_name: String(formData.get("lastName") ?? "").trim(),
      });
      setRegisteredNumber(participant.registration_number);
      formElement.reset();
    } catch (requestError) {
      setError(messageFor(requestError));
    } finally {
      setWorking(false);
    }
  }

  return (
    <main className="workspace-page">
      <WorkspaceHeading title="Регистрация участника" description="Введите код, полученный у организатора, и заполните имя участника." />
      {!access ? (
        <form className="workspace-card access-entry-form" onSubmit={(event) => void handleVerify(event)}>
          <label htmlFor="registration-access-code">Код регистрации</label>
          <input id="registration-access-code" value={code} onChange={(event) => setCode(event.target.value)} required minLength={8} maxLength={128} autoComplete="off" />
          <button className="primary-button" disabled={working}>{working ? "Проверяем…" : "Продолжить"}</button>
        </form>
      ) : (
        <>
          <div className="workspace-card access-context">
            <p className="eyebrow">ДОСТУП ПОДТВЕРЖДЁН</p>
            <p>Регистрация участника мероприятия № {access.event_id}</p>
            <button className="quiet-button" onClick={() => { setAccess(null); setRegisteredNumber(""); }}>Ввести другой код</button>
          </div>
          {!registeredNumber ? (
            <form className="workspace-card workspace-form registration-form access-registration-form" onSubmit={(event) => void handleRegister(event)}>
              <label>Имя<input name="firstName" required maxLength={100} /></label>
              <label>Фамилия<input name="lastName" required maxLength={100} /></label>
              <button className="primary-button" disabled={working}>{working ? "Регистрируем…" : "Зарегистрировать"}</button>
            </form>
          ) : (
            <div className="workspace-card registration-result" role="status">
              <span>Ваш номер участника</span>
              <strong>{registeredNumber}</strong>
              <p>Сохраните номер — он понадобится для начисления баллов.</p>
              <button className="primary-button" onClick={() => setRegisteredNumber("")}>Зарегистрировать следующего участника</button>
            </div>
          )}
        </>
      )}
      {error && <p className="form-error" role="alert">{error}</p>}
    </main>
  );
}

export function ScoringPage() {
  const [accountLogin, setAccountLogin] = useState(false);
  return accountLogin
    ? <OidcScoringPage />
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
          ? "Результат аннулирован организатором. Повторное начисление запрещено."
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
      <WorkspaceHeading title="Начисление баллов" description="Введите код площадки, выданный организатором. Площадка будет определена автоматически." />
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
                      ? "Результат аннулирован организатором. Повторное начисление запрещено."
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
      <button className="quiet-button staff-account-link" onClick={onUseAccountLogin}>Войти через учётную запись организации</button>
    </main>
  );
}

function OidcScoringPage() {
  const { user } = useAuth();
  const accessToken = user?.access_token ?? "";
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
    if (!accessToken) return;
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
  }, [accessToken]);

  useEffect(() => {
    if (!accessToken || selectedEventId === null) return;
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
    if (!selectedStation || !accessToken) return;
    setWorking(true);
    setError("");
    setSuccess("");
    setParticipant(null);
    try {
      const result = await lookupParticipant(selectedStation.id, accessToken, registrationNumber);
      setParticipant(result);
      if (result.already_scored && result.score) {
        setSuccess(result.score.is_annulled
          ? "Начисление аннулировано организатором. Повторно начислить баллы нельзя."
          : `Участник уже прошёл эту площадку: ${result.score.points} баллов.`);
      }
    } catch (requestError) {
      setError(messageFor(requestError));
    } finally {
      setWorking(false);
    }
  }

  async function handleSubmitScore() {
    if (!selectedStation || !participant || participant.already_scored || !accessToken) return;
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
      {accessToken && (
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
                        ? "Результат аннулирован организатором. Повторное начисление на этой площадке запрещено."
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
          <p className="backend-gap-note">Проверка кода площадки пока не поддерживается Backend. Сейчас сотрудник входит через Keycloak; право на площадку проверяется сервером. Повторное начисление и шкала также проверяются сервером и базой.</p>
        </>
      )}
    </AuthenticatedPage>
  );
}
