import { useState, useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts'

const API = '/api'

// ── Data fetching ────────────────────────────────────────────────────────────
async function apiFetch(path: string) {
  try {
    const res = await fetch(API + path)
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return await res.json()
  } catch {
    return null
  }
}

// ── Types ────────────────────────────────────────────────────────────────────
interface GapScore {
  admin_unit_id: number; name: string; evs_total: number;
  public_chargers: number; evs_per_charger: number;
  coverage_pop_pct: number; gap_index: number; rank: number;
}

interface KPIs {
  totalChargers: number; totalEVs: number; highGapDistricts: number; avgCoverage: number;
}

// ── Colour helpers ───────────────────────────────────────────────────────────
function gapColor(gapIndex: number): string {
  if (gapIndex > 0.7) return '#ff4d4d'
  if (gapIndex > 0.5) return '#ff8c42'
  if (gapIndex > 0.3) return '#ffd60a'
  return '#39d98a'
}

// ── Components ───────────────────────────────────────────────────────────────

function DataBadge({ status }: { status: string }) {
  return <span className={`data-badge ${status}`}>{status}</span>
}

function KPICard({ label, value, color }: { label: string; value: string | number; color: string }) {
  return (
    <div className="kpi-card">
      <div className="kpi-label">{label}</div>
      <div className={`kpi-value ${color}`}>{value}</div>
    </div>
  )
}

// ── Map View ─────────────────────────────────────────────────────────────────
function MapView({ gaps }: { gaps: GapScore[] }) {
  const mapRef = useRef<HTMLDivElement>(null)
  const mapInstance = useRef<maplibregl.Map | null>(null)
  const [chargers, setChargers] = useState<any[]>([])

  useEffect(() => {
    apiFetch('/chargers?limit=2000').then(d => { if (d) setChargers(d) })
  }, [])

  useEffect(() => {
    if (!mapRef.current || mapInstance.current) return

    const map = new maplibregl.Map({
      container: mapRef.current,
      style: 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json?key=cb1_4ns0_1_ac540c55994fd3f92fe032cf',
      center: [75.71, 19.75],
      zoom: 6,
    })

    map.addControl(new maplibregl.NavigationControl(), 'top-right')
    map.addControl(new maplibregl.ScaleControl(), 'bottom-right')

    map.on('load', () => {
      // Charger points
      if (chargers.length > 0) {
        const geojson: GeoJSON.FeatureCollection = {
          type: 'FeatureCollection',
          features: chargers.map(c => ({
            type: 'Feature',
            geometry: c.geometry || { type: 'Point', coordinates: [0, 0] },
            properties: {
              name: c.name || 'Unknown',
              operator: c.operator || 'Unknown',
              max_power_kw: c.max_power_kw,
              current_type: c.current_type,
              data_status: c.data_status,
            },
          })),
        }

        map.addSource('chargers', { type: 'geojson', data: geojson, cluster: true, clusterMaxZoom: 12, clusterRadius: 40 })
        map.addLayer({ id: 'chargers-cluster', type: 'circle', source: 'chargers', filter: ['has', 'point_count'],
          paint: {
            'circle-color': ['step', ['get', 'point_count'], '#39d98a', 10, '#4da6ff', 50, '#ff8c42'],
            'circle-radius': ['step', ['get', 'point_count'], 16, 10, 22, 50, 30],
            'circle-opacity': 0.85,
          },
        })
        map.addLayer({ id: 'chargers-count', type: 'symbol', source: 'chargers', filter: ['has', 'point_count'],
          layout: { 'text-field': '{point_count_abbreviated}', 'text-size': 12 },
          paint: { 'text-color': '#0d1117', 'text-halo-color': '#0d1117', 'text-halo-width': 1 },
        })
        map.addLayer({ id: 'chargers-single', type: 'circle', source: 'chargers', filter: ['!', ['has', 'point_count']],
          paint: {
            'circle-color': ['match', ['get', 'current_type'], 'DC', '#4da6ff', '#39d98a'],
            'circle-radius': 7, 'circle-stroke-width': 1.5, 'circle-stroke-color': '#0d1117',
          },
        })

        map.on('click', 'chargers-single', (e) => {
          const props = e.features?.[0].properties
          new maplibregl.Popup({ className: 'charger-popup' })
            .setLngLat(e.lngLat)
            .setHTML(`<div style="font-family:Inter,sans-serif;padding:8px">
              <strong style="color:#39d98a">${props?.name || 'EV Charger'}</strong><br/>
              Operator: ${props?.operator || '—'}<br/>
              Power: ${props?.max_power_kw || '?'} kW · ${props?.current_type || '?'}<br/>
              <span style="font-size:10px;color:#8b949e">Source: ${props?.data_status}</span>
            </div>`)
            .addTo(map)
        })
        map.on('mouseenter', 'chargers-single', () => { map.getCanvas().style.cursor = 'pointer' })
        map.on('mouseleave', 'chargers-single', () => { map.getCanvas().style.cursor = '' })
      }
    })

    mapInstance.current = map
    return () => { map.remove(); mapInstance.current = null }
  }, [chargers])

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      <div ref={mapRef} style={{ width: '100%', height: '100%' }} />
      <div className="map-legend">
        <div style={{ fontWeight: 600, marginBottom: 6, fontSize: 11, color: '#8b949e', letterSpacing: '0.08em', textTransform: 'uppercase' }}>Legend</div>
        <div className="legend-item"><div className="legend-dot" style={{ background: '#4da6ff' }} />DC Fast Charger</div>
        <div className="legend-item"><div className="legend-dot" style={{ background: '#39d98a' }} />AC Charger</div>
        <div className="legend-item"><div className="legend-dot" style={{ background: '#ff4d4d' }} />High Gap District</div>
        <div style={{ marginTop: 8, fontSize: 10, color: '#484f58' }}>
          Map data © <a href="https://www.openstreetmap.org/copyright" style={{ color: '#4da6ff' }}>OSM</a> · © CARTO
        </div>
      </div>
    </div>
  )
}

// ── Dashboard View ───────────────────────────────────────────────────────────
function DashboardView({ kpis, gaps }: { kpis: KPIs; gaps: GapScore[] }) {
  const [scenario, setScenario] = useState('baseline')
  const [forecasts, setForecasts] = useState<any[]>([])

  useEffect(() => {
    apiFetch(`/forecasts?scenario=${scenario}`).then(d => { if (d) setForecasts(d) })
  }, [scenario])

  const chartData = forecasts.slice(0, 24).map((f: any) => ({
    period: f.period?.slice(0, 7),
    predicted: Math.round(f.evs_pred),
    lo: Math.round(f.lo || 0),
    hi: Math.round(f.hi || 0),
  }))

  return (
    <div style={{ padding: 16, overflowY: 'auto', flex: 1 }}>
      <div className="kpi-grid" style={{ marginBottom: 20 }}>
        <KPICard label="Total Chargers" value={kpis.totalChargers.toLocaleString()} color="green" />
        <KPICard label="EV Registrations" value={(kpis.totalEVs / 1000).toFixed(1) + 'K'} color="blue" />
        <KPICard label="High-Gap Districts" value={kpis.highGapDistricts} color="red" />
        <KPICard label="Avg. Pop. Coverage" value={(kpis.avgCoverage * 100).toFixed(0) + '%'} color="orange" />
      </div>

      <div style={{ marginBottom: 16 }}>
        <div className="sidebar-title">EV Growth Forecast</div>
        <select
          value={scenario}
          onChange={e => setScenario(e.target.value)}
          style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', color: 'var(--text-primary)', borderRadius: 'var(--radius)', padding: '4px 8px', marginBottom: 12, fontFamily: 'var(--font)' }}
        >
          <option value="baseline">Baseline</option>
          <option value="accelerated">Accelerated (PM E-DRIVE)</option>
          <option value="conservative">Conservative</option>
        </select>
        <ResponsiveContainer width="100%" height={180}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#21262d" />
            <XAxis dataKey="period" tick={{ fill: '#8b949e', fontSize: 10 }} />
            <YAxis tick={{ fill: '#8b949e', fontSize: 10 }} />
            <Tooltip contentStyle={{ background: '#1c2128', border: '1px solid #30363d', color: '#e6edf3' }} />
            <Line type="monotone" dataKey="predicted" stroke="#39d98a" strokeWidth={2} dot={false} name="EV Forecast" />
            <Line type="monotone" dataKey="hi" stroke="#4da6ff" strokeWidth={1} dot={false} strokeDasharray="4 4" name="Upper" />
            <Line type="monotone" dataKey="lo" stroke="#ff8c42" strokeWidth={1} dot={false} strokeDasharray="4 4" name="Lower" />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div>
        <div className="sidebar-title">Top Underserved Districts</div>
        <table className="data-table">
          <thead>
            <tr><th>Rank</th><th>District</th><th>Gap Index</th><th>EVs/Charger</th></tr>
          </thead>
          <tbody>
            {gaps.slice(0, 10).map(g => (
              <tr key={g.admin_unit_id}>
                <td><strong style={{ color: g.rank <= 3 ? 'var(--accent-red)' : 'var(--text-primary)' }}>#{g.rank}</strong></td>
                <td>{g.name}</td>
                <td><span style={{ color: gapColor(g.gap_index), fontWeight: 600 }}>{(g.gap_index).toFixed(3)}</span></td>
                <td>{g.evs_per_charger?.toFixed(0) || '∞'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── What-If Simulator ─────────────────────────────────────────────────────────
function SimulatorView() {
  const [weights, setWeights] = useState({
    evs_per_charger: 0.30, coverage: 0.25, demand: 0.20, growth: 0.10, corridor: 0.15
  })

  const totalWeight = Object.values(weights).reduce((a, b) => a + b, 0)
  const valid = Math.abs(totalWeight - 1.0) < 0.01

  const Slider = ({ key: k, label }: { key: string; label: string }) => (
    <div className="slider-row">
      <span className="slider-label">{label}</span>
      <input type="range" className="slider-input" min={0} max={100} step={5}
        value={Math.round(weights[k as keyof typeof weights] * 100)}
        onChange={e => setWeights(w => ({ ...w, [k]: +e.target.value / 100 }))}
      />
      <span className="slider-val">{(weights[k as keyof typeof weights] * 100).toFixed(0)}%</span>
    </div>
  )

  return (
    <div style={{ padding: 16, overflowY: 'auto', flex: 1 }}>
      <div className="sidebar-title">Gap Index Weights</div>
      <p style={{ color: 'var(--text-secondary)', fontSize: 12, marginBottom: 16 }}>
        Adjust the relative importance of each indicator in the Charging Gap Index.
        Weights must sum to 100%.
      </p>

      <Slider key="evs_per_charger" label="EVs/Charger" />
      <Slider key="coverage" label="Coverage" />
      <Slider key="demand" label="Demand Score" />
      <Slider key="growth" label="Growth Rate" />
      <Slider key="corridor" label="Corridor Gap" />

      <div style={{ marginTop: 12, padding: '8px 12px', background: valid ? 'rgba(57,217,138,0.08)' : 'rgba(255,77,77,0.08)',
        border: `1px solid ${valid ? 'rgba(57,217,138,0.3)' : 'rgba(255,77,77,0.3)'}`, borderRadius: 'var(--radius)' }}>
        <span style={{ color: valid ? 'var(--accent-green)' : 'var(--accent-red)', fontWeight: 600 }}>
          Total: {(totalWeight * 100).toFixed(0)}% {valid ? '✓' : '— must equal 100%'}
        </span>
      </div>

      <button className="btn btn-primary" style={{ marginTop: 16, width: '100%' }}>
        Recompute Gap Index
      </button>
    </div>
  )
}

// ── Methodology View ─────────────────────────────────────────────────────────
function MethodologyView() {
  const [assumptions, setAssumptions] = useState<any[]>([])
  const [sources, setSources] = useState<any[]>([])

  useEffect(() => {
    apiFetch('/meta/assumptions').then(d => { if (d) setAssumptions(d) })
    apiFetch('/meta/sources').then(d => { if (d) setSources(d) })
  }, [])

  return (
    <div style={{ padding: 16, overflowY: 'auto', flex: 1 }}>
      <div className="sidebar-title" style={{ marginBottom: 12 }}>Assumptions</div>
      <table className="data-table" style={{ marginBottom: 24 }}>
        <thead><tr><th>Key</th><th>Value</th><th>Unit</th><th>Status</th></tr></thead>
        <tbody>
          {assumptions.map(a => (
            <tr key={a.key}>
              <td style={{ fontFamily: 'monospace', fontSize: 11 }}>{a.key}</td>
              <td>{a.value}</td>
              <td style={{ color: 'var(--text-muted)' }}>{a.unit}</td>
              <td><DataBadge status={a.data_status || 'derived'} /></td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="sidebar-title" style={{ marginBottom: 12 }}>Data Sources</div>
      <table className="data-table">
        <thead><tr><th>Name</th><th>Licence</th><th>Accessed</th></tr></thead>
        <tbody>
          {sources.map(s => (
            <tr key={s.id}>
              <td>{s.name}</td>
              <td style={{ color: 'var(--text-muted)' }}>{s.licence || '—'}</td>
              <td style={{ color: 'var(--text-muted)' }}>{s.accessed_at || '—'}</td>
            </tr>
          ))}
          {sources.length === 0 && (
            <tr><td colSpan={3} style={{ color: 'var(--text-muted)', textAlign: 'center' }}>No sources loaded yet</td></tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

// ── Main App ─────────────────────────────────────────────────────────────────
export default function App() {
  const [tab, setTab] = useState<'map' | 'dashboard' | 'simulator' | 'methodology'>('map')
  const [gaps, setGaps] = useState<GapScore[]>([])
  const [kpis, setKpis] = useState<KPIs>({ totalChargers: 0, totalEVs: 0, highGapDistricts: 0, avgCoverage: 0 })

  useEffect(() => {
    // Load gap scores for district ranking + partial KPIs
    apiFetch('/gaps?level=district').then(d => {
      if (!d) return
      setGaps(d)
      setKpis(prev => ({
        ...prev,
        totalEVs: d.reduce((s: number, g: GapScore) => s + (g.evs_total || 0), 0),
        highGapDistricts: d.filter((g: GapScore) => g.gap_index > 0.5).length,
        avgCoverage: d.length ? d.reduce((s: number, g: GapScore) => s + (g.coverage_pop_pct || 0), 0) / d.length : 0,
      }))
    })
    // Fetch real charger count directly
    apiFetch('/chargers?limit=5000').then(d => {
      if (d && Array.isArray(d)) {
        setKpis(prev => ({ ...prev, totalChargers: d.length }))
      }
    })
  }, [])

  return (
    <div className="app">
      {/* Navbar */}
      <nav className="navbar">
        <a className="navbar-brand" href="#">
          <div className="dot" />
          EV_Nirvana
        </a>
        <div className="navbar-tabs">
          {(['map', 'dashboard', 'simulator', 'methodology'] as const).map(t => (
            <button key={t} className={`tab-btn${tab === t ? ' active' : ''}`} onClick={() => setTab(t)}>
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          ))}
        </div>
        <DataBadge status="synthetic" />
        <span style={{ color: 'var(--text-muted)', fontSize: 11 }}>Maharashtra</span>
      </nav>

      {/* Main content */}
      <div className="main-content">
        {/* Sidebar — always visible */}
        <aside className="sidebar">
          <div className="sidebar-section">
            <div className="sidebar-title">KPIs</div>
            <div className="kpi-grid">
              <KPICard label="Chargers" value={kpis.totalChargers.toLocaleString()} color="green" />
              <KPICard label="EV Registrations" value={(kpis.totalEVs / 1000 || 0).toFixed(1) + 'K'} color="blue" />
              <KPICard label="High-Gap Districts" value={kpis.highGapDistricts} color="red" />
              <KPICard label="Avg Coverage" value={(kpis.avgCoverage * 100).toFixed(0) + '%'} color="orange" />
            </div>
          </div>

          {tab === 'map' && (
            <div className="sidebar-section">
              <div className="sidebar-title">District Ranking (Top 5)</div>
              <table className="data-table">
                <thead><tr><th>#</th><th>District</th><th>CGI</th></tr></thead>
                <tbody>
                  {gaps.slice(0, 5).map(g => (
                    <tr key={g.admin_unit_id}>
                      <td style={{ color: 'var(--accent-red)', fontWeight: 700 }}>#{g.rank}</td>
                      <td>{g.name}</td>
                      <td><span style={{ color: gapColor(g.gap_index) }}>{g.gap_index?.toFixed(3)}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {tab === 'simulator' && <SimulatorView />}
          {tab === 'methodology' && <MethodologyView />}
          {tab === 'dashboard' && <DashboardView kpis={kpis} gaps={gaps} />}
        </aside>

        {/* Map always shown */}
        <div className="map-container">
          <MapView gaps={gaps} />
        </div>
      </div>

      {/* Status bar */}
      <div className="status-bar">
        <div className="status-dot" />
        <span>Maharashtra</span>
        <span>·</span>
        <DataBadge status="synthetic" />
        <span style={{ marginLeft: 4 }}>EV registrations are synthetic — replace with real VAHAN data</span>
        <span style={{ marginLeft: 'auto' }}>OSM © OpenStreetMap contributors (ODbL)</span>
      </div>
    </div>
  )
}
