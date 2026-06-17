import React, { useState, useEffect } from 'react';
import { StyleSheet, Text, View, TextInput, TouchableOpacity, ScrollView, Alert } from 'react-native';
import * as Location from 'expo-location';
import { Accelerometer } from 'expo-sensors';
import * as TaskManager from 'expo-task-manager';
import AsyncStorage from '@react-native-async-storage/async-storage';

const LOCATION_TASK_NAME = 'background-location-task';
const DEVICE_ID_KEY = 'gps_tracker_device_id';
const GPS_SEND_INTERVAL_MS = 2000;

// Variable global para la URL en el TaskManager
let globalServerUrl = '';
let globalParticipante = null;
let globalDeviceId = null;
let globalLocationSubscription = null; // Guardar la suscripcion para detenerla despues
let globalTimer = null; // Forzar envio cada segundo
let lastKnownLocation = null;
let globalSendingGps = false;
let globalLastGpsSentMs = 0;

// Función compartida para enviar GPS
const enviarGps = async (loc) => {
  if (!globalServerUrl || !globalParticipante) return;
  const nowMs = Date.now();
  if (globalSendingGps || nowMs - globalLastGpsSentMs < GPS_SEND_INTERVAL_MS) return;

  globalSendingGps = true;
  globalLastGpsSentMs = nowMs;

  try {
    await fetch(`${globalServerUrl}/gps`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        latitude: loc.coords.latitude,
        longitude: loc.coords.longitude,
        accuracy: loc.coords.accuracy,
        altitude: loc.coords.altitude,
        altitude_accuracy: loc.coords.altitudeAccuracy,
        heading: loc.coords.heading,
        speed_mps: loc.coords.speed,
        speed_kmh: loc.coords.speed ? loc.coords.speed * 3.6 : null,
        speed_source: 'gps_sensor',
        device_id: globalDeviceId,
        device_label: `App-${globalDeviceId.substring(0,6)}`,
        client_timestamp_ms: nowMs
      })
    });
  } catch (e) {
    console.error("Error enviando GPS:", e);
  } finally {
    globalSendingGps = false;
  }
};

// Definir la tarea en segundo plano fuera de los componentes de React
TaskManager.defineTask(LOCATION_TASK_NAME, async ({ data, error }) => {
  if (error) {
    console.error("Error en background task:", error);
    return;
  }
  if (data) {
    const { locations } = data;
    if (locations && locations.length > 0) {
      await enviarGps(locations[locations.length - 1]);
    }
  }
});

export default function App() {
  const [serverUrl, setServerUrl] = useState('https://TU-TUNEL.trycloudflare.com');
  const [participante, setParticipante] = useState(null);
  const [activo, setActivo] = useState(false);
  const [deviceId, setDeviceId] = useState('');
  const [statusMsg, setStatusMsg] = useState('Esperando URL y Registro...');
  
  // Datos visuales
  const [location, setLocation] = useState(null);
  const [accelData, setAccelData] = useState({ x: 0, y: 0, z: 0 });

  useEffect(() => {
    inicializarDevice();
  }, []);

  const inicializarDevice = async () => {
    let id = await AsyncStorage.getItem(DEVICE_ID_KEY);
    if (!id) {
      id = "app-" + Date.now().toString(36) + Math.random().toString(36).substring(2,8);
      await AsyncStorage.setItem(DEVICE_ID_KEY, id);
    }
    setDeviceId(id);
    globalDeviceId = id;
  };

  const registrar = async () => {
    if (!serverUrl.startsWith('http')) {
      Alert.alert('Error', 'Ingresa una URL válida (http/https)');
      return;
    }
    try {
      setStatusMsg('Registrando...');
      const res = await fetch(`${serverUrl}/registrar`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ device_id: deviceId, device_label: `App-${deviceId.substring(0,6)}` })
      });
      const data = await res.json();
      if (data.status === 'ok') {
        setParticipante(data.participante);
        globalParticipante = data.participante;
        globalServerUrl = serverUrl;
        setStatusMsg(`Registrado como: ${data.participante}`);
      } else {
        setStatusMsg(`Error: ${data.msg}`);
      }
    } catch (e) {
      setStatusMsg('Error de red al registrar. Revisa la URL.');
    }
  };

  const iniciarCaptura = async () => {
    if (!participante) {
      Alert.alert('Aviso', 'Primero debes registrarte en el servidor.');
      return;
    }

    // Pedir permisos
    const { status: fgStatus } = await Location.requestForegroundPermissionsAsync();
    if (fgStatus !== 'granted') {
      Alert.alert('Error', 'Se requiere permiso de ubicación en primer plano.');
      return;
    }

    try {
      const { status: bgStatus } = await Location.requestBackgroundPermissionsAsync();
      if (bgStatus !== 'granted') {
        Alert.alert('Aviso', 'Permiso en segundo plano denegado. Solo funcionará con la app abierta.');
      }
    } catch (e) {
      console.log('Expo Go en iOS no permite pedir permisos de segundo plano.');
    }

    setActivo(true);
    setStatusMsg('Captura iniciada (Fondo y Primer plano)');

    // Iniciar Acelerómetro visual
    Accelerometer.setUpdateInterval(500);
    Accelerometer.addListener(data => {
      setAccelData(data);
    });

    // Iniciar GPS en segundo plano
    try {
      await Location.startLocationUpdatesAsync(LOCATION_TASK_NAME, {
        accuracy: Location.Accuracy.BestForNavigation,
        timeInterval: 2000,
        distanceInterval: 0,
        showsBackgroundLocationIndicator: true,
        foregroundService: {
          notificationTitle: "GPS Tracker Activo",
          notificationBody: "Enviando ubicación al servidor...",
          notificationColor: "#2563eb",
        }
      });
    } catch (error) {
      console.log("Aviso: Segundo plano no disponible en Expo Go iOS. Corriendo silenciosamente en primer plano.");
    }

    globalLocationSubscription = await Location.watchPositionAsync({
      accuracy: Location.Accuracy.BestForNavigation,
      timeInterval: 2000,
      distanceInterval: 0
    }, (loc) => {
      setLocation(loc);
      lastKnownLocation = loc;
    });

    // BUCLE FORZADO: intenta enviar seguido, pero enviarGps limita a 2s
    // usando la ultima ubicacion conocida. Esto soluciona el problema de
    // iOS/Android mandando datos cada 5-10 segundos cuando estas quieto.
    if (globalTimer) clearInterval(globalTimer);
    globalTimer = setInterval(() => {
      if (lastKnownLocation) {
        enviarGps(lastKnownLocation);
      }
    }, 250);
  };

  const detenerCaptura = async () => {
    setActivo(false);
    setStatusMsg('Captura detenida.');
    Accelerometer.removeAllListeners();
    
    // Detener el envio forzado (timer)
    if (globalTimer) {
      clearInterval(globalTimer);
      globalTimer = null;
    }
    
    // Detener el envio en primer plano
    if (globalLocationSubscription) {
      globalLocationSubscription.remove();
      globalLocationSubscription = null;
    }
    
    // Detener la tarea en segundo plano
    try {
      await Location.stopLocationUpdatesAsync(LOCATION_TASK_NAME);
    } catch (e) {
      console.log("El segundo plano ya estaba detenido o no soportado.");
    }
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={{paddingBottom: 50}}>
      <Text style={styles.title}>GPS Tracker App</Text>
      <Text style={styles.subtitle}>Conexión Nativa (Segundo Plano Real)</Text>

      <View style={styles.card}>
        <Text style={styles.label}>URL del Servidor (Cloudflare)</Text>
        <TextInput 
          style={styles.input}
          value={serverUrl}
          onChangeText={setServerUrl}
          placeholder="https://...trycloudflare.com"
          autoCapitalize="none"
          editable={!activo}
        />
        <TouchableOpacity style={[styles.btn, styles.btnSecondary]} onPress={registrar} disabled={activo}>
          <Text style={styles.btnText}>Conectar y Registrar</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.statusBox}>
        <Text style={styles.statusText}>{statusMsg}</Text>
      </View>

      {!activo ? (
        <TouchableOpacity style={styles.btn} onPress={iniciarCaptura}>
          <Text style={styles.btnText}>Iniciar Captura en Segundo Plano</Text>
        </TouchableOpacity>
      ) : (
        <TouchableOpacity style={[styles.btn, styles.btnDanger]} onPress={detenerCaptura}>
          <Text style={styles.btnText}>Detener Captura</Text>
        </TouchableOpacity>
      )}

      <View style={styles.grid}>
        <View style={styles.cardHalf}>
          <Text style={styles.label}>Velocidad</Text>
          <Text style={styles.value}>
            {location && location.coords.speed && location.coords.speed > 0 
              ? (location.coords.speed * 3.6).toFixed(2) 
              : '0.00'} km/h
          </Text>
        </View>

        <View style={styles.cardHalf}>
          <Text style={styles.label}>Precisión</Text>
          <Text style={styles.value}>
            {location ? location.coords.accuracy.toFixed(0) : '--'} m
          </Text>
        </View>

        <View style={styles.cardFull}>
          <Text style={styles.label}>Acelerómetro (G)</Text>
          <Text style={styles.small}>X: {accelData.x.toFixed(3)}</Text>
          <Text style={styles.small}>Y: {accelData.y.toFixed(3)}</Text>
          <Text style={styles.small}>Z: {accelData.z.toFixed(3)}</Text>
        </View>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f8fafc',
    padding: 20,
    paddingTop: 60,
  },
  title: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#0f172a',
    marginBottom: 4,
  },
  subtitle: {
    fontSize: 14,
    color: '#475569',
    marginBottom: 24,
  },
  card: {
    backgroundColor: 'white',
    padding: 16,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#e2e8f0',
    marginBottom: 16,
  },
  label: {
    fontSize: 12,
    color: '#64748b',
    marginBottom: 8,
    fontWeight: '600',
    textTransform: 'uppercase',
  },
  input: {
    backgroundColor: '#f1f5f9',
    padding: 12,
    borderRadius: 8,
    fontSize: 16,
    color: '#0f172a',
    marginBottom: 12,
  },
  btn: {
    backgroundColor: '#2563eb',
    padding: 16,
    borderRadius: 10,
    alignItems: 'center',
    marginBottom: 12,
  },
  btnSecondary: {
    backgroundColor: '#0f766e',
    marginBottom: 0,
  },
  btnDanger: {
    backgroundColor: '#ef4444',
  },
  btnText: {
    color: 'white',
    fontSize: 16,
    fontWeight: 'bold',
  },
  statusBox: {
    backgroundColor: '#e0e7ff',
    padding: 16,
    borderRadius: 10,
    marginBottom: 20,
    borderWidth: 1,
    borderColor: '#c7d2fe',
  },
  statusText: {
    color: '#3730a3',
    fontWeight: '600',
    textAlign: 'center',
  },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
  },
  cardHalf: {
    backgroundColor: 'white',
    padding: 16,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#e2e8f0',
    width: '48%',
    marginBottom: 16,
  },
  cardFull: {
    backgroundColor: 'white',
    padding: 16,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#e2e8f0',
    width: '100%',
    marginBottom: 16,
  },
  value: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#0f172a',
  },
  small: {
    fontSize: 14,
    color: '#334155',
    marginBottom: 4,
    fontFamily: 'monospace',
  }
});
