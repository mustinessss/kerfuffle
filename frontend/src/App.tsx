import { useMemo, useState } from "react";
import "./styles.css";

type Tab = "overview" | "participants" | "stations" | "leaderboard";

const stations = [
  { id: "01", name: "Arrival & welcome", wing: "East wing", detail: "Check-in, identity and first impressions", min: 0, max: 10, visited: 42, color: "tomato", symbol: "✳" },
  { id: "02", name: "The nest", wing: "East wing", detail: "A small challenge about finding your place", min: 0, max: 10, visited: 35, color: "ochre", symbol: "◎" },
  { id: "03", name: "Common ground", wing: "Central hall", detail: "Build something together", min: 0, max: 5, visited: 28, color: "teal", symbol: "⌘" },
  { id: "04", name: "Quiet signals", wing: "West wing", detail: "Notice what others might miss", min: 0, max: 10, visited: 19, color: "ink", symbol: "· · ·" },
  { id: "05", name: "The exchange", wing: "West wing", detail: "Trade ideas, stories and points", min: 0, max: 10, visited: 14, color: "clay", symbol: "↗" },
  { id: "06", name: "The last room", wing: "North wing", detail: "One final moment before the finish", min: 0, max: 5, visited: 8, color: "pale", symbol: "✺" },
];

const people = [
  { number: "014", name: "Alex Morgan", points: 38, progress: "6 / 6" },
  { number: "027", name: "Jamie Rivera", points: 35, progress: "6 / 6" },
  { number: "008", name: "Taylor Kim", points: 35, progress: "5 / 6" },
  { number: "031", name: "Sam Parker", points: 29, progress: "5 / 6" },
  { number: "019", name: "Robin Ellis", points: 24, progress: "4 / 6" },
];

function SunMark() {
  return <span className="sun-mark" aria-hidden="true"><i /></span>;
}

function App() {
  const [tab, setTab] = useState<Tab>("overview");
  const [query, setQuery] = useState("");
  const [selectedEvent, setSelectedEvent] = useState("The Marigold Gathering");
  const [activeStation, setActiveStation] = useState("02");

  const filteredPeople = useMemo(
    () => people.filter((p) => `${p.name} ${p.number}`.toLowerCase().includes(query.toLowerCase())),
    [query],
  );

  const nav: { id: Tab; label: string; index: string }[] = [
    { id: "overview", label: "Overview", index: "01" },
    { id: "participants", label: "Participants", index: "02" },
    { id: "stations", label: "Stations", index: "03" },
    { id: "leaderboard", label: "Leaderboard", index: "04" },
  ];

  return (
    <main className="app-shell">
      <div className="topline">
        <div className="topline-brand"><span className="tiny-flower">✳</span> KERFUFFLE <span className="topline-muted">— EVENT FIELDNOTES</span></div>
        <div className="topline-center">LIVE EVENT · 06 NOVEMBER 2026</div>
        <div className="topline-right"><span className="live-dot" /> OPERATIONS DESK</div>
      </div>

      <header className="hero">
        <div className="hero-copy">
          <div className="eyebrow">THE GATHERING COLLECTION · NO. 001</div>
          <h1>MAKE ROOM<br />FOR <em>PLAY</em><span className="period">.</span></h1>
          <p className="hero-subtitle">A day of small adventures, generous ideas and unexpected connections</p>
        </div>
        <aside className="hero-aside">
          <div className="hero-art">
            <SunMark />
            <div className="art-caption">CURATED FOR<br /><strong>GOOD COMPANY</strong><small>people · places · possibility</small></div>
          </div>
          <div className="hero-meta">
            <div><span>ON VIEW</span><strong>TODAY → ALWAYS</strong></div>
            <div><span>FULL VISIT</span><strong>≈ 42 MINUTES</strong></div>
          </div>
        </aside>
      </header>

      <div className="visit-strip">
        <span className="strip-label">YOUR VISIT</span>
        <div className="progress-block"><div className="progress-segments">{stations.map((s, i) => <i key={s.id} className={i < 2 ? "filled" : ""} />)}</div><span>2 OF 6 ROOMS</span></div>
        <span className="strip-note">take your time — we'll keep your place</span>
      </div>

      <div className="workspace">
        <aside className="sidebar">
          <div className="sidebar-label">THE COLLECTION</div>
          <div className="event-picker">
            <span>SELECTED EVENT</span>
            <select value={selectedEvent} onChange={(e) => setSelectedEvent(e.target.value)}>
              <option>The Marigold Gathering</option>
              <option>Autumn Assembly</option>
              <option>Open Studio Night</option>
            </select>
          </div>
          <nav className="main-nav" aria-label="Main navigation">
            {nav.map((item) => (
              <button key={item.id} className={tab === item.id ? "nav-item active" : "nav-item"} onClick={() => setTab(item.id)}>
                <span>{item.index}</span>{item.label}<b>↗</b>
              </button>
            ))}
          </nav>
          <div className="sidebar-bottom">
            <div className="sidebar-label">FIELD STATUS</div>
            <div className="status-row"><span className="live-dot" /> All systems in bloom</div>
            <div className="sidebar-foot">KERFUFFLE OFFICE<br />ISSUE 001 / 2026</div>
          </div>
        </aside>

        <section className="content">
          <div className="content-heading">
            <div>
              <div className="eyebrow">WELCOME BACK · ORGANIZER VIEW</div>
              <h2>{nav.find((n) => n.id === tab)?.label}<span className="period">.</span></h2>
            </div>
            <button className="outline-button" onClick={() => setTab("leaderboard")}>VIEW LIVE BOARD <span>↗</span></button>
          </div>

          {tab === "overview" && <>
            <section className="stats-grid">
              <article className="stat-card stat-accent"><span>REGISTERED GUESTS</span><strong>128</strong><small>+ 18 since doors opened</small></article>
              <article className="stat-card"><span>POINTS AWARDED</span><strong>2,418</strong><small>across all six rooms</small></article>
              <article className="stat-card"><span>ROOMS COMPLETED</span><strong>04<span className="stat-unit">/ 06</span></strong><small>average guest progress</small></article>
              <article className="stat-card"><span>TIME TOGETHER</span><strong>42<span className="stat-unit">m</span></strong><small>average first visit</small></article>
            </section>

            <div className="section-title"><div><span className="eyebrow">EXPLORE THE FLOOR</span><h3>Rooms & stations</h3></div><span className="section-count">06 TOTAL ↘</span></div>
            <div className="station-grid">
              {stations.map((station) => (
                <button key={station.id} className={`station-card ${activeStation === station.id ? "selected" : ""}`} onClick={() => { setActiveStation(station.id); setTab("stations"); }}>
                  <div className="station-top"><span>ROOM {station.id}</span><span>{station.wing.toUpperCase()}</span><span className="view-status"><i /> {station.id === "01" ? "VISITED" : "ON VIEW"}</span></div>
                  <div className={`station-art ${station.color}`}><span className="station-number">{station.id}</span><span className="station-symbol">{station.symbol}</span></div>
                  <div className="station-info"><h4>{station.name}</h4><p>{station.detail}</p></div>
                  <div className="station-foot"><span>◷ &nbsp;{station.visited} VISITS</span><span>OPEN ROOM ↗</span></div>
                </button>
              ))}
            </div>

            <div className="section-title leaderboard-title"><div><span className="eyebrow">A LITTLE FRIENDLY COMPETITION</span><h3>Leading the way</h3></div><button className="text-button" onClick={() => setTab("leaderboard")}>FULL LEADERBOARD ↗</button></div>
            <Leaderboard rows={people.slice(0, 3)} />
          </>}

          {tab === "participants" && <>
            <div className="panel-intro"><p>Every guest has their own route through the rooms. Find a person to view their registration and progress.</p><button className="solid-button" onClick={() => alert("Connect this action to POST /events/{event_id}/participants")}>+ REGISTER GUEST</button></div>
            <div className="search-row"><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search by name or registration number…" /><span>{filteredPeople.length} GUESTS</span></div>
            <div className="people-list">{filteredPeople.map((p) => <div className="person-row" key={p.number}><span className="person-number">#{p.number}</span><strong>{p.name}</strong><span>{p.progress} ROOMS</span><b>{p.points} PTS</b></div>)}</div>
          </>}

          {tab === "stations" && <>
            <div className="station-detail">
              <div className={`detail-art ${stations.find(s => s.id === activeStation)?.color || "tomato"}`}><span>{stations.find(s => s.id === activeStation)?.symbol}</span><small>ROOM {activeStation}</small></div>
              <div className="detail-copy"><div className="eyebrow">STATION CONFIGURATION</div><h3>{stations.find(s => s.id === activeStation)?.name}</h3><p>{stations.find(s => s.id === activeStation)?.detail}</p><div className="scale-row"><span>SCORING SCALE</span><strong>0 — {stations.find(s => s.id === activeStation)?.max} POINTS · STEP 1</strong></div><div className="scale-row"><span>VISITS RECORDED</span><strong>{stations.find(s => s.id === activeStation)?.visited}</strong></div><button className="solid-button" onClick={() => alert("Station editing will be connected to the API.")}>EDIT STATION ↗</button></div>
            </div>
            <div className="section-title"><div><span className="eyebrow">ALL LOCATIONS</span><h3>Choose a room</h3></div></div>
            <div className="station-tabs">{stations.map(s => <button className={activeStation === s.id ? "chosen" : ""} onClick={() => setActiveStation(s.id)} key={s.id}>{s.id} / {s.name}</button>)}</div>
          </>}

          {tab === "leaderboard" && <>
            <div className="leaderboard-banner"><SunMark /><div><span className="eyebrow">THE CURRENT PICTURE</span><strong>Every point tells a story.</strong><small>Ranked by total points · ties share the same place</small></div><span className="live-pill"><i /> LIVE</span></div>
            <div className="search-row"><input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Find a guest…" /><span>UPDATED JUST NOW</span></div>
            <Leaderboard rows={filteredPeople} expanded />
          </>}
          <footer className="content-footer"><span>KERFUFFLE © 2026</span><span>MADE FOR GATHERING, NOT HURRYING.</span><span>ISSUE 001 · {selectedEvent.toUpperCase()}</span></footer>
        </section>
      </div>
    </main>
  );
}

function Leaderboard({ rows, expanded = false }: { rows: typeof people; expanded?: boolean }) {
  let lastPoints = -1;
  let rank = 0;
  return <div className="leaderboard">
    <div className="leader-head"><span>PLACE</span><span>GUEST</span><span>ROOMS VISITED</span><span>TOTAL POINTS</span></div>
    {rows.map((p, i) => {
      if (p.points !== lastPoints) rank = i + 1;
      lastPoints = p.points;
      return <div className="leader-row" key={p.number}><strong className="rank">{String(rank).padStart(2, "0")}</strong><span className="leader-name">{p.name}<small>REG. #{p.number}</small></span><span className="leader-progress">{p.progress}</span><strong className="leader-points">{p.points}<small>PTS</small></strong></div>;
    })}
    {rows.length === 0 && <div className="empty-state">No guests match that search yet.</div>}
    {!expanded && <div className="leader-note">A shared place is awarded when totals are equal. Time is never a tie-breaker.</div>}
  </div>;
}

export default App;
