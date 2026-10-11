import React, {useCallback, useEffect, useState} from 'react';
import {
  ActivityIndicator,
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

type Device = {id: string; name: string; connected: boolean};
type State = {paused: boolean; connected: number; devices: Device[]};
const API = 'http://127.0.0.1:48501/api';

async function call(path: string, options?: RequestInit) {
  const response = await fetch(`${API}${path}`, {
    headers: {'Content-Type': 'application/json'},
    ...options,
  });
  if (!response.ok) {
    throw new Error(`ClipBridge control request failed (${response.status})`);
  }
  return response.json();
}

export default function App() {
  const [state, setState] = useState<State | null>(null);
  const [error, setError] = useState('');

  const refresh = useCallback(async () => {
    try {
      setState(await call('/state'));
      setError('');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not reach ClipBridge.');
    }
  }, []);

  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 1500);
    return () => clearInterval(timer);
  }, [refresh]);

  const action = async (path: string, body?: object) => {
    try {
      await call(path, {method: 'POST', body: JSON.stringify(body ?? {})});
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'ClipBridge action failed.');
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.page}>
        <View style={styles.header}>
          <View>
            <Text style={styles.eyebrow}>CLIPBOARD SYNC</Text>
            <Text style={styles.title}>ClipBridge</Text>
          </View>
          <View style={[styles.dot, state?.connected ? styles.green : styles.amber]} />
        </View>
        <View style={styles.hero}>
          <Text style={styles.heroLabel}>CONNECTION</Text>
          <Text style={styles.heroTitle}>
            {state?.connected ? 'Connected' : 'Waiting for phone'}
          </Text>
          <Text style={styles.muted}>
            {state?.connected
              ? 'Your clipboard is syncing securely on this network.'
              : 'Pair a phone to start syncing clipboard text.'}
          </Text>
        </View>
        {error ? <Text style={styles.error}>{error}</Text> : null}
        <View style={styles.actions}>
          <Pressable style={styles.primary} onPress={() => action('/pair')}>
            <Text style={styles.primaryText}>Pair new phone</Text>
          </Pressable>
          <Pressable style={styles.secondary} onPress={() => action('/pause')}>
            <Text style={styles.secondaryText}>{state?.paused ? 'Resume sync' : 'Pause sync'}</Text>
          </Pressable>
        </View>
        <Text style={styles.section}>PAIRED DEVICES</Text>
        {state?.devices.length ? state.devices.map(device => (
          <View style={styles.device} key={device.id}>
            <View style={styles.deviceText}>
              <Text style={styles.deviceName}>{device.name}</Text>
              <Text style={styles.muted}>{device.connected ? 'Connected now' : 'Not connected'}</Text>
            </View>
            <Pressable style={styles.disconnect} onPress={() => action('/disconnect', {device_id: device.id})}>
              <Text style={styles.disconnectText}>Disconnect</Text>
            </Pressable>
          </View>
        )) : <Text style={styles.muted}>No paired phones.</Text>}
        {!state && !error ? <ActivityIndicator color="#6ea8fe" /> : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: {flex: 1, backgroundColor: '#09111f'},
  page: {width: 820, maxWidth: '100%', alignSelf: 'center', padding: 42, gap: 22},
  header: {flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center'},
  eyebrow: {color: '#6ea8fe', fontSize: 12, fontWeight: '800', letterSpacing: 2},
  title: {color: '#f4f7fb', fontSize: 36, fontWeight: '800', marginTop: 6},
  dot: {width: 16, height: 16, borderRadius: 8},
  green: {backgroundColor: '#40d98a'},
  amber: {backgroundColor: '#f5b85b'},
  hero: {backgroundColor: '#121f33', borderRadius: 22, padding: 28, borderWidth: 1, borderColor: '#203550'},
  heroLabel: {color: '#8194ad', fontSize: 12, fontWeight: '800', letterSpacing: 1.5},
  heroTitle: {color: '#f4f7fb', fontSize: 30, fontWeight: '800', marginTop: 10},
  muted: {color: '#9badc2', fontSize: 15, marginTop: 7},
  error: {color: '#ff9a9a', backgroundColor: '#3a1c25', padding: 14, borderRadius: 10},
  actions: {flexDirection: 'row', gap: 12},
  primary: {backgroundColor: '#3478f6', borderRadius: 12, paddingVertical: 14, paddingHorizontal: 22},
  primaryText: {color: 'white', fontWeight: '800', fontSize: 15},
  secondary: {backgroundColor: '#17263b', borderRadius: 12, paddingVertical: 14, paddingHorizontal: 22},
  secondaryText: {color: '#dbe8f8', fontWeight: '700', fontSize: 15},
  section: {color: '#8194ad', fontWeight: '800', letterSpacing: 1.5, marginTop: 12},
  device: {backgroundColor: '#101c2d', borderRadius: 15, padding: 18, flexDirection: 'row', alignItems: 'center'},
  deviceText: {flex: 1},
  deviceName: {color: '#f4f7fb', fontSize: 17, fontWeight: '700'},
  disconnect: {borderWidth: 1, borderColor: '#9b4c5d', borderRadius: 9, paddingVertical: 9, paddingHorizontal: 13},
  disconnectText: {color: '#ff9da9', fontWeight: '700'},
});
