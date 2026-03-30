import React, { useState, useEffect } from 'react'
import { View, Text, FlatList, StyleSheet, TouchableOpacity } from 'react-native'

interface AlertEvent {
  asset_name: string
  price: number
  min_price: number
  max_price: number
  timestamp: string
}

const API_URL = process.env.EXPO_PUBLIC_API_URL || 'http://localhost:8000'

export default function AlertsScreen() {
  const [alerts, setAlerts] = useState<AlertEvent[]>([])

  useEffect(() => {
    // Fetch existing history from REST on mount
    fetch(`${API_URL}/history`)
      .then(res => res.json())
      .then((data: AlertEvent[]) => setAlerts(data.slice(0, 50)))
      .catch(console.error)

    let ws: WebSocket | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null

    const connect = () => {
      ws = new WebSocket(`${API_URL.replace('http', 'ws')}/ws`)

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data)
          if (msg.type === 'alert') {
            setAlerts((prev: AlertEvent[]) => [msg.data as AlertEvent, ...prev].slice(0, 50))
          }
          // Ignore snapshot and price_update on this screen
        } catch {}
      }

      ws.onclose = () => {
        reconnectTimer = setTimeout(connect, 3000)
      }

      ws.onerror = () => {
        ws?.close()
      }
    }

    connect()

    return () => {
      // Clean up both WS and any pending reconnect timer
      if (reconnectTimer) clearTimeout(reconnectTimer)
      ws?.close()
    }
  }, [])

  const formatPrice = (price: number) =>
    `$${price.toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: price < 1 ? 6 : 2,
    })}`

  const renderItem = ({ item }: { item: AlertEvent }) => (
    <View style={styles.alertItem}>
      <Text style={styles.alertIcon}>🔔</Text>
      <View style={styles.alertContent}>
        <Text style={styles.alertTitle}>{item.asset_name} entered range</Text>
        <Text style={styles.alertMeta}>
          Price: {formatPrice(item.price)}
          {' | '}Range: {formatPrice(item.min_price)} – {formatPrice(item.max_price)}
        </Text>
        <Text style={styles.alertTime}>{new Date(item.timestamp).toLocaleString()}</Text>
      </View>
    </View>
  )

  return (
    <View style={styles.container}>
      {alerts.length > 0 && (
        <View style={styles.countBar}>
          <Text style={styles.countText}>{alerts.length} alert{alerts.length !== 1 ? 's' : ''} recorded</Text>
        </View>
      )}
      <FlatList
        data={alerts}
        keyExtractor={(_: AlertEvent, i: number) => i.toString()}
        renderItem={renderItem}
        contentContainerStyle={styles.list}
        ListEmptyComponent={
          <View style={styles.emptyWrap}>
            <Text style={styles.emptyIcon}>📭</Text>
            <Text style={styles.empty}>No alerts yet</Text>
            <Text style={styles.emptyHint}>Alerts appear here when prices enter your target ranges</Text>
          </View>
        }
      />
    </View>
  )
}

const styles = StyleSheet.create({
  container:   { flex: 1, backgroundColor: '#0f172a' },
  countBar:    { backgroundColor: '#1e293b', padding: 10, alignItems: 'center' },
  countText:   { color: '#94a3b8', fontSize: 13 },
  list:        { padding: 16 },
  alertItem:   { flexDirection: 'row', backgroundColor: '#1e293b', borderRadius: 12, padding: 16, marginBottom: 12 },
  alertIcon:   { fontSize: 24, marginRight: 12 },
  alertContent:{ flex: 1 },
  alertTitle:  { fontSize: 16, fontWeight: '600', color: '#f1f5f9', marginBottom: 4 },
  alertMeta:   { fontSize: 14, color: '#94a3b8' },
  alertTime:   { fontSize: 12, color: '#64748b', marginTop: 4 },
  emptyWrap:   { alignItems: 'center', marginTop: 60 },
  emptyIcon:   { fontSize: 40, marginBottom: 12 },
  empty:       { color: '#94a3b8', textAlign: 'center', fontSize: 16, fontWeight: '600' },
  emptyHint:   { color: '#64748b', textAlign: 'center', fontSize: 13, marginTop: 8, paddingHorizontal: 32 },
})
