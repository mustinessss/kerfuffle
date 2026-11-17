import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import {
  acceptOrganizerInvitation,
  completePasswordReset,
  createLocalPasswordResetLink,
  getAdminInvitations,
  getAdminUsers,
  getEvents,
  inviteOrganizer,
  requestPasswordReset,
  resendInvitation,
  revokeInvitation,
  setOrganizerEventAccess,
  setUserBlocked,
} from "./api";
import type { AdminInvitation, AdminUser, EventSummary } from "./api";
import { ApiError } from "./api";
import { useAuth } from "./authContext";

function messageFor(error: unknown): string {
  return error instanceof ApiError
    ? error.message
    : "Не удалось связаться с сервером. Проверьте подключение и повторите попытку.";
}

function ErrorMessage({ children }: { children: string }) {
  return children ? <p className="form-error" role="alert">{children}</p> : null;
}

function passwordMatchesPolicy(value: string) {
  return value.length >= 12
    && /[a-z]/.test(value)
    && /[A-Z]/.test(value)
    && /\d/.test(value);
}

export function LoginPage() {
  const { user, loading } = useAuth();
  return (
    <main className="workspace-page">
      <div className="workspace-heading">
        <p className="eyebrow">ЗАЩИЩЁННЫЙ ДОСТУП</p>
        <h1>Вход<span className="accent-dot">.</span></h1>
        <p>Войдите в кабинет организатора или администратора.</p>
      </div>
      {loading
        ? <div className="state-box" role="status"><span className="spinner" />Проверяем сессию…</div>
        : user
          ? <div className="workspace-card">Вы вошли как {user.display_name}. <a href="/organizer">Перейти в кабинет</a></div>
          : <LoginForm />}
    </main>
  );
}

export function LoginForm() {
  const { login, error: authError, clearError } = useAuth();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setSaving(true);
    setError("");
    clearError();
    try {
      await login(String(form.get("email") ?? ""), String(form.get("password") ?? ""));
      window.location.assign("/organizer");
    } catch (requestError) {
      setError(messageFor(requestError));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="workspace-card workspace-form login-form" onSubmit={(event) => void submit(event)}>
      <label>Email<input name="email" type="email" autoComplete="username" required maxLength={254} /></label>
      <label>Пароль<input name="password" type="password" autoComplete="current-password" required /></label>
      <ErrorMessage>{error || authError}</ErrorMessage>
      <button className="primary-button" disabled={saving}>{saving ? "Входим…" : "Войти"}</button>
      <a className="quiet-button" href="/forgot-password">Забыли пароль?</a>
    </form>
  );
}

export function InvitationPage() {
  const token = new URLSearchParams(window.location.search).get("token") ?? "";
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const password = String(form.get("password") ?? "");
    const confirmation = String(form.get("confirmation") ?? "");
    if (password !== confirmation) {
      setError("Пароли не совпадают.");
      return;
    }
    if (!passwordMatchesPolicy(password)) {
      setError("Нужен пароль от 12 символов со строчными и заглавными буквами и цифрой.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await acceptOrganizerInvitation({
        token,
        display_name: String(form.get("displayName") ?? "").trim(),
        password,
      });
      setSuccess("Аккаунт активирован. Теперь можно войти.");
    } catch (requestError) {
      setError(messageFor(requestError));
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="workspace-page">
      <div className="workspace-heading">
        <p className="eyebrow">АКТИВАЦИЯ АККАУНТА</p>
        <h1>Приглашение<span className="accent-dot">.</span></h1>
        <p>Создайте пароль организатора. Ссылка одноразовая и действует ограниченное время.</p>
      </div>
      {success
        ? <div className="workspace-card"><p className="success-message">{success}</p><a className="primary-button" href="/login">Перейти ко входу</a></div>
        : token
          ? <form className="workspace-card workspace-form login-form" onSubmit={(event) => void submit(event)}>
              <label>Имя<input name="displayName" required maxLength={200} autoComplete="name" /></label>
              <label>Пароль<input name="password" type="password" required minLength={12} autoComplete="new-password" /></label>
              <label>Повторите пароль<input name="confirmation" type="password" required minLength={12} autoComplete="new-password" /></label>
              <ErrorMessage>{error}</ErrorMessage>
              <button className="primary-button" disabled={saving}>{saving ? "Активируем…" : "Создать аккаунт"}</button>
            </form>
          : <div className="state-box error-box" role="alert">В ссылке нет токена приглашения. Попросите администратора отправить новое приглашение.</div>}
    </main>
  );
}

export function ForgotPasswordPage() {
  const [saving, setSaving] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const email = String(new FormData(event.currentTarget).get("email") ?? "");
    setSaving(true);
    setError("");
    try {
      await requestPasswordReset(email);
      setSubmitted(true);
    } catch (requestError) {
      setError(messageFor(requestError));
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="workspace-page">
      <div className="workspace-heading"><p className="eyebrow">ВОССТАНОВЛЕНИЕ ДОСТУПА</p><h1>Сброс пароля<span className="accent-dot">.</span></h1></div>
      {submitted
        ? <div className="workspace-card">Если активный аккаунт с таким email существует, инструкция по сбросу будет отправлена на него.</div>
        : <form className="workspace-card workspace-form login-form" onSubmit={(event) => void submit(event)}>
            <label>Email<input name="email" type="email" required maxLength={254} autoComplete="email" /></label>
            <ErrorMessage>{error}</ErrorMessage>
            <button className="primary-button" disabled={saving}>{saving ? "Отправляем…" : "Отправить ссылку"}</button>
          </form>}
    </main>
  );
}

export function ResetPasswordPage() {
  const token = new URLSearchParams(window.location.search).get("token") ?? "";
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const password = String(form.get("password") ?? "");
    if (password !== String(form.get("confirmation") ?? "")) {
      setError("Пароли не совпадают.");
      return;
    }
    if (!passwordMatchesPolicy(password)) {
      setError("Нужен пароль от 12 символов со строчными и заглавными буквами и цифрой.");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await completePasswordReset({ token, password });
      setDone(true);
    } catch (requestError) {
      setError(messageFor(requestError));
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="workspace-page">
      <div className="workspace-heading"><p className="eyebrow">ВОССТАНОВЛЕНИЕ ДОСТУПА</p><h1>Новый пароль<span className="accent-dot">.</span></h1></div>
      {done
        ? <div className="workspace-card">Пароль изменён. Все активные сеансы завершены. <a href="/login">Войти</a></div>
        : token
          ? <form className="workspace-card workspace-form login-form" onSubmit={(event) => void submit(event)}>
              <label>Новый пароль<input name="password" type="password" required minLength={12} autoComplete="new-password" /></label>
              <label>Повторите пароль<input name="confirmation" type="password" required minLength={12} autoComplete="new-password" /></label>
              <ErrorMessage>{error}</ErrorMessage>
              <button className="primary-button" disabled={saving}>{saving ? "Сохраняем…" : "Сохранить пароль"}</button>
            </form>
          : <div className="state-box error-box" role="alert">В ссылке отсутствует токен сброса пароля.</div>}
    </main>
  );
}

export function AdminUsersPage() {
  const { user } = useAuth();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [invitations, setInvitations] = useState<AdminInvitation[]>([]);
  const [events, setEvents] = useState<EventSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [inviteUrl, setInviteUrl] = useState("");
  const [resetUrl, setResetUrl] = useState("");
  const [saving, setSaving] = useState(false);

  async function refresh() {
    const [nextUsers, nextInvitations, nextEvents] = await Promise.all([
      getAdminUsers(),
      getAdminInvitations(),
      getEvents(),
    ]);
    setUsers(nextUsers);
    setInvitations(nextInvitations);
    setEvents(nextEvents);
  }

  useEffect(() => {
    let active = true;
    Promise.all([getAdminUsers(), getAdminInvitations(), getEvents()])
      .then(([nextUsers, nextInvitations, nextEvents]) => {
        if (!active) return;
        setUsers(nextUsers);
        setInvitations(nextInvitations);
        setEvents(nextEvents);
      })
      .catch((requestError: unknown) => {
        if (active) setError(messageFor(requestError));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, []);

  if (!user?.is_system_admin) {
    return <main className="workspace-page"><div className="workspace-heading"><h1>Пользователи<span className="accent-dot">.</span></h1></div><div className="state-box error-box">Раздел доступен только системному администратору.</div></main>;
  }

  async function submitInvitation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setSaving(true);
    setError("");
    setMessage("");
    setInviteUrl("");
    try {
      const invitation = await inviteOrganizer(String(new FormData(form).get("email") ?? "").trim());
      setInviteUrl(invitation.invitation_url ?? "");
      setMessage(`Приглашение отправлено: ${invitation.email}`);
      form.reset();
      await refresh();
    } catch (requestError) {
      setError(messageFor(requestError));
    } finally {
      setSaving(false);
    }
  }

  async function runAction(action: () => Promise<unknown>, success: string) {
    setError("");
    setMessage("");
    try {
      await action();
      setMessage(success);
      await refresh();
    } catch (requestError) {
      setError(messageFor(requestError));
    }
  }

  async function createResetLink(account: AdminUser) {
    setError("");
    setResetUrl("");
    try {
      const result = await createLocalPasswordResetLink(account.id);
      setResetUrl(result.reset_url);
      setMessage(`Ссылка сброса пароля создана для ${account.email}.`);
    } catch (requestError) {
      setError(messageFor(requestError));
    }
  }

  return (
    <main className="workspace-page">
      <div className="workspace-heading"><p className="eyebrow">АДМИНИСТРИРОВАНИЕ</p><h1>Пользователи<span className="accent-dot">.</span></h1><p>Приглашайте организаторов, назначайте мероприятия и управляйте доступом.</p></div>
      {loading && <div className="state-box" role="status"><span className="spinner" />Загружаем пользователей…</div>}
      <ErrorMessage>{error}</ErrorMessage>
      {message && <p className="success-message" role="status">{message}</p>}
      {inviteUrl && <div className="workspace-card credential-card"><strong>Локальная ссылка приглашения</strong><p>Ссылка показана только системному администратору для локального тестирования без SMTP.</p><code>{inviteUrl}</code></div>}
      {resetUrl && <div className="workspace-card credential-card"><strong>Локальная ссылка сброса</strong><p>Одноразовая ссылка действует 30 минут и показана только системному администратору.</p><code>{resetUrl}</code></div>}
      <form className="workspace-card workspace-form event-create-form" onSubmit={(event) => void submitInvitation(event)}>
        <h3>Пригласить организатора</h3>
        <label>Email<input name="email" type="email" required maxLength={254} autoComplete="email" /></label>
        <button className="primary-button" disabled={saving}>{saving ? "Отправляем…" : "Отправить приглашение"}</button>
      </form>
      <section className="workspace-section">
        <div className="workspace-section-heading"><div><p className="eyebrow">УЧЁТНЫЕ ЗАПИСИ</p><h2>Пользователи</h2></div></div>
        {users.map((account) => (
          <article className="workspace-card admin-user-card" key={account.id}>
            <div className="admin-user-heading"><div><strong>{account.display_name}</strong><span>{account.email ?? "Без email"}</span></div><span>{account.is_system_admin ? "Системный администратор" : account.is_active ? "Активен" : "Заблокирован"}</span></div>
            {!account.is_system_admin && <button className="quiet-button" onClick={() => void runAction(() => setUserBlocked(account.id, account.is_active), account.is_active ? "Пользователь заблокирован." : "Пользователь разблокирован.")}>{account.is_active ? "Заблокировать" : "Разблокировать"}</button>}
            {!account.is_system_admin && account.is_active && <button className="quiet-button" onClick={() => void createResetLink(account)}>Создать локальную ссылку сброса</button>}
            {account.is_organizer && (
              <div className="admin-event-assignments">
                <span>Мероприятия</span>
                {events.map((event) => {
                  const assigned = account.events.some((access) => access.event_id === event.id && access.role === "organizer");
                  return <label key={event.id}><input type="checkbox" checked={assigned} onChange={(change) => void runAction(() => setOrganizerEventAccess(account.id, event.id, change.target.checked), "Назначения обновлены.")} />{event.name} (ID {event.id})</label>;
                })}
              </div>
            )}
          </article>
        ))}
      </section>
      <section className="workspace-section">
        <div className="workspace-section-heading"><div><p className="eyebrow">ПРИГЛАШЕНИЯ</p><h2>История приглашений</h2></div></div>
        {invitations.map((invitation) => (
          <article className="workspace-card admin-user-card" key={invitation.id}>
            <div className="admin-user-heading"><div><strong>{invitation.email}</strong><span>Действует до {new Date(invitation.expires_at).toLocaleString()}</span></div><span>{invitation.status}</span></div>
            {invitation.status !== "used" && invitation.status !== "revoked" && <button className="quiet-button" onClick={() => void runAction(() => revokeInvitation(invitation.id), "Приглашение отозвано.")}>Отозвать</button>}
            {(invitation.status === "expired" || invitation.status === "revoked") && <button className="quiet-button" onClick={() => void runAction(() => resendInvitation(invitation.id), "Новое приглашение создано.")}>Отправить новое приглашение</button>}
          </article>
        ))}
        {!invitations.length && !loading && <p className="empty-workspace">Приглашений пока нет.</p>}
      </section>
    </main>
  );
}
