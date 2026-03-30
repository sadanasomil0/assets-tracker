import React, { useState, useEffect } from 'react'
import { View, Text, TextInput, TouchableOpacity, StyleSheet, ScrollView, Alert } from 'react-native'
import { NativeStackNavigationProp } from '@react-navigation/native-stack'

type RootStackParamList = {
  Dashboard: undefined
  AddAsset: undefined
}

type Props = {
  navigation: NativeStackNavigationProp<RootStackParamList, 'AddAsset'>
}

interface AvailableAssets {
  commodities: string[]
  stocks:      string[]
  crypto:      string[]
  all:         string[]
}

const API_URL = process.env.EXPO_PUBLIC_API_URL || 'http://localhost:8000'

export default function AddAssetScreen({ navigation }: Props) {
  const [name, setName] = useState('')
  const [minPrice, setMinPrice] = useState('')
  const [maxPrice, setMaxPrice] = useState('')
  const [available, setAvailable] = useState<AvailableAssets>({
    commodities: [],
    stocks:      [],
    crypto:      [],
    all:         [],
  })

  useEffect(() => {
    fetch(`${API_URL}/assets/available`)
      .then(res => res.json())
      .then((data: AvailableAssets) => setAvailable(data))
      .catch(err => console.error('Failed to load available assets:', err))
  }, [])

  const handleSubmit = async () => {
    if (!name) {
      Alert.alert('Error', 'Please select an asset.')
      return
    }
    const min = parseFloat(minPrice)
    const max = parseFloat(maxPrice)
    if (isNaN(min) || isNaN(max) || min >= max) {
      Alert.alert('Error', 'Min price must be a number less than Max price.')
      return
    }

    try {
      const res = await fetch(`${API_URL}/assets`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, min_price: min, max_price: max }),
      })

      if (res.ok) {
        navigation.goBack()
      } else {
        const err = await res.json()
        Alert.alert('Error', err.detail || 'Failed to add asset.')
      }
    } catch {
      Alert.alert('Error', 'Network error — is the backend running?')
    }
  }

  const AssetChipGroup = ({ label, items }: { label: string; items: string[] }) => {
    if (items.length === 0) return null
    return (
      <>
        <Text style={styles.groupLabel}>{label}</Text>
        <View style={styles.assetGrid}>
          {items.map(a => (
            <TouchableOpacity
              key={a}
              style={[styles.assetChip, name === a && styles.assetChipSelected]}
              onPress={() => setName(a)}
            >
              <Text style={[styles.assetChipText, name === a && styles.assetChipTextSelected]}>{a}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </>
    )
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.label}>Select Asset</Text>

      <AssetChipGroup label="₿ Crypto"           items={available.crypto} />
      <AssetChipGroup label="📦 Commodities"     items={available.commodities} />
      <AssetChipGroup label="📊 Stocks & Indices" items={available.stocks} />

      {name !== '' && (
        <View style={styles.selectedBadge}>
          <Text style={styles.selectedText}>Selected: {name}</Text>
        </View>
      )}

      <Text style={styles.label}>Min Price (USD)</Text>
      <TextInput
        style={styles.input}
        placeholder="e.g. 80000"
        placeholderTextColor="#64748b"
        keyboardType="numeric"
        value={minPrice}
        onChangeText={setMinPrice}
      />

      <Text style={styles.label}>Max Price (USD)</Text>
      <TextInput
        style={styles.input}
        placeholder="e.g. 90000"
        placeholderTextColor="#64748b"
        keyboardType="numeric"
        value={maxPrice}
        onChangeText={setMaxPrice}
      />

      <TouchableOpacity
        style={[styles.submitBtn, !name && styles.submitBtnDisabled]}
        onPress={handleSubmit}
        disabled={!name}
      >
        <Text style={styles.submitBtnText}>Add Asset</Text>
      </TouchableOpacity>
    </ScrollView>
  )
}

const styles = StyleSheet.create({
  container:              { flex: 1, backgroundColor: '#0f172a' },
  content:                { padding: 16, paddingBottom: 40 },
  label:                  { color: '#f1f5f9', fontSize: 16, fontWeight: '600', marginBottom: 8, marginTop: 20 },
  groupLabel:             { color: '#94a3b8', fontSize: 13, textTransform: 'uppercase', letterSpacing: 0.5, marginTop: 14, marginBottom: 8 },
  assetGrid:              { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  assetChip:              { backgroundColor: '#1e293b', paddingHorizontal: 14, paddingVertical: 8, borderRadius: 8, borderWidth: 1, borderColor: '#334155' },
  assetChipSelected:      { backgroundColor: '#3b82f6', borderColor: '#3b82f6' },
  assetChipText:          { color: '#94a3b8', fontSize: 14 },
  assetChipTextSelected:  { color: '#fff', fontWeight: '700' },
  selectedBadge:          { marginTop: 12, backgroundColor: '#1e3a5f', borderRadius: 8, padding: 10, borderLeftWidth: 3, borderLeftColor: '#3b82f6' },
  selectedText:           { color: '#93c5fd', fontWeight: '600' },
  input:                  { backgroundColor: '#1e293b', borderWidth: 1, borderColor: '#334155', borderRadius: 8, padding: 14, color: '#f1f5f9', fontSize: 16 },
  submitBtn:              { backgroundColor: '#3b82f6', padding: 16, borderRadius: 8, alignItems: 'center', marginTop: 28 },
  submitBtnDisabled:      { opacity: 0.4 },
  submitBtnText:          { color: '#fff', fontWeight: '600', fontSize: 16 },
})
