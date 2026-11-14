import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import {
  Activity, BarChart3, Bell, BrainCircuit, Check, ChevronDown,
  Database, FileText, LayoutDashboard, LogOut, Menu, Plus,
  RefreshCw, Search, Settings, Shield, ShieldCheck, Users, Wallet, Zap
} from 'lucide-react'
import {
  createChart, CandlestickSeries,
  type IChartApi, type ISeriesApi, type CandlestickData, type Time
} from 'lightweight-charts'
import { api, setToken, token } from './api'

type Me = { id: number; email: string; full_name: string; role: string; status: string }
type Signal = {
  symbol: string
  timeframe?: string
  resolution?: string
  signal: 'LONG' | 'SHORT' | 'WAIT' | string
  entry?: number | null
  stop_loss?: number | null
  targets?: number[]
  target_profit_pct?: number[]
  risk_reward?: number[]
  score?: number
  indicators?: Record<string, number | null>
  votes?: Record<string, string | boolean | number | null>
  disclaimer?: string
  status?: string
}
type Candle = { time: number | string; open: number; high: number; low: number; close: number; volume?: number }

const money = (value: unknown) => {
  if (value === null || value === undefined || value === '') return '—'
  const n = Number(value)
  return Number.isFinite(n) ? n.toLocaleString('en-IN', { maximumFractionDigits: 4 }) : '—'
}

function toChartTime(value: number | string): Time | null {
  let n = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(n)) {
    const parsed = Date.parse(String(value))
    if (!Number.isFinite(parsed)) return null
    n = parsed / 1000
  }
  if (n > 1e14) n /= 1e6
  else if (n > 1e11) n /= 1e3
  return Math.floor(n) as Time
}

function normalizeCandles(data: any): Candle[] {
  const rows = Array.isArray(data) ? data : data?.candles ?? data?.result ?? []
  if (!Array.isArray(rows)) return []
  return rows.map((item: any) => ({
    time: item.time ?? item.timestamp ?? item.t,
    open: Number(item.open ?? item.o),
    high: Number(item.high ?? item.h),
    low: Number(item.low ?? item.l),
    close: Number(item.close ?? item.c),
    volume: Number(item.volume ?? item.v ?? 0),
  })).filter((c: Candle) => c.time !== undefined && c.time !== null &&
    [c.open, c.high, c.low, c.close].every(Number.isFinite) &&
    c.open > 0 && c.high >= c.low && c.low > 0 && c.close > 0)
}

function voteText(value: unknown) {
  if (value === true) return 'Confirmed'
  if (value === false) return 'Not confirmed'
  return value === null || value === undefined ? 'Neutral' : String(value)
}

function voteTone(value: unknown) {
  const v = voteText(value).toLowerCase()
  if (v.includes('bullish') || v.includes('confirmed') || v.includes('strong')) return 'green'
  if (v.includes('bearish') || v.includes('not confirmed') || v.includes('weak')) return 'red'
  return 'muted'
}

function TradeChart({ candles, signal }: { candles: Candle[]; signal: Signal | null }) {
  const host = useRef<HTMLDivElement | null>(null)
  const chart = useRef<IChartApi | null>(null)
  const series = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const lines = useRef<any[]>([])

  useEffect(() => {
    if (!host.current) return
    const instance = createChart(host.current, {
      width: host.current.clientWidth,
      height: 390,
      layout: { background: { color: '#0b1522' }, textColor: '#91a4bc' },
      grid: { vertLines: { color: '#17263a' }, horzLines: { color: '#17263a' } },
      rightPriceScale: { borderColor: '#26384d' },
      timeScale: { borderColor: '#26384d', timeVisible: true, secondsVisible: false },
      crosshair: { vertLine: { color: '#536b84' }, horzLine: { color: '#536b84' } },
    })
    const candleSeries = instance.addSeries(CandlestickSeries, {
      upColor: '#36c99a', downColor: '#f06f82',
      borderUpColor: '#36c99a', borderDownColor: '#f06f82',
      wickUpColor: '#36c99a', wickDownColor: '#f06f82',
    })
    chart.current = instance
    series.current = candleSeries
    const resize = () => {
      if (host.current && chart.current) chart.current.applyOptions({ width: host.current.clientWidth })
    }
    window.addEventListener('resize', resize)
    return () => {
      window.removeEventListener('resize', resize)
      instance.remove()
      chart.current = null
      series.current = null
      lines.current = []
    }
  }, [])

  useEffect(() => {
    if (!series.current) return
    lines.current.forEach(line => {
      try { series.current?.removePriceLine(line) } catch { /* already removed */ }
    })
    lines.current = []

    const sorted = candles.map(c => {
      const time = toChartTime(c.time)
      if (time === null) return null
      return { time, open: c.open, high: c.high, low: c.low, close: c.close }
    }).filter((c): c is CandlestickData<Time> => c !== null)
      .sort((a, b) => Number(a.time) - Number(b.time))

    const unique = sorted.filter((c, i) => i === 0 || Number(c.time) !== Number(sorted[i - 1].time))
    if (unique.length) series.current.setData(unique)

    if (signal && (signal.signal === 'LONG' || signal.signal === 'SHORT')) {
      const levels = [
        { price: signal.entry, color: '#60d9c4', title: 'ENTRY' },
        { price: signal.stop_loss, color: '#f06f82', title: 'STOP LOSS' },
        ...(signal.targets ?? []).map((price, i) => ({ price, color: '#e9c66f', title: `TP${i + 1}` })),
      ]
      levels.forEach(level => {
        if (typeof level.price !== 'number' || !Number.isFinite(level.price)) return
        const line = series.current?.createPriceLine({
          price: level.price, color: level.color, lineWidth: 2,
          lineStyle: 2, axisLabelVisible: true, title: level.title,
        })
        if (line) lines.current.push(line)
      })
    }
    if (unique.length) chart.current?.timeScale().fitContent()
  }, [candles, signal])

  return <div className="chart-shell">
    <div className="chart-legend">
      <span><i className="bull" /> Bullish</span>
      <span><i className="bear" /> Bearish</span>
      <span>Entry / SL / Targets</span>
    </div>
    <div ref={host} className="chart-host" />
    {!candles.length && <div className="chart-empty">Run analysis to load exchange candles.</div>}
  </div>
}

export default function App() {
  const [me, setMe] = useState<Me | null>(null)
  const [page, setPage] = useState('Overview')
  const [authPage, setAuthPage] = useState<'Login' | 'Register'>('Login')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [symbol, setSymbol] = useState('BTCUSD')
  const [tf, setTf] = useState('15m')
  const [signal, setSignal] = useState<Signal | null>(null)
  const [candles, setCandles] = useState<Candle[]>([])
  const [users, setUsers] = useState<any[]>([])
  const [products, setProducts] = useState<any[]>([])
  const [tickers, setTickers] = useState<any[]>([])
  const [marketEnv, setMarketEnv] = useState('unknown')
  const [credentialEnv, setCredentialEnv] = useState('demo')
  const [apiKey, setApiKey] = useState('')
  const [apiSecret, setApiSecret] = useState('')
  const [sidebar, setSidebar] = useState(true)
  const [journal, setJournal] = useState<any[]>([])
  const authed = Boolean(token())

  async function loadMe() {
    try { setMe(await api('/me')) }
    catch { setMe(null); setToken('') }
  }

  useEffect(() => { if (authed) void loadMe() }, [])
  useEffect(() => {
    if (me?.status === 'approved' || me?.role === 'admin') void refreshOverview()
  }, [me])

  async function refreshOverview() {
    try {
      setError('')
      const [p, t, s] = await Promise.all([
        api('/market/products'), api('/market/tickers'), api('/market/status'),
      ])
      setProducts(Array.isArray(p) ? p : p?.result ?? [])
      setTickers(Array.isArray(t) ? t : t?.result ?? [])
      setMarketEnv(s?.market_data_environment ?? s?.environment ?? 'unknown')
    } catch (e: any) { setError(e.message || 'Could not refresh market data') }
  }

  async function login(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError(''); setMessage('')
    try {
      const body = new URLSearchParams({ username: email, password })
      const result = await api('/auth/login', { method: 'POST', body })
      setToken(result.access_token)
      const user = await api('/me')
      setMe(user); setPage('Overview'); setMessage('Welcome back')
    } catch (e: any) { setError(e.message || 'Login failed') }
    finally { setBusy(false) }
  }

  async function register(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError(''); setMessage('')
    try {
      const result = await api('/auth/register', {
        method: 'POST', body: JSON.stringify({ email, full_name: name, password }),
      })
      setMessage(result.message || 'Registration received')
      setAuthPage('Login')
    } catch (e: any) { setError(e.message || 'Registration failed') }
    finally { setBusy(false) }
  }

  async function scan() {
    if (!symbol.trim()) { setError('Enter a contract symbol'); return }
    setBusy(true); setError(''); setMessage(''); setSignal(null); setCandles([])
    const payload = { symbol: symbol.trim().toUpperCase(), resolution: tf, limit: 250 }
    try {
      const [signalData, candleData] = await Promise.all([
        api('/analysis/signal', { method: 'POST', body: JSON.stringify(payload) }),
        api('/analysis/candles', { method: 'POST', body: JSON.stringify(payload) }),
      ])
      if (!signalData || !signalData.signal) throw new Error('Backend returned an invalid signal response')
      const parsedCandles = normalizeCandles(candleData)
      if (!parsedCandles.length) throw new Error('No valid candles returned for chart')
      setSignal(signalData)
      setCandles(parsedCandles)
    } catch (e: any) { setError(e.message || 'Analysis failed') }
    finally { setBusy(false) }
  }

  async function adminUsers() {
    try { setUsers(await api('/admin/users')) }
    catch (e: any) { setError(e.message || 'Could not load users') }
  }

  async function changeStatus(id: number, status: string) {
    try {
      await api(`/admin/users/${id}/status`, { method: 'PATCH', body: JSON.stringify({ status }) })
      await adminUsers(); setMessage(`User status updated: ${status}`)
    } catch (e: any) { setError(e.message || 'Could not update status') }
  }

  async function connectDelta(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError(''); setMessage('')
    try {
      const result = await api('/delta/credentials', {
        method: 'PUT',
        body: JSON.stringify({ api_key: apiKey, api_secret: apiSecret, environment: credentialEnv }),
      })
      setMessage(result.connected ? 'Encrypted credentials saved' : 'Credentials saved')
      setApiKey(''); setApiSecret('')
    } catch (e: any) { setError(e.message || 'Could not save credentials') }
    finally { setBusy(false) }
  }

  async function loadJournal() {
    try { setJournal(await api('/journal')) }
    catch (e: any) { setError(e.message || 'Could not load journal') }
  }

  function logout() {
    setToken(''); setMe(null); setSignal(null); setCandles([])
    setPage('Overview'); setAuthPage('Login'); setError(''); setMessage('')
  }

  const stats = useMemo(() => ({ contracts: products.length, tickers: tickers.length }), [products, tickers])
  const nav: any[] = [
    ['Overview', LayoutDashboard], ['Market Scanner', Activity], ['AI Signals', BrainCircuit],
    ['Portfolio', Wallet], ['Trade Journal', FileText], ['Connect Exchange', Database],
    ...(me?.role === 'admin' ? [['User Management', Users], ['Audit & Security', ShieldCheck]] : []),
    ['Settings', Settings],
  ]

  if (!me) return <div className="auth-shell"><div className="auth-card">
    <div className="brand-mark"><Zap /></div>
    <div className="eyebrow">DELTA AI / TRADING INTELLIGENCE</div>
    <h1>{authPage === 'Register' ? 'Create your account' : 'Trade with clarity.'}</h1>
    <p className="muted">A private, admin-approved market analysis workspace.</p>
    <div className="auth-tabs">
      <button className={authPage === 'Login' ? 'active' : ''} onClick={() => setAuthPage('Login')}>Sign in</button>
      <button className={authPage === 'Register' ? 'active' : ''} onClick={() => setAuthPage('Register')}>Create account</button>
    </div>
    {authPage === 'Register' ? <form onSubmit={register}>
      <label>Full name</label><input required value={name} onChange={e => setName(e.target.value)} placeholder="Your name" />
      <label>Email address</label><input required type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" />
      <label>Password · 12 characters minimum</label><input required minLength={12} maxLength={72} type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="Create a strong password" />
      <button className="primary wide" disabled={busy}>{busy ? 'Creating…' : 'Request access'}</button>
    </form> : <form onSubmit={login}>
      <label>Email address</label><input required type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="you@example.com" />
      <label>Password</label><input required type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder="Your password" />
      <button className="primary wide" disabled={busy}>{busy ? 'Signing in…' : 'Sign in securely'}</button>
    </form>}
    {error && <div className="alert error">{error}</div>}
    {message && <div className="alert success">{message}</div>}
    <div className="auth-foot"><Shield size={14} /> Admin approval required · Order execution disabled</div>
  </div></div>

  return <div className="app-shell">
    <aside className={`sidebar ${sidebar ? '' : 'closed'}`}>
      <div className="brand"><div className="brand-mark"><Zap /></div><div><b>DELTA<span>AI</span></b><small>TRADING TERMINAL</small></div></div>
      <div className="workspace"><span className="online-dot" /> PRIVATE WORKSPACE <ChevronDown size={13} /></div>
      <div className="nav-label">WORKSPACE</div>
      {nav.map(([label, Icon]) => <button key={label} className={`nav-item ${page === label ? 'selected' : ''}`} onClick={() => {
        setPage(label); if (label === 'User Management') void adminUsers(); if (label === 'Trade Journal') void loadJournal()
      }}><Icon size={17} />{label}{label === 'User Management' && <span className="nav-count">{users.filter(u => u.status === 'pending').length}</span>}</button>)}
      <div className="sidebar-bottom">
        <div className="secure-card"><ShieldCheck size={17} /><b>Account protected</b><small>Encrypted credentials · Role-based access</small></div>
        <button className="nav-item" onClick={logout}><LogOut size={17} />Sign out</button>
        <div className="profile"><div className="avatar">{me.full_name.slice(0, 1).toUpperCase()}</div><div><b>{me.full_name}</b><small>{me.role === 'admin' ? 'SUPER ADMIN' : 'TRADER'} · {me.status.toUpperCase()}</small></div></div>
      </div>
    </aside>

    <main className="main">
      <header className="topbar">
        <button className="icon-btn" onClick={() => setSidebar(!sidebar)}><Menu /></button>
        <div className="crumb">Workspace <span>/</span> {page}</div>
        <div className="top-actions">
          <span className="env-pill"><i /> MARKET DATA: {marketEnv.toUpperCase()}</span>
          <button className="icon-btn" title="Refresh" onClick={() => void refreshOverview()}><RefreshCw size={17} /></button>
          <button className="icon-btn" title="Notifications"><Bell size={17} /></button>
          <div className="avatar mini">{me.full_name.slice(0, 1).toUpperCase()}</div>
        </div>
      </header>

      <div className="content">
        <div className="page-heading"><div><div className="eyebrow">DELTA EXCHANGE · MARKET INTELLIGENCE</div><h1>{page}</h1><p className="muted">{page === 'Overview' ? 'Your market at a glance. Stay disciplined, trade your plan.' : `Manage your ${page.toLowerCase()} workspace.`}</p></div>
          <div className="heading-actions"><button className="secondary" onClick={() => void refreshOverview()}><RefreshCw size={15} /> Refresh data</button><button className="primary" onClick={() => setPage('Market Scanner')}><Plus size={16} /> New analysis</button></div>
        </div>

        {error && <div className="alert error">{error}<button onClick={() => setError('')}>×</button></div>}
        {message && <div className="alert success">{message}<button onClick={() => setMessage('')}>×</button></div>}

        {me.status !== 'approved' && me.role !== 'admin' ? <div className="panel pending"><Shield size={26} /><h2>Access pending approval</h2><p>Your account is registered. The administrator must approve access before market features unlock.</p><span className="status pending-tag">{me.status}</span></div> : <>

          {page === 'Overview' && <>
            <div className="stats-grid">
              <div className="stat-card"><div className="stat-top">Available contracts <BarChart3 /></div><strong>{stats.contracts || '—'}</strong><small>Returned by Delta product catalogue</small></div>
              <div className="stat-card"><div className="stat-top">Ticker records <Activity /></div><strong>{stats.tickers || '—'}</strong><small>Public market snapshot</small></div>
              <div className="stat-card"><div className="stat-top">Order execution <ShieldCheck /></div><strong className="green">DISABLED</strong><small>Analysis-only build</small></div>
              <div className="stat-card"><div className="stat-top">Access status <Users /></div><strong className="green">ACTIVE</strong><small>{me.role === 'admin' ? 'Platform owner' : 'Approved trader'}</small></div>
            </div>
            <div className="two-col">
              <section className="panel"><div className="panel-head"><div><h3>Market watch</h3><p>Products loaded from Delta Exchange</p></div><button className="text-btn" onClick={() => setPage('Market Scanner')}>Open scanner ↗</button></div>
                <div className="market-list">{tickers.slice(0, 7).map((t: any, i: number) => <div className="market-row" key={t.symbol || i}><div className="coin-icon">{(t.symbol || 'D').slice(0, 1)}</div><div className="market-name"><b>{t.symbol || t.product?.symbol || 'Contract'}</b><small>Delta market</small></div><div className="market-price">{money(t.close ?? t.last_price ?? t.mark_price)}</div><span className="muted tiny">Snapshot</span></div>)}{!tickers.length && <div className="empty">Market data will appear after the API responds.</div>}</div>
              </section>
              <section className="panel"><div className="panel-head"><div><h3>Analysis engine</h3><p>Rule-based technical confluence</p></div><BrainCircuit /></div><div className="signal-promo"><div className="signal-orb"><BrainCircuit size={30} /></div><h2>Find the setup.<br /><em>Respect the risk.</em></h2><p>Scan a Delta contract and inspect the indicators, entry reference, stop and target estimates.</p><button className="primary wide" onClick={() => setPage('Market Scanner')}>Launch market scanner</button></div></section>
            </div>
          </>}

          {(page === 'Market Scanner' || page === 'AI Signals') && <>
            <div className="two-col scanner-layout">
              <section className="panel"><div className="panel-head"><div><h3>Technical analysis scanner</h3><p>EMA · RSI · MACD · ADX · VWAP · ATR · Bollinger Bands</p></div><Activity /></div>
                <div className="form-grid"><div><label>Contract symbol</label><input value={symbol} onChange={e => setSymbol(e.target.value)} placeholder="BTCUSD" /></div><div><label>Timeframe</label><select value={tf} onChange={e => setTf(e.target.value)}>{['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '12h', '1d', '1w'].map(x => <option key={x} value={x}>{x}</option>)}</select></div></div>
                <button className="primary" disabled={busy} onClick={() => void scan()}><Search size={16} />{busy ? 'Analysing…' : 'Analyse market'}</button>
                <div className="disclaimer">The score measures indicator agreement, not the probability of profit. WAIT is a valid result.</div>
              </section>

              <section className="panel"><div className="panel-head"><div><h3>Signal result</h3><p>Wait for confluence; avoid forced trades</p></div><Zap /></div>
                {signal ? <>
                  <div className={`signal-result ${signal.signal.toLowerCase()}`}><span>DETECTED DIRECTION</span><strong>{signal.signal}</strong><small>Indicator agreement · {money(signal.score)}%</small></div>
                  <div className="result-grid"><div><small>Entry reference</small><b>{money(signal.entry)}</b></div><div><small>Stop loss</small><b>{money(signal.stop_loss)}</b></div>{(signal.targets ?? []).map((target, i) => <div key={i}><small>Target {i + 1}</small><b>{money(target)}</b></div>)}</div>
                  {(signal.targets?.length ?? 0) > 0 && <div className="panel-subsection"><h4>Potential price movement</h4>{signal.targets?.map((_, i) => <div className="confirm-row" key={i}><span>TP{i + 1}</span><b className="green">{signal.target_profit_pct?.[i] !== undefined ? `${money(signal.target_profit_pct[i])}%` : '—'}</b></div>)}<small className="muted">Price movement estimate before fees, funding, slippage and contract sizing. Not actual P&amp;L.</small></div>}
                  {(signal.risk_reward?.length ?? 0) > 0 && <div className="panel-subsection"><h4>Risk / Reward estimate</h4>{signal.risk_reward?.map((ratio, i) => <div className="confirm-row" key={i}><span>Target {i + 1}</span><b>1 : {money(ratio)}</b></div>)}</div>}
                  <h4>Indicator confirmations</h4>{Object.entries(signal.votes ?? {}).map(([key, value]) => <div className="confirm-row" key={key}><span>{key}</span><span className={voteTone(value)}>{voteText(value)}</span></div>)}
                  {signal.indicators && <div className="panel-subsection"><h4>Indicator values</h4>{Object.entries(signal.indicators).map(([key, value]) => <div className="confirm-row" key={key}><span>{key.replaceAll('_', ' ').toUpperCase()}</span><b>{money(value)}</b></div>)}</div>}
                  <div className="disclaimer">{signal.disclaimer || 'Technical analysis is an estimate, not a guaranteed trading result.'}</div>
                </> : <div className="empty large"><BrainCircuit size={30} /><b>No analysis yet</b><span>Choose a symbol and timeframe, then run analysis.</span></div>}
              </section>
            </div>
            <section className="panel chart-panel"><div className="panel-head"><div><h3>Price action & trade plan</h3><p>Exchange candlesticks · Entry, stop loss and target overlays</p></div><BarChart3 /></div><TradeChart candles={candles} signal={signal} /></section>
          </>}

          {page === 'Portfolio' && <div className="panel"><div className="panel-head"><div><h3>Account overview</h3><p>Private Delta account data for this user</p></div><Wallet /></div>
            <button className="secondary" onClick={async () => { try { setMessage(JSON.stringify(await api('/account/wallet'))) } catch (e: any) { setError(e.message) } }}>Fetch wallet balances</button>
            <button className="secondary" onClick={async () => { try { setMessage(JSON.stringify(await api('/account/positions'))) } catch (e: any) { setError(e.message) } }}>Fetch open positions</button>
            <p className="muted">Private account reads require your own environment-matched API credentials. Order execution remains disabled.</p></div>}

          {page === 'Connect Exchange' && <section className="panel narrow"><div className="panel-head"><div><h3>Connect Delta Exchange</h3><p>Your API keys are encrypted before storage.</p></div><Database /></div>
            <form onSubmit={connectDelta}><label>Credential environment</label><select value={credentialEnv} onChange={e => setCredentialEnv(e.target.value)}><option value="demo">Demo / Testnet</option><option value="live">Production</option></select><label>API key</label><input required value={apiKey} onChange={e => setApiKey(e.target.value)} autoComplete="off" /><label>API secret</label><input required type="password" value={apiSecret} onChange={e => setApiSecret(e.target.value)} autoComplete="new-password" /><button className="primary" disabled={busy}>{busy ? 'Saving…' : 'Save encrypted credentials'}</button></form>
            <div className="disclaimer">Never share API keys. Use least-privilege permissions and IP restrictions. Saving credentials does not enable orders.</div></section>}

          {page === 'User Management' && me.role === 'admin' && <section className="panel"><div className="panel-head"><div><h3>Access control</h3><p>Approve, reject or suspend platform accounts</p></div><button className="secondary" onClick={() => void adminUsers()}><RefreshCw size={14} /> Refresh</button></div>
            <div className="table-wrap"><table><thead><tr><th>USER</th><th>EMAIL</th><th>STATUS</th><th>CREATED</th><th>ACTIONS</th></tr></thead><tbody>{users.map(u => <tr key={u.id}><td>{u.full_name}</td><td>{u.email}</td><td><span className={`status ${u.status}`}>{u.status}</span></td><td>{u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}</td><td><div className="row-actions"><button onClick={() => void changeStatus(u.id, 'approved')}>Approve</button><button onClick={() => void changeStatus(u.id, 'suspended')}>Suspend</button><button onClick={() => void changeStatus(u.id, 'rejected')}>Reject</button></div></td></tr>)}</tbody></table></div></section>}

          {page === 'Trade Journal' && <section className="panel"><div className="panel-head"><div><h3>Trade journal</h3><p>Personal trade notes and review</p></div><FileText /></div><button className="secondary" onClick={() => void loadJournal()}>Refresh journal</button>{journal.map((j, i) => <div className="market-row" key={j.id ?? i}><b>{j.symbol}</b><span>{j.side}</span><span>{money(j.entry_price)}</span><span>{j.status}</span></div>)}{!journal.length && <div className="empty">No journal entries yet.</div>}</section>}

          {page === 'Audit & Security' && me.role === 'admin' && <section className="panel"><div className="panel-head"><div><h3>Security overview</h3><p>Role-based access and platform safeguards</p></div><ShieldCheck /></div><div className="security-list"><div><Check /> Admin-only access approvals</div><div><Check /> User-isolated encrypted API credentials</div><div><Check /> Order execution disabled in this build</div><div><Check /> Audit events for account status changes</div></div></section>}

          {page === 'Settings' && <section className="panel"><h3>Platform settings</h3><p className="muted">Public market data and private API credentials are configured separately. This build does not place orders.</p><div className="setting-line"><span>Market data environment</span><span className="status approved">{marketEnv.toUpperCase()}</span></div><div className="setting-line"><span>Live order execution</span><span className="status suspended">DISABLED</span></div><div className="setting-line"><span>Demo order execution</span><span className="status suspended">DISABLED</span></div><div className="setting-line"><span>Credential encryption</span><span className="status approved">FERNET</span></div></section>}
        </>}

        <footer>DELTA AI TERMINAL <span>·</span> MARKET DATA SUBJECT TO EXCHANGE AVAILABILITY <span>·</span> NOT FINANCIAL ADVICE</footer>
      </div>
    </main>
  </div>
}
