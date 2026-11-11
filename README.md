# Kerfuffle

Сервис для регистрации участников мероприятий, выставления баллов на площадках
и публикации рейтинга.

## Состав проекта

- `backend/` — FastAPI, SQLAlchemy, OIDC-аутентификация и API.
- `backend/alembic/` — версионируемые миграции PostgreSQL.
- `database/schema.sql` — SQL-схема проекта.
- `database/app_role.sql` — ограниченная роль PostgreSQL для runtime-приложения.
- `frontend/` — публичный рейтинг, кабинет и рабочие сценарии на React, Vite
  и TypeScript.
- `keycloak/` — локальная dev-конфигурация OIDC realm (Docker required).
- `PROJECT_STATUS.md` — сделанное, состояние окружения и оставшиеся задачи.

## Локальный запуск на Windows

1. Настройте PostgreSQL и приложение по инструкциям в
   [backend/README.md](./backend/README.md). Для приложения используйте роль
   `kerfuffle_app`, а миграции выполняйте от имени владельца базы.
2. Запустите API из `backend`:

   ```powershell
   python -m uvicorn app.main:app --reload
   ```

3. Установите Node.js LTS. В другом PowerShell из `frontend` выполните:

   ```powershell
   npm install
   npm run dev
   ```

4. Откройте публичную таблицу с номером мероприятия, например
   `http://localhost:5173/leaderboard?eventId=1`, или документацию API
   http://127.0.0.1:8000/docs.

Для входа в защищённый рабочий кабинет необходимо настроить OIDC-провайдера.
Не публикуйте `.env` и не сохраняйте пароль PostgreSQL в Git.

Для локальной разработки с Keycloak см. раздел Keycloak в
[frontend/README.md](./frontend/README.md). Конфигурация контейнера находится
в `keycloak/`; пароль администратора задаётся только в локальном
`keycloak/.env`.
