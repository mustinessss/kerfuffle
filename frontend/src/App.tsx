import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import './App.css'

type LeaderboardParticipant = {
  registration_number: string
  place: number
  total_points: number
  stations_completed: number
  stations_total: number
}

type LeaderboardResponse = {
  event: {
    id: number
    name: string
    event_date: string
  }
  stations_total: number
  participants: LeaderboardParticipant[]
}

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'

function formatEventDate(value: string) {
  return new Intl.DateTimeFormat('ru-RU', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
  }).format(new Date(`${value}T00:00:00`))
}

function App() {
  const initialEventId = new URLSearchParams(window.location.search).get('eventId') ?? ''
  const [eventId, setEventId] = useState(initialEventId)
  const [eventIdInput, setEventIdInput] = useState(initialEventId)
  const [data, setData] = useState<LeaderboardResponse | null>(null)
  const [filter, setFilter] = useState('')
  const [error, setError] = useState('')
  const [loadedEventId, setLoadedEventId] = useState('')
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [retryKey, setRetryKey] = useState(0)
  const loading = Boolean(eventId && loadedEventId !== eventId)
  const currentData =
    data && Number(eventId) === data.event.id ? data : null

  useEffect(() => {
    if (!eventId) return

    let active = true
    let eventNotFound = false
    const controller = new AbortController()

    const loadLeaderboard = async () => {
      try {
        const response = await fetch(
          `${API_BASE}/public/events/${encodeURIComponent(eventId)}/leaderboard`,
          { signal: controller.signal },
        )
        if (!response.ok) {
          if (response.status === 404) {
            eventNotFound = true
            throw new Error('Мероприятие не найдено. Проверьте номер и попробуйте ещё раз.')
          }
          throw new Error(`Не удалось загрузить таблицу (ошибка ${response.status}).`)
        }

        const result = (await response.json()) as LeaderboardResponse
        if (active) {
          setData(result)
          setError('')
          setLastUpdated(new Date())
          setLoadedEventId(eventId)
          eventNotFound = false
        }
      } catch (caught) {
        if (active && !(caught instanceof DOMException && caught.name === 'AbortError')) {
          setError(
            caught instanceof TypeError
              ? 'Сервер сейчас недоступен. Проверьте, запущен ли backend, и попробуйте ещё раз.'
              : caught instanceof Error
              ? caught.message
              : 'Не удалось связаться с сервером. Попробуйте ещё раз.',
          )
          setLoadedEventId(eventId)
        }
      }
    }

    void loadLeaderboard()
    const intervalId = window.setInterval(() => {
      if (!eventNotFound) void loadLeaderboard()
    }, 5000)

    return () => {
      active = false
      controller.abort()
      window.clearInterval(intervalId)
    }
  }, [eventId, retryKey])

  const visibleParticipants = useMemo(() => {
    const normalizedFilter = filter.trim().toLowerCase()
    if (!normalizedFilter) return currentData?.participants ?? []
    return (currentData?.participants ?? []).filter((participant) =>
      participant.registration_number.toLowerCase().includes(normalizedFilter),
    )
  }, [currentData, filter])

  const handleOpenEvent = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const normalizedId = eventIdInput.trim()
    if (!/^\d+$/.test(normalizedId) || Number(normalizedId) < 1) {
      setError('Введите положительный номер мероприятия.')
      return
    }
    window.history.replaceState(null, '', `?eventId=${encodeURIComponent(normalizedId)}`)
    setFilter('')
    setError('')
    setLoadedEventId('')
    setEventId(normalizedId)
  }

  const podium = currentData?.participants.slice(0, 3) ?? []

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="Kerfuffle — на главную">
          <span className="brand-mark" aria-hidden="true">k</span>
          <span>kerfuffle</span>
        </a>
        <div className="topbar-meta">
          <span className="live-dot" aria-hidden="true" />
          <span>Результаты обновляются автоматически</span>
        </div>
      </header>

      <section className="hero">
        <div className="hero-copy">
          <span className="eyebrow"><span className="eyebrow-line" />ТАБЛИЦА РЕЗУЛЬТАТОВ</span>
          <h1>Каждый балл<br /><span>имеет значение.</span></h1>
          <p>Следите за результатами и прогрессом участников в реальном времени.</p>
        </div>
        <div className="event-picker">
          <div className="picker-label"><span className="picker-icon">↗</span>ОТКРЫТЬ МЕРОПРИЯТИЕ</div>
          <form onSubmit={handleOpenEvent}>
            <label className="sr-only" htmlFor="event-id">Номер мероприятия</label>
            <input
              id="event-id"
              inputMode="numeric"
              pattern="[0-9]*"
              placeholder="Например, 12"
              value={eventIdInput}
              onChange={(event) => setEventIdInput(event.target.value)}
            />
            <button type="submit">Показать <span aria-hidden="true">→</span></button>
          </form>
          <span className="picker-hint">Номер мероприятия находится в ссылке организатора</span>
        </div>
      </section>

      {eventId && currentData && (
        <>
          <section className="event-heading">
            <div>
              <span className="section-kicker">МЕРОПРИЯТИЕ №{currentData.event.id}</span>
              <h2>{currentData.event.name}</h2>
              <p>{formatEventDate(currentData.event.event_date)}</p>
            </div>
            <div className="refresh-status">
              <span className="refresh-icon" aria-hidden="true">↻</span>
              <span>
                <strong>Обновление каждые 5 сек.</strong>
                <small>{lastUpdated ? `Последнее: ${lastUpdated.toLocaleTimeString('ru-RU')}` : 'Загружаем...'}</small>
              </span>
            </div>
          </section>

          <section className="summary-grid" aria-label="Сводка результатов">
            <article className="summary-card">
              <span className="summary-icon people-icon" aria-hidden="true">◎</span>
              <span className="summary-label">УЧАСТНИКИ</span>
              <strong>{currentData.participants.length}</strong>
              <span className="summary-note">в таблице результатов</span>
            </article>
            <article className="summary-card">
              <span className="summary-icon station-icon" aria-hidden="true">⌁</span>
              <span className="summary-label">ПЛОЩАДКИ</span>
              <strong>{currentData.stations_total}</strong>
              <span className="summary-note">в программе события</span>
            </article>
            <article className="summary-card highlight-card">
              <span className="summary-icon winner-icon" aria-hidden="true">✳</span>
              <span className="summary-label">ЛИДЕР</span>
              <strong>{podium[0]?.registration_number ?? '—'}</strong>
              <span className="summary-note">
                {podium[0] ? `${podium[0].total_points} баллов` : 'пока без оценок'}
              </span>
            </article>
          </section>

          {podium.length > 0 && (
            <section className="podium-section" aria-label="Лидеры мероприятия">
              <div className="section-title-row">
                <div>
                  <span className="section-kicker">ВПЕРЕДИ ВСЕХ</span>
                  <h2>Лидеры</h2>
                </div>
                <span className="podium-caption">По сумме баллов</span>
              </div>
              <div className="podium-grid">
                {[1, 0, 2].map((index) => {
                  const participant = podium[index]
                  if (!participant) return <div className="podium-empty" key={index} />
                  return (
                    <article
                      className={`podium-card podium-${participant.place <= 3 ? participant.place : 'other'}`}
                      key={participant.registration_number}
                    >
                      <span className="podium-medal" aria-hidden="true">
                        {participant.place === 1 ? '✳' : participant.place === 2 ? '◆' : '●'}
                      </span>
                      <span className="podium-rank">МЕСТО {participant.place}</span>
                      <strong>№ {participant.registration_number}</strong>
                      <span className="podium-points">{participant.total_points} <small>баллов</small></span>
                      <span className="podium-progress">
                        {participant.stations_completed} / {participant.stations_total} площадок
                      </span>
                    </article>
                  )
                })}
              </div>
            </section>
          )}

          <section className="results-section">
            <div className="section-title-row results-title-row">
              <div>
                <span className="section-kicker">ПОЛНЫЙ РЕЗУЛЬТАТ</span>
                <h2>Рейтинг участников</h2>
              </div>
              <label className="search-field">
                <span aria-hidden="true">⌕</span>
                <span className="sr-only">Поиск по номеру</span>
                <input
                  type="search"
                  placeholder="Найти участника"
                  value={filter}
                  onChange={(event) => setFilter(event.target.value)}
                />
              </label>
            </div>

            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col">МЕСТО</th>
                    <th scope="col">УЧАСТНИК</th>
                    <th scope="col">БАЛЛЫ</th>
                    <th scope="col">ПРОГРЕСС</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleParticipants.map((participant) => {
                    const progress = participant.stations_total
                      ? Math.round((participant.stations_completed / participant.stations_total) * 100)
                      : 0
                    return (
                      <tr key={participant.registration_number}>
                        <td>
                          <span className={`rank-badge ${participant.place <= 3 ? `rank-${participant.place}` : ''}`}>
                            {String(participant.place).padStart(2, '0')}
                          </span>
                        </td>
                        <td>
                          <span className="participant-number">№ {participant.registration_number}</span>
                          <span className="participant-caption">Номер участника</span>
                        </td>
                        <td><strong className="points-value">{participant.total_points}</strong><span className="points-unit">баллов</span></td>
                        <td>
                          <div className="progress-cell">
                            <span>{participant.stations_completed} из {participant.stations_total}</span>
                            <div
                              className="progress-track"
                              role="progressbar"
                              aria-label={`Пройдено площадок: ${participant.stations_completed} из ${participant.stations_total}`}
                              aria-valuemin={0}
                              aria-valuemax={participant.stations_total}
                              aria-valuenow={participant.stations_completed}
                            >
                              <span style={{ width: `${progress}%` }} />
                            </div>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                  {visibleParticipants.length === 0 && (
                    <tr>
                      <td className="empty-table" colSpan={4}>
                        {currentData.participants.length === 0
                          ? 'Участники появятся здесь после регистрации.'
                          : 'По этому номеру участников не найдено.'}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            <div className="table-footer">
              <span>Показано {visibleParticipants.length} из {currentData.participants.length} участников</span>
              <span>Все результаты доступны только для чтения</span>
            </div>
          </section>
        </>
      )}

      {loading && !currentData && (
        <div className="notice-card" role="status">
          <span className="loading-spinner" aria-hidden="true" />
          Загружаем таблицу результатов...
        </div>
      )}

      {error && (
        <div className="notice-card error-card" role="alert">
          <span aria-hidden="true">!</span>
          <div><strong>Не удалось открыть рейтинг</strong><p>{error}</p></div>
          <button
            type="button"
            onClick={() => {
              setEventId(eventIdInput.trim())
              setLoadedEventId('')
              setRetryKey((current) => current + 1)
            }}
          >
            Повторить
          </button>
        </div>
      )}

      {!eventId && !loading && !error && (
        <div className="notice-card welcome-card">
          <span className="welcome-icon" aria-hidden="true">↳</span>
          <div>
            <strong>Всё готово к старту</strong>
            <p>Введите номер мероприятия выше, чтобы открыть его таблицу результатов.</p>
          </div>
        </div>
      )}

      <footer className="footer">
        <a className="brand footer-brand" href="/">
          <span className="brand-mark" aria-hidden="true">k</span>
          <span>kerfuffle</span>
        </a>
        <span>Участие — это уже победа.</span>
        <span>© Kerfuffle 2026</span>
      </footer>
    </main>
  )
}

export default App
