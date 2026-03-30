'use client'

import { useState, useEffect, useCallback } from 'react'

interface Asset {
  name: string
  min_price: number
  max_price: number
  state: 'OUTSIDE' | 'INSIDE'
  last_price: number | null
  last_alert_time: string | null
}

interface AlertEvent {
  asset_name: string
  price: number
  min_price: number
  max_price: number
  timestamp: string
}

interface AvailableAssets {
  commodities: string[]
  stocks: string[]
  crypto: string[]
  all: string[]
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export default function Dashboard() {
  const [assets, setAssets] = useState<Asset[]>([])
  const [prices, setPrices] = useState<Record<string, number>>({})
  const [alerts, setAlerts] = useState<AlertEvent[]>([])
  const [available, setAvailable] = useState<AvailableAssets>({
    commodities: [],
    stocks: [],
    crypto: [],
    all: [],
  })
  const [newAsset, setNewAsset] = useState({ name: '', min_price: '', max_price: '' })
  const [connected, setConnected] = useState(false)
  const [addError, setAddError] = useState<string | null>(null)
  const [addSuccess, setAddSuccess] = useState(false)

  const fetchAssets = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/assets`)
      if (res.ok) {
        const data = await res.json()
        setAssets(data)
        // Populate prices map from last_price field
        setPrices(prev => {
          const updated = { ...prev }
          for (const a of data as Asset[]) {
            if (a.last_price != null) updated[a.name] = a.last_price
          }
          return updated
        })
      }
    } catch (err) {
      console.error('Failed to fetch assets:', err)
    }
  }, [])

  const fetchAvailable = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/assets/available`)
      if (res.ok) {
        const data = await res.json()
        setAvailable(data)
      }
    } catch (err) {
      console.error('Failed to fetch available assets:', err)
    }
  }, [])

  const fetchHistory = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/history`)
      if (res.ok) {
        const data: AlertEvent[] = await res.json()
        setAlerts(data.slice(0, 50))
      }
    } catch (err) {
      console.error('Failed to fetch history:', err)
    }
  }, [])

  useEffect(() => {
    fetchAssets()
    fetchAvailable()
    fetchHistory()

    let ws: WebSocket | null = null
    let reconnectTimer: NodeJS.Timeout

    const connect = () => {
      ws = new WebSocket(`${API_URL.replace('http', 'ws')}/ws`)

      ws.onopen = () => {
        setConnected(true)
        console.log('WebSocket connected')
      }

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data)

          if (msg.type === 'snapshot') {
            // Initial state snapshot sent by backend on connect
            const snap = msg.data as Asset[]
            setAssets(snap)
            setPrices(prev => {
              const updated = { ...prev }
              for (const a of snap) {
                if (a.last_price != null) updated[a.name] = a.last_price
              }
              return updated
            })
          } else if (msg.type === 'price_update') {
            setPrices(prev => ({ ...prev, [msg.data.name]: msg.data.price }))
          } else if (msg.type === 'alert') {
            setAlerts(prev => [msg.data as AlertEvent, ...prev].slice(0, 50))
          }
        } catch (err) {
          console.error('Failed to parse WS message:', err)
        }
      }

      ws.onclose = () => {
        setConnected(false)
        reconnectTimer = setTimeout(connect, 3000)
      }

      ws.onerror = () => {
        ws?.close()
      }
    }

    connect()

    return () => {
      clearTimeout(reconnectTimer)
      ws?.close()
    }
  }, [fetchAssets, fetchAvailable, fetchHistory])

  const handleAddAsset = async (e: React.FormEvent) => {
    e.preventDefault()
    setAddError(null)
    setAddSuccess(false)

    if (!newAsset.name || !newAsset.min_price || !newAsset.max_price) {
      setAddError('Please fill in all fields.')
      return
    }

    const min = parseFloat(newAsset.min_price)
    const max = parseFloat(newAsset.max_price)
    if (isNaN(min) || isNaN(max) || min >= max) {
      setAddError('Min price must be a number less than Max price.')
      return
    }

    try {
      const res = await fetch(`${API_URL}/assets`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newAsset.name, min_price: min, max_price: max }),
      })

      if (res.ok) {
        setNewAsset({ name: '', min_price: '', max_price: '' })
        setAddSuccess(true)
        setTimeout(() => setAddSuccess(false), 3000)
        fetchAssets()
      } else {
        const err = await res.json()
        setAddError(err.detail || 'Failed to add asset.')
      }
    } catch (err) {
      setAddError('Network error — is the backend running?')
    }
  }

  const handleRemoveAsset = async (name: string) => {
    try {
      const res = await fetch(`${API_URL}/assets/${name}`, { method: 'DELETE' })
      if (res.ok) fetchAssets()
    } catch (err) {
      console.error('Failed to remove asset:', err)
    }
  }

  return (
    <div className="container">
      <header>
        <h1>Price Alert Dashboard</h1>
        <div className="status-badge">
          <div className="status-dot" style={{ background: connected ? '#10b981' : '#ef4444' }} />
          {connected ? 'Live' : 'Disconnected'}
        </div>
      </header>

      <form className="add-form" onSubmit={handleAddAsset}>
        <div className="form-title">Add Asset to Track</div>
        <div className="form-row">
          <div className="form-group">
            <label>Asset</label>
            <select
              value={newAsset.name}
              onChange={e => setNewAsset({ ...newAsset, name: e.target.value })}
            >
              <option value="">Select asset...</option>
              <optgroup label="₿ Crypto">
                {available.crypto.map(a => <option key={a} value={a}>{a}</option>)}
              </optgroup>
              <optgroup label="📦 Commodities">
                {available.commodities.map(a => <option key={a} value={a}>{a}</option>)}
              </optgroup>
              <optgroup label="📊 Stocks & Indices">
                {available.stocks.map(a => <option key={a} value={a}>{a}</option>)}
              </optgroup>
            </select>
          </div>
          <div className="form-group">
            <label>Min Price</label>
            <input
              type="number"
              step="any"
              placeholder="e.g. 80000"
              value={newAsset.min_price}
              onChange={e => setNewAsset({ ...newAsset, min_price: e.target.value })}
            />
          </div>
          <div className="form-group">
            <label>Max Price</label>
            <input
              type="number"
              step="any"
              placeholder="e.g. 90000"
              value={newAsset.max_price}
              onChange={e => setNewAsset({ ...newAsset, max_price: e.target.value })}
            />
          </div>
          <button type="submit">Add</button>
        </div>
        {addError && <div className="form-error">⚠️ {addError}</div>}
        {addSuccess && <div className="form-success">✅ Asset added successfully!</div>}
      </form>

      <div className="grid">
        {assets.length === 0 ? (
          <div className="card empty-state">
            No assets being tracked. Add one above!
          </div>
        ) : (
          assets.map(asset => (
            <div key={asset.name} className={`card ${asset.state === 'INSIDE' ? 'card-in-range' : ''}`}>
              <div className="card-header">
                <span className="asset-name">{asset.name}</span>
                <button className="remove" onClick={() => handleRemoveAsset(asset.name)}>
                  Remove
                </button>
              </div>
              <div className="asset-price">
                {prices[asset.name] != null
                  ? `$${prices[asset.name].toLocaleString(undefined, {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: prices[asset.name] < 1 ? 6 : 2,
                    })}`
                  : '—'}
              </div>
              <div className="range-info">
                Range: ${asset.min_price.toLocaleString()} – ${asset.max_price.toLocaleString()}
              </div>
              <div style={{ marginTop: '0.5rem' }}>
                <span className={`state-indicator state-${asset.state.toLowerCase()}`}>
                  {asset.state === 'INSIDE' ? '✓ In Range' : '○ Outside Range'}
                </span>
              </div>
            </div>
          ))
        )}
      </div>

      <div className="alerts-section">
        <div className="section-title">🔔 Recent Alerts</div>
        {alerts.length === 0 ? (
          <div className="empty-state">No alerts yet. Prices will trigger when they enter your target range.</div>
        ) : (
          alerts.map((alert, i) => (
            <div key={i} className="alert-item">
              <span className="alert-icon">🔔</span>
              <div className="alert-details">
                <div className="alert-title">{alert.asset_name} entered range</div>
                <div className="alert-meta">
                  Price: ${alert.price.toLocaleString(undefined, { maximumFractionDigits: 4 })} &nbsp;|&nbsp;
                  Range: ${alert.min_price.toLocaleString()} – ${alert.max_price.toLocaleString()} &nbsp;|&nbsp;
                  {new Date(alert.timestamp).toLocaleString()}
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
