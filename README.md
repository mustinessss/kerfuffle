# Kerfuffle

Сервис для регистрации участников мероприятий, выставления баллов на площадках
и публикации рейтинга.

## Состав проекта

- `backend/` — FastAPI, PostgreSQL, Alembic и встроенная авторизация.
- `frontend/` — React/Vite/TypeScript: публичный рейтинг и рабочие кабинеты.
- `database/` — SQL-схема и ограниченная runtime-роль PostgreSQL.
- `deploy/` — локальный Docker Compose-пакет для переноса на Windows-машину.
- `PROJECT_STATUS.md` — актуальное состояние и оставшиеся задачи.

## Локальный запуск приложения

Для backend нужны Python 3.12+, PostgreSQL и PowerShell; для frontend — Node.js
LTS. Инструкции по созданию базы, установке зависимостей, миграциям и первому
суперпользователю находятся в [backend/README.md](./backend/README.md).

После настройки базы запустите backend на `127.0.0.1:8001`, затем frontend
командами из соответствующих README. Первый суперпользователь создаётся
командой `python -m app.cli create-admin`; организаторов он приглашает по
email из `/admin/users`. Короткие коды регистратора и площадки остаются
отдельным способом доступа для сотрудников мероприятий.

## Перенос на другую машину

Установите Docker Desktop с Linux container engine. Из корня проекта соберите
архив командой:

```powershell
.\deploy\package.ps1
```

Скрипт создаёт `mustiness-kerfuffle-package.zip` без локальных `.env`,
виртуальных окружений и зависимостей Node. Распакуйте архив на целевой машине
и запустите `.\deploy\start.ps1`. При первом запуске будут созданы локальные
секреты, применены миграции и запущены frontend, backend и PostgreSQL.
Подробности и создание первого суперпользователя описаны в
[deploy/README.md](./deploy/README.md).

Этот пакет предназначен для локальной демонстрации и приёмочной проверки, а
не для публикации в интернете. Не передавайте `deploy/.env` и не включайте его
в архив.

## Production minimum

Перед публичным запуском нужны HTTPS reverse proxy, безопасное хранение
секретов, SMTP, PostgreSQL с TLS и отдельной runtime-ролью, резервные копии с
проверенным восстановлением, мониторинг, edge rate limiting и acceptance-тесты
на staging. Подробный checklist находится в
[backend/README.md](./backend/README.md).
