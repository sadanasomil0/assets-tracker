import React, { useState, useEffect, useCallback } from 'react'
import { View, Text, FlatList, TouchableOpacity, StyleSheet, RefreshControl, Alert } from 'react-native'
import { NativeStackNavigationProp } from '@react-navigation/native-stack'
import { useFocusEffect } from '@react-navigation/native'

type RootStackParamList = {
  Dashboard: undefined
  AddAsset: undefined
  Alerts: undefined
}

type Props = {
  navigation: NativeStackNavigationProp<RootStackParamList, 'Dashboard'>
}

interface Asset {
  name: string
  min_price: number
  max_price: number
  state: 'OUTSIDE' | 'INSIDE'
  last_price: number | null
}

interface AlertEvent {
  asset_name: string
  price: number
  min_price: number
  max_price: number
  timestamp: string
}

// 📝 Change this to your server's local IP when running on a real device.
// Use http://localhost:8000 for emulators / web preview.
const API_URL = process.env.EXPO_PUBLIC_API_URL || 'http://localhost:8000'

export default function DashboardScreen({ navigation }: Props) {
  const [assets, setAssets] = useState<Asset[]>([])
  const [prices, setPrices] = useState<Record<string, number>>({})
  const [recentAlerts, setRecentAlerts] = useState<AlertEvent[]>([])
  const [refreshing, setRefreshing] = useState(false)
  const [connected, setConnected] = useState(false)

  const fetchAssets = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/assets`)
      if (res.ok) {
        const data: Asset[] = await res.json()
        setAssets(data)
        // Seed prices from last_price so we display something before WS
        setPrices(prev => {
          const updated = { ...prev }
          for (const a of data) {
            if (a.last_price != null) updated[a.name] = a.last_price
          }
          return updated
        })
      }
    } catch (err) {
      console.error('Failed to fetch assets:', err)
    }
  }, [])

  const removeAsset = async (name: string) => {
    try {
      const res = await fetch(`${API_URL}/assets/${name}`, { method: 'DELETE' })
      if (res.ok) {
        fetchAssets()
      } else {
        Alert.alert('Error', `Could not remove ${name}.`)
      }
    } catch (err) {
      Alert.alert('Error', 'Network error — is the backend running?')
    }
  }

  useFocusEffect(
    useCallback(() => {
      fetchAssets()
    }, [fetchAssets])
  )

  useEffect(() => {
    let ws: WebSocket | null = null
    let reconnectTimer: ReturnType<typeof setTimeout>

    const connect = () => {
      ws = new WebSocket(`${API_URL.replace('http', 'ws')}/ws`)

      ws.onopen = () => setConnected(true)

      ws.onclose = () => {
        setConnected(false)
        reconnectTimer = setTimeout(connect, 3000)
      }

      ws.onerror = () => {
        ws?.close()
      }

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data)

          if (msg.type === 'snapshot') {
            // Backend sends current state on connect — hydrate assets & prices
            const snap: Asset[] = msg.data
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
            const ev: AlertEvent = msg.data
            setRecentAlerts(prev => [ev, ...prev].slice(0, 20))
            // Show native alert notification
            Alert.alert(
              `🔔 ${ev.asset_name} Alert!`,
              `Price $${ev.price.toLocaleString()} entered your range ($${ev.min_price.toLocaleString()} – $${ev.max_price.toLocaleString()})`
            )
          }
        } catch {}
      }
    }

    connect()

    return () => {
      clearTimeout(reconnectTimer)
      ws?.close()
    }
  }, [])

  const onRefresh = async () => {
    setRefreshing(true)
    await fetchAssets()
    setRefreshing(false)
  }

  const formatPrice = (price: number) =>
    `$${price.toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: price < 1 ? 6 : 2,
    })}`

  const renderItem = ({ item }: { item: Asset }) => (
    <View style={styles.card}>
      <View style={styles.cardHeader}>
        <Text style={styles.assetName}>{item.name}</Text>
        <TouchableOpacity onPress={() => removeAsset(item.name)}>
          <Text style={styles.removeBtn}>Remove</Text>
        </TouchableOpacity>
      </View>
      <Text style={styles.price}>
        {prices[item.name] != null ? formatPrice(prices[item.name]) : '—'}
      </Text>
      <Text style={styles.range}>
        Range: {formatPrice(item.min_price)} – {formatPrice(item.max_price)}
      </Text>
      <View style={[styles.stateBadge, item.state === 'INSIDE' ? styles.stateInside : styles.stateOutside]}>
        <Text style={styles.stateText}>{item.state === 'INSIDE' ? '✓ In Range' : '○ Outside'}</Text>
      </View>
    </View>
  )

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>📈 Price Alerts</Text>
        <View style={styles.statusRow}>
          <View style={[styles.statusDot, { backgroundColor: connected ? '#10b981' : '#ef4444' }]} />
          <Text style={styles.statusText}>{connected ? 'Live' : 'Reconnecting…'}</Text>
        </View>
      </View>

      {recentAlerts.length > 0 && (
        <View style={styles.alertBanner}>
          <Text style={styles.alertBannerText}>
            🔔 Last alert: {recentAlerts[0].asset_name} @ ${recentAlerts[0].price.toLocaleString()}
          </Text>
        </View>
      )}

      <FlatList
        data={assets}
        keyExtractor={(item) => item.name}
        renderItem={renderItem}
        contentContainerStyle={styles.list}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#3b82f6" />}
        ListEmptyComponent={<Text style={styles.empty}>No assets tracked. Tap "+ Add Asset" to start.</Text>}
      />

      <View style={styles.actions}>
        <TouchableOpacity style={styles.btn} onPress={() => navigation.navigate('AddAsset')}>
          <Text style={styles.btnText}>+ Add Asset</Text>
        </TouchableOpacity>
        <TouchableOpacity style={[styles.btn, styles.btnSecondary]} onPress={() => navigation.navigate('Alerts')}>
          <Text style={styles.btnText}>View Alerts {recentAlerts.length > 0 ? `(${recentAlerts.length})` : ''}</Text>
        </TouchableOpacity>
      </View>
    </View>
  )
}

const styles = StyleSheet.create({
  container:       { flex: 1, backgroundColor: '#0f172a' },
  header:          { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 16 },
  title:           { fontSize: 20, fontWeight: '700', color: '#f1f5f9' },
  statusRow:       { flexDirection: 'row', alignItems: 'center', gap: 6 },
  statusDot:       { width: 8, height: 8, borderRadius: 4 },
  statusText:      { color: '#94a3b8', fontSize: 13 },
  alertBanner:     { backgroundColor: '#1e3a5f', marginHorizontal: 16, marginBottom: 8, padding: 10, borderRadius: 8, borderLeftWidth: 3, borderLeftColor: '#3b82f6' },
  alertBannerText: { color: '#93c5fd', fontSize: 13 },
  list:            { padding: 16, paddingTop: 0 },
  card:            { backgroundColor: '#1e293b', borderRadius: 12, padding: 16, marginBottom: 12 },
  cardHeader:      { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 },
  assetName:       { fontSize: 18, fontWeight: '600', color: '#f1f5f9' },
  removeBtn:       { color: '#dc2626', fontSize: 14 },
  price:           { fontSize: 24, fontWeight: '700', color: '#3b82f6', marginBottom: 4 },
  range:           { color: '#94a3b8', fontSize: 14, marginBottom: 8 },
  stateBadge:      { alignSelf: 'flex-start', paddingHorizontal: 12, paddingVertical: 4, borderRadius: 9999 },
  stateInside:     { backgroundColor: '#065f46' },
  stateOutside:    { backgroundColor: '#374151' },
  stateText:       { color: '#fff', fontSize: 12, fontWeight: '600' },
  empty:           { color: '#94a3b8', textAlign: 'center', marginTop: 40, fontSize: 15 },
  actions:         { flexDirection: 'row', padding: 16, gap: 12 },
  btn:             { flex: 1, backgroundColor: '#3b82f6', padding: 14, borderRadius: 8, alignItems: 'center' },
  btnSecondary:    { backgroundColor: '#1e293b', borderWidth: 1, borderColor: '#334155' },
  btnText:         { color: '#fff', fontWeight: '600', fontSize: 15 },
})
