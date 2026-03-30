import React from 'react'
import { StatusBar } from 'expo-status-bar'
import { NavigationContainer } from '@react-navigation/native'
import { createNativeStackNavigator } from '@react-navigation/native-stack'
import DashboardScreen from './screens/DashboardScreen'
import AddAssetScreen from './screens/AddAssetScreen'
import AlertsScreen from './screens/AlertsScreen'

const Stack = createNativeStackNavigator()

export default function App() {
  return (
    <NavigationContainer>
      <StatusBar style="light" />
      <Stack.Navigator
        initialRouteName="Dashboard"
        screenOptions={{
          headerStyle: { backgroundColor: '#1e293b' },
          headerTintColor: '#f1f5f9',
          headerTitleStyle: { fontWeight: '600' },
          contentStyle: { backgroundColor: '#0f172a' },
        }}
      >
        <Stack.Screen 
          name="Dashboard" 
          component={DashboardScreen}
          options={{ title: 'Price Alerts' }}
        />
        <Stack.Screen 
          name="AddAsset" 
          component={AddAssetScreen}
          options={{ title: 'Add Asset' }}
        />
        <Stack.Screen 
          name="Alerts" 
          component={AlertsScreen}
          options={{ title: 'Alert History' }}
        />
      </Stack.Navigator>
    </NavigationContainer>
  )
}
