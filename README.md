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
- `deploy/` — локальная упаковка Docker Compose и инструкции по запуску.
- `PROJECT_STATUS.md` — сделанное, состояние окружения и оставшиеся задачи.

## Запуск локального пакета на Windows

Установите Docker Desktop с Linux container engine. Чтобы подготовить архив
для переноса, из корня проекта выполните:

```powershell
.\deploy\package.ps1
```

Скрипт создаст `mustiness-kerfuffle-package.zip` без локальных `.env`,
виртуальных окружений и зависимостей Node. Распакуйте архив на целевой машине
и запустите:

```powershell
.\deploy\start.ps1
```

При первом запуске будут созданы локальные случайные секреты в
`deploy/.env`, собраны контейнеры, применены миграции и запущены frontend,
backend, PostgreSQL и Keycloak. Приложение откроется по адресу
http://localhost:5173. Подробные инструкции по созданию первого
суперпользователя и настройке создания организаторов находятся в
[deploy/README.md](./deploy/README.md).

Это пакет для локальной демонстрации и приёмочной проверки, а не для
публикации в интернете. Он использует HTTP, dev-режим Keycloak и локальную
PostgreSQL. Не передавайте `deploy/.env` и не включайте его в архив. До
production-запуска выполните требования раздела Production minimum ниже и в
[backend/README.md](./backend/README.md).

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

## Production minimum

Проект пока не готов к публичному production-развёртыванию. Перед ним нужны
домен и HTTPS reverse proxy, production Keycloak с MFA и защитой от подбора,
PostgreSQL с TLS и отдельными ролями, секреты в secret manager, проверенные
резервные копии, rate limiting, мониторинг и приёмочные тесты на staging.
Подробный checklist находится в [backend/README.md](./backend/README.md).
