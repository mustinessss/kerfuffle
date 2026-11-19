# Развёртывание Kerfuffle на Linux VPS

Это production-инструкция для Linux VPS с отдельными публичным и
административным входами. Она рассчитана на Ubuntu
22.04/24.04 LTS и актуальную ветку `main`. Для другого Linux-дистрибутива
команды установки Docker и настройки firewall могут отличаться.

> **Важно:** не используйте для публичного сервера локальный
> `deploy/compose.yaml`. Он предназначен для Windows/local demo и не
> настраивает production HTTPS. Для VPS используется только
> `deploy/compose.production.yaml`.

## 1. Что понадобится

- Linux VPS с публичным IPv4. Минимум 2 GB RAM; для более комфортной работы
  рекомендуется начать с 2 vCPU, 4 GB RAM и 30–40 GB SSD.
- Публичный домен, например `kerfuffle.example.com`.
- Private DNS-имя для администратора, например `kerfuffle-admin.internal`,
  разрешаемое только из LAN/VPN.
- Возможность изменить DNS-записи домена.
- SSH-доступ к VPS с пользователем, имеющим `sudo`.
- Открытые входящие TCP-порты 80 и 443. UDP 443 можно открыть для HTTP/3.
- LAN/VPN-интерфейс и разрешённый CIDR для административного TCP-порта 8443.

Публичный домен использует HTTPS через Caddy/Let's Encrypt. Административный
интерфейс с рейтингами доступен только из доверенной LAN/VPN-сети через
отдельный Caddy на порту 8443 и внутренний TLS-сертификат. **Запуск только по
голому публичному IP штатно не настроен**: сначала направьте публичный домен
на IP сервера.

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

Настройте private DNS-запись для `ADMIN_DOMAIN`, указывающую на private/VPN
адрес сервера. Это имя не должно разрешаться на публичный адрес, если доступ
администраторов предназначен только для LAN/VPN.

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
sudo ufw allow from 10.66.0.0/24 to any port 8443 proto tcp
sudo ufw status
```

Если UFW ещё не включён и вы проверили правило SSH:

```bash
sudo ufw enable
sudo ufw status verbose
```

Также проверьте firewall/security group в панели VPS-провайдера. Разрешите
входящие TCP 80 и 443 (и UDP 443, если нужен HTTP/3); 8443 разрешайте только
для фактического CIDR LAN/VPN. Замените `10.66.0.0/24` на свою VPN-сеть.
**Не открывайте наружу** порты PostgreSQL 5432 и backend 8000, и не
публикуйте 8443 для всего интернета.

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
- `ADMIN_DOMAIN` — private DNS-имя, например `kerfuffle-admin.internal`.
- `ADMIN_BIND_IP` — IP LAN/VPN-интерфейса сервера. Значение `127.0.0.1`
  оставляет админку доступной только локально; для прямого доступа по VPN
  задайте адрес VPN-интерфейса.
- `ADMIN_ALLOWED_CIDRS` — один или несколько CIDR LAN/VPN, разрешённых для
  административного входа, например `10.66.0.0/24`.
- `APP_PUBLIC_URL` — административный HTTPS origin:
  `https://kerfuffle-admin.internal:8443`. Ссылка сброса пароля администратора
  будет вести на этот private адрес.
- `APP_ALLOWED_ORIGINS` — оба origin, через запятую:
  `https://kerfuffle.example.com,https://kerfuffle-admin.internal:8443`.
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

### Настройка восстановления пароля администратора

Сотрудники получают доступ к площадкам и регистрации по кодам, которые
администратор выпускает в рабочем пространстве. Для восстановления пароля
администратора заполните `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`,
`SMTP_PASSWORD`, `SMTP_FROM` и `SMTP_USE_TLS`. Ссылка одноразовая и действует
30 минут.

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

## 8. Получите готовые Linux-образы и запустите приложение

Образы backend, публичного frontend и административного frontend собираются
GitHub Actions на Linux runner и публикуются в GitHub Container Registry
(GHCR). VPS не собирает исходники: он только скачивает готовые `linux/amd64`
образы. Публикация запускается
автоматически после push изменений backend/frontend в `main`, а также может
быть запущена вручную во вкладке **Actions → Publish Linux images → Run
workflow**.

Перед первым запуском откройте в репозитории GitHub раздел **Actions** и
убедитесь, что workflow **Publish Linux images** завершился успешно. Затем
откройте профиль владельца GitHub → **Packages** и проверьте пакеты
`kerfuffle-backend`, `kerfuffle-frontend-public` и
`kerfuffle-frontend-admin`. Для простого развёртывания на VPS рекомендуется
установить пакетам видимость **Public** (Package settings → Change visibility).
Публичные образы можно скачивать без токена. Если
оставить пакеты Private, перед `docker compose pull` нужно выполнить вход в
GHCR с токеном GitHub, имеющим только `read:packages`:

```bash
read -s GHCR_TOKEN
printf '%s' "$GHCR_TOKEN" | sudo docker login ghcr.io -u GITHUB_USERNAME --password-stdin
unset GHCR_TOKEN
```

Замените `GITHUB_USERNAME` на имя пользователя GitHub. Не вставляйте токен
непосредственно в команду и не сохраняйте его в `.env.production`.

Все следующие команды выполняйте из корня репозитория `/opt/kerfuffle`.
Сначала проверьте итоговую конфигурацию Compose:

```bash
sudo docker compose --env-file deploy/.env.production \
  -f deploy/compose.production.yaml config
```

Затем скачайте опубликованные образы и запустите сервисы:

```bash
sudo docker compose --env-file deploy/.env.production \
  -f deploy/compose.production.yaml pull
sudo docker compose --env-file deploy/.env.production \
  -f deploy/compose.production.yaml up -d
```

В этой конфигурации `migrate` и `backend` используют один backend image.
Перед запуском backend Compose дождётся успешного выполнения Alembic migration.
Первый запуск скачает образы и базовые сервисы, поднимет PostgreSQL и
применит миграции. Сборки Docker на VPS нет.

Посмотрите состояние контейнеров:

```bash
sudo docker compose --env-file deploy/.env.production \
  -f deploy/compose.production.yaml ps
```

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

В текущей версии ожидаемая голова миграций — `0013_station_rating_modes`.
Если миграция
завершилась ошибкой, не продолжайте настройку и не пытайтесь исправить ситуацию
через `alembic downgrade`: сначала разберите ошибку и сохраните данные.

## 9. Проверьте публичный и административный входы

Caddy автоматически запросит и будет продлевать публичный сертификат
Let's Encrypt. Для этого публичный домен должен указывать на VPS, а TCP 80 и
443 должны быть доступны из интернета.

Проверьте публичные страницы:

```bash
curl -I https://kerfuffle.example.com/register
curl -I https://kerfuffle.example.com/score
```

Публичный адрес предоставляет только регистрацию и начисление. Проверяйте
health backend из контейнера:

```bash
sudo docker compose --env-file deploy/.env.production \
  -f deploy/compose.production.yaml exec backend \
  python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health').status)"
```

Для административной зоны настройте private DNS `ADMIN_DOMAIN`, привяжите
порт 8443 к IP LAN/VPN-интерфейса через `ADMIN_BIND_IP` и убедитесь, что
firewall разрешает 8443 только доверенным CIDR. Установите внутренний
корневой сертификат Caddy на устройства администраторов; после запуска его
можно получить командой:

```bash
sudo docker compose --env-file deploy/.env.production \
  -f deploy/compose.production.yaml cp \
  admin-caddy:/data/caddy/pki/authorities/local/root.crt \
  ./kerfuffle-admin-root.crt
```

Безопасно доставьте этот публичный CA-сертификат администраторам и добавьте
его в системное хранилище доверенных CA. Не копируйте и не распространяйте
приватный ключ CA из Docker volume. Затем откройте
`https://ADMIN_DOMAIN:8443/login` из LAN/VPN и проверьте, что извне этого
диапазона порт недоступен.

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
https://kerfuffle-admin.internal:8443/login
```

Замените имя на значение `ADMIN_DOMAIN`. Войдите под созданной учётной записью.
Держателям площадок и регистраторам
администратор выдаёт коды доступа в рабочем пространстве; отдельные аккаунты
сотрудников не создаются.

## 10. Проведите проверку перед мероприятием

Не ограничивайтесь тем, что главная страница открывается. На тестовом
мероприятии проверьте полный сценарий:

1. Создайте мероприятие и настройте площадки/маршрутные листы.
2. Пригласите держателя площадки, назначьте ему конкретную площадку и создайте
   для неё код доступа.
3. Проверьте, что держатель видит и обслуживает только назначенную площадку.
4. Зарегистрируйте тестовых участников с ручными уникальными шестизначными
   номерами и назначьте их на маршрутные листы.
5. Проверьте начисление на площадке из маршрута и вне маршрута, сохранение
   исходного маршрутного листа и отказ повторного начисления.
6. Проверьте исправление/аннулирование начисления администратором и журнал
   изменений с причиной.
7. Проверьте общий и групповой рейтинги, включая нулевые результаты и ничьи.
8. Убедитесь, что публичный адрес не показывает вход, рейтинги и
   административные API; проверьте их доступность только из LAN/VPN.

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

После push в `main` дождитесь успешного workflow **Publish Linux images** в
GitHub Actions. Перед обновлением сделайте и вынесите за пределы VPS резервную
копию. Затем из корня репозитория:

```bash
sudo bash deploy/backup-postgres.sh
git status
git pull --ff-only
sudo docker compose --env-file deploy/.env.production \
  -f deploy/compose.production.yaml pull
sudo docker compose --env-file deploy/.env.production \
  -f deploy/compose.production.yaml up -d
sudo docker compose --env-file deploy/.env.production \
  -f deploy/compose.production.yaml ps
```

`git pull` обновляет compose-файлы и конфигурацию на VPS, `compose pull`
скачивает новые Linux-образы из GHCR, а `up -d` применяет обновление. База
данных и её Docker volume при этом сохраняются.

Проверьте логи миграций, health backend из контейнера и доступность
административного ingress из LAN/VPN после обновления. Не применяйте
обновление, если в рабочей копии есть незакоммиченные изменения, которые вы не
понимаете. Не запускайте `alembic downgrade`.

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
  -f deploy/compose.production.yaml logs --tail=200 caddy admin-caddy backend db migrate

sudo docker compose --env-file deploy/.env.production \
  -f deploy/compose.production.yaml exec db \
  pg_isready -U postgres -d kerfuffle

sudo docker compose --env-file deploy/.env.production \
  -f deploy/compose.production.yaml exec backend \
  python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health').status)"
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
- **Письмо для сброса пароля администратора не приходит:** проверьте
  SMTP-параметры, пароль SMTP и логи backend. Сотрудники используют коды
  доступа и не получают приглашения по email.

Публичный `/api/v1/health` намеренно недоступен. Проверяйте здоровье backend
изнутри Compose или через закрытый административный ingress. Не публикуйте
содержимое `.env.production`, пароли, коды доступа, приватные ключи и дампы
базы в тикетах или логах.

## Схема production-развёртывания

Из интернета доступны public Caddy на TCP 80/443 (UDP 443 — опционально) и
только публичные формы регистрации/начисления. Отдельный admin Caddy на TCP
8443 привязан к LAN/VPN адресу и фильтрует клиентов по CIDR. Backend разрешает
public proxy только точный allowlist API; админские API доступны только через
private proxy. PostgreSQL и backend не имеют опубликованных host-портов.

```text
Публичный браузер -- HTTPS :443 --> public Caddy
                                      |-- public frontend (register / score)
                                      `-- allowlisted public API

Администратор в LAN/VPN -- HTTPS :8443 --> admin Caddy (internal TLS, CIDR)
                                             |-- admin frontend (ratings / management)
                                             `-- private API
                                                    |
                                                    v
                                        backend :8000 -- TLS --> PostgreSQL :5432
```
