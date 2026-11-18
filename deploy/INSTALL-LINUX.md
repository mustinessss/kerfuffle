# Развёртывание Kerfuffle на Linux VPS

Это production-инструкция для публичного сервера. Она рассчитана на Ubuntu
22.04/24.04 LTS и актуальную ветку `main`. Для другого Linux-дистрибутива
команды установки Docker и настройки firewall могут отличаться.

> **Важно:** не используйте для публичного сервера локальный
> `deploy/compose.yaml`. Он предназначен для Windows/local demo и не
> настраивает production HTTPS. Для VPS используется только
> `deploy/compose.production.yaml`.

## 1. Что понадобится

- Linux VPS с публичным IPv4. Минимум 2 GB RAM; для более комфортной работы
  рекомендуется начать с 2 vCPU, 4 GB RAM и 30–40 GB SSD.
- Домен или поддомен, например `kerfuffle.example.com`.
- Возможность изменить DNS-записи домена.
- SSH-доступ к VPS с пользователем, имеющим `sudo`.
- Открытые входящие TCP-порты 80 и 443. UDP 443 можно открыть для HTTP/3.

Production-конфигурация рассчитана на доменное имя и автоматический HTTPS
через Caddy/Let's Encrypt. **Запуск только по голому публичному IP штатно не
настроен**: сначала направьте домен на IP сервера.

## 2. Подготовьте DNS

В панели управления DNS создайте запись:

| Тип | Имя | Значение |
| --- | --- | --- |
| A | `kerfuffle` (или нужный поддомен) | публичный IPv4 вашего VPS |

Если используете корневой домен, укажите соответствующее имя записи у
регистратора. Не создавайте AAAA-запись, пока у сервера нет рабочего публичного
IPv6 и корректного IPv6-маршрута.

Подключитесь к серверу:

```bash
ssh USER@SERVER_IP
```

Проверьте, что DNS уже указывает на нужный адрес (подставьте свой домен):

```bash
getent ahostsv4 kerfuffle.example.com
```

В выводе должен присутствовать IPv4 вашего VPS. Если DNS ещё не обновился,
дождитесь распространения записи до продолжения.

## 3. Установите Docker Engine и Compose

Обновите систему:

```bash
sudo apt update
sudo apt upgrade -y
```

Установите Docker Engine и Compose plugin способом, рекомендованным
документацией Docker для вашей версии Ubuntu:
[официальная инструкция Docker Engine](https://docs.docker.com/engine/install/ubuntu/).

После установки включите Docker и проверьте Compose:

```bash
sudo systemctl enable --now docker
sudo docker version
sudo docker compose version
```

Дальше в инструкции команды приведены с `sudo docker compose`, поэтому
добавлять пользователя в группу `docker` необязательно. Членство в этой
группе фактически предоставляет права уровня root.

## 4. Настройте firewall

Если используете UFW, сначала убедитесь, что SSH разрешён, чтобы не потерять
доступ к серверу:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 443/udp
sudo ufw status
```

Если UFW ещё не включён и вы проверили правило SSH:

```bash
sudo ufw enable
sudo ufw status verbose
```

Также проверьте firewall/security group в панели VPS-провайдера. Разрешите
входящие TCP 80 и 443 (и UDP 443, если нужен HTTP/3). **Не открывайте наружу**
порты PostgreSQL 5432 и backend 8000: они доступны только внутри Docker-сети.

## 5. Скачайте проект

Установите Git, создайте каталог и клонируйте репозиторий:

```bash
sudo apt install -y git
sudo mkdir -p /opt/kerfuffle
sudo chown "$USER":"$USER" /opt/kerfuffle
git clone https://github.com/mustinessss/kerfuffle.git /opt/kerfuffle
cd /opt/kerfuffle
```

Если каталог уже содержит рабочую копию проекта, не клонируйте поверх неё:
перейдите в существующий каталог и проверьте текущую ветку и локальные изменения.

## 6. Создайте production environment

Скопируйте шаблон и откройте его редактором:

```bash
cp deploy/.env.production.example deploy/.env.production
nano deploy/.env.production
chmod 0600 deploy/.env.production
```

Заполните значения:

- `APP_DOMAIN` — домен без `https://`, например
  `kerfuffle.example.com`.
- `APP_PUBLIC_URL` — полный адрес, например
  `https://kerfuffle.example.com`.
- `APP_ALLOWED_ORIGINS` — тот же origin:
  `https://kerfuffle.example.com`.
- `POSTGRES_PASSWORD` — отдельный случайный пароль суперпользователя БД.
- `APP_DB_PASSWORD` — другой случайный пароль runtime-пользователя приложения.
- `ACCESS_CODE_HASH_SECRET` — отдельный случайный секрет не короче 32 символов.

Сгенерируйте три разных значения:

```bash
openssl rand -hex 32
openssl rand -hex 32
openssl rand -base64 48
```

Скопируйте первые два значения в пароли БД, третье — в
`ACCESS_CODE_HASH_SECRET`. Не используйте один секрет в нескольких полях.
Hex-значения удобны тем, что не содержат символов, требующих дополнительного
экранирования в Compose env-файле.

Не оставляйте примеры `replace-with-...` из шаблона. Не коммитьте и не
отправляйте никому `deploy/.env.production`, пароли или секреты.

### Настройка отправки приглашений

Для приглашений организаторов и ссылок восстановления пароля выберите один
вариант:

1. **SMTP (предпочтительно):** заполните `SMTP_HOST`, `SMTP_PORT`,
   `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` и `SMTP_USE_TLS`.
   Используйте пароль приложения/SMTP, если почтовый провайдер его требует.
2. **Ручная передача:** если SMTP пока нет, установите
   `MANUAL_AUTH_LINKS_ENABLED=true`. Системный администратор сможет получить
   одноразовую ссылку и передать её организатору по доверенному каналу.
   Ссылка приглашения действует 24 часа, ссылка сброса пароля — 30 минут.

Не включайте ручную передачу без понимания, как безопасно передать ссылку
конкретному организатору. Ссылки дают возможность активировать аккаунт или
сбросить пароль.

Сохраните файл и проверьте права:

```bash
chmod 0600 deploy/.env.production
```

## 7. Создайте TLS-сертификаты для PostgreSQL

Production PostgreSQL принимает только TLS-соединения внутри Docker-сети.
Сгенерируйте внутренний CA и серверный сертификат:

```bash
sudo bash deploy/postgres-tls/generate-postgres-tls.sh
```

Скрипту нужны OpenSSL и Docker; он определяет UID/GID пользователя postgres
из используемого Compose-образа и выставляет права на ключ сервера.

Файл `deploy/postgres-tls/ca.key` — приватный ключ CA. Он не нужен работающему
приложению. Храните его отдельно в защищённом месте или удалите после
генерации, если не планируете перевыпускать сертификаты с тем же CA:

```bash
sudo rm -f deploy/postgres-tls/ca.key
```

Не удаляйте `ca.crt`, `server.crt`, `server.key` и `pg_hba.conf`: они
нужны production Compose. Не загружайте приватные ключи в Git.

## 8. Проверьте конфигурацию и запустите приложение

Все команды выполняйте из корня репозитория `/opt/kerfuffle`.

Сначала проверьте итоговую конфигурацию Compose:

```bash
sudo docker compose --env-file deploy/.env.production \
  -f deploy/compose.production.yaml config
```

Если Compose сообщает об отсутствующих переменных или ошибках конфигурации,
исправьте их до запуска. Затем соберите образы и запустите сервисы:

```bash
sudo docker compose --env-file deploy/.env.production \
  -f deploy/compose.production.yaml up --build -d
```

Посмотрите состояние контейнеров:

```bash
sudo docker compose --env-file deploy/.env.production \
  -f deploy/compose.production.yaml ps
```

Первый запуск может занять несколько минут: Docker скачает базовые образы,
соберёт frontend/backend, запустит PostgreSQL и применит миграции Alembic.
Backend запускается только после успешного завершения миграций.

Проверьте логи миграции и backend:

```bash
sudo docker compose --env-file deploy/.env.production \
  -f deploy/compose.production.yaml logs migrate backend
```

Проверьте текущую миграцию:

```bash
sudo docker compose --env-file deploy/.env.production \
  -f deploy/compose.production.yaml exec backend \
  python -m alembic current
```

В текущей версии ожидаемая голова миграций — `0008_route_sheets`. Если миграция
завершилась ошибкой, не продолжайте настройку и не пытайтесь исправить ситуацию
через `alembic downgrade`: сначала разберите ошибку и сохраните данные.

## 9. Проверьте HTTPS и создайте первого администратора

Caddy автоматически запросит и будет продлевать сертификат Let's Encrypt.
Для выпуска сертификата домен должен указывать на VPS, а TCP 80 и 443 должны
быть доступны из интернета.

Проверьте сайт и API:

```bash
curl -I https://kerfuffle.example.com
curl -fsS https://kerfuffle.example.com/api/v1/health
```

Замените домен на свой. Health endpoint должен ответить успешно.

Создайте первого системного администратора:

```bash
sudo docker compose --env-file deploy/.env.production \
  -f deploy/compose.production.yaml run --rm backend \
  python -m app.cli create-admin
```

CLI запросит email и пароль. Пароль должен быть не короче 12 символов и
содержать строчные и заглавные латинские буквы и цифру. После создания
откройте:

```
https://kerfuffle.example.com/login
```

Войдите под созданной учётной записью. Самостоятельной публичной регистрации
администраторов нет: системный администратор приглашает организаторов из
раздела управления пользователями, назначает им мероприятия. Для отправки
приглашений используйте настроенный SMTP или включённый ручной режим.

## 10. Проведите проверку перед мероприятием

Не ограничивайтесь тем, что главная страница открывается. На тестовом
мероприятии проверьте полный сценарий:

1. Создайте мероприятие и настройте площадки/маршрутные листы.
2. Создайте и проверьте коды регистрации и внесения баллов.
3. Пригласите организатора и убедитесь, что он видит только назначенное ему
   мероприятие.
4. Зарегистрируйте несколько тестовых участников; проверьте выдачу
   шестизначных кодов.
5. Проверьте начисление баллов на разрешённой площадке и запрет повторного
   начисления.
6. Проверьте запрет начисления на площадке, которой нет в маршрутном листе.
7. Проверьте публичную таблицу участников и прогресс.
8. Проверьте вход с телефонов через мобильную сеть, а не только из локальной
   сети VPS.

После теста удаляйте тестовые данные только предусмотренными средствами
приложения и убедитесь, что не затрагиваете реальные данные.

## 11. Резервное копирование

Создайте резервную копию PostgreSQL:

```bash
sudo bash deploy/backup-postgres.sh
```

Архив появится в `deploy/backups/`. Скрипт проверяет, что архив не пустой и
что gzip-файл читается. Скопируйте резервные копии за пределы VPS в
зашифрованное хранилище. Копия только на том же сервере не защищает от потери
сервера или диска.

Проверьте восстановление в отдельную временную базу:

```bash
sudo bash deploy/test-restore.sh \
  deploy/backups/kerfuffle-YYYYMMDDTHHMMSSZ.sql.gz
```

Подставьте фактическое имя архива. Скрипт восстанавливает данные во временную
БД `kerfuffle_restore_test`, а не поверх рабочей базы.

Настройте регулярный запуск резервного копирования (например, два раза в
день). Если используете cron от root, укажите абсолютные пути:

```cron
0 2,14 * * * cd /opt/kerfuffle && /bin/bash /opt/kerfuffle/deploy/backup-postgres.sh >> /var/log/kerfuffle-backup.log 2>&1
```

Периодически проверяйте журналы cron и тестируйте восстановление.

## 12. Обновление приложения

Перед каждым обновлением сделайте и вынесите за пределы VPS резервную копию.
Затем из корня репозитория:

```bash
sudo bash deploy/backup-postgres.sh
git status
git pull --ff-only
sudo docker compose --env-file deploy/.env.production \
  -f deploy/compose.production.yaml build
sudo docker compose --env-file deploy/.env.production \
  -f deploy/compose.production.yaml up -d
sudo docker compose --env-file deploy/.env.production \
  -f deploy/compose.production.yaml ps
```

Проверьте логи миграций и endpoint `/api/v1/health` после обновления. Не
применяйте обновление, если в рабочей копии есть незакоммиченные изменения,
которые вы не понимаете. Не запускайте `alembic downgrade`.

## 13. Остановка и диагностика

Остановить сервисы, сохранив базу данных:

```bash
sudo docker compose --env-file deploy/.env.production \
  -f deploy/compose.production.yaml down
```

Запустить снова:

```bash
sudo docker compose --env-file deploy/.env.production \
  -f deploy/compose.production.yaml up -d
```

**Не используйте** `docker compose down -v` и не удаляйте volume
`postgres-data`: это приведёт к потере данных PostgreSQL.

Полезные команды:

```bash
sudo docker compose --env-file deploy/.env.production \
  -f deploy/compose.production.yaml ps

sudo docker compose --env-file deploy/.env.production \
  -f deploy/compose.production.yaml logs --tail=200 caddy backend db migrate

sudo docker compose --env-file deploy/.env.production \
  -f deploy/compose.production.yaml exec db \
  pg_isready -U postgres -d kerfuffle

curl -fsS https://kerfuffle.example.com/api/v1/health
```

Частые причины проблем:

- **Caddy не получает сертификат:** проверьте DNS A-запись, доступность TCP
  80/443 и отсутствие другого сервиса, занимающего эти порты.
- **Compose сообщает о пустых переменных:** проверьте
  `deploy/.env.production`, имена переменных и отсутствие незаменённых
  шаблонных значений.
- **Backend не стартует:** проверьте `migrate` и `backend` logs; не
  обходите ошибку миграции.
- **PostgreSQL не стартует:** проверьте TLS-файлы, права на `server.key` и
  логи `db`.
- **Приглашения не приходят:** проверьте SMTP-параметры, пароль SMTP и логи
  backend. Временный альтернативный вариант — ручная передача ссылок через
  доверенный канал.

Для внешнего мониторинга настройте HTTPS-проверку
`/api/v1/health`. Не публикуйте содержимое `.env.production`, пароли,
коды доступа, приватные ключи и дампы базы в тикетах или логах.

## Схема production-развёртывания

Из интернета доступны только Caddy на TCP 80/443 (UDP 443 — опционально).
Caddy маршрутизирует запросы к frontend и backend внутри приватной Docker-сети.
PostgreSQL и backend не имеют опубликованных host-портов.

```text
Пользователь / браузер
        |
        | HTTPS :443 (HTTP :80 -> HTTPS)
        v
      Caddy
       /  \
      /    \
 frontend  backend :8000
               |
               | TLS внутри Docker-сети
               v
         PostgreSQL :5432
```
