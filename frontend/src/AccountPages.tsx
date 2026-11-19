import { useState } from "react";
import type { FormEvent } from "react";
import {
  completePasswordReset,
  requestPasswordReset,
} from "./api";
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
        <p>Войдите как системный администратор.</p>
      </div>
      {loading
        ? <div className="state-box" role="status"><span className="spinner" />Проверяем сессию…</div>
        : user
          ? <div className="workspace-card">Вы вошли как {user.display_name}. <a href="/workspace">Перейти в кабинет</a></div>
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
      window.location.assign("/workspace");
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
        ? <div className="workspace-card">Если активная учётная запись администратора с таким email существует, инструкция по сбросу будет отправлена на него. Если письмо не пришло, обратитесь к системному администратору.</div>
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
