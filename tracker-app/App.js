import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { StatusBar } from 'expo-status-bar';
import * as Location from 'expo-location';
import { Accelerometer } from 'expo-sensors';
import * as TaskManager from 'expo-task-manager';
import AsyncStorage from '@react-native-async-storage/async-storage';

const LOCATION_TASK_NAME = 'background-location-task';
const DEVICE_ID_KEY = 'gps_tracker_device_id';
const SERVER_URL_KEY = 'gps_tracker_server_url';
const PARTICIPANTE_KEY = 'gps_tracker_participante';
const GPS_SEND_INTERVAL_MS = 2000;
const ACCELERATION_SAMPLE_WINDOW = 3;

let globalServerUrl = '';
let globalParticipante = null;
let globalDeviceId = null;
let globalLastKnownLocation = null;
let globalLocationSubscription = null;
let globalTimer = null;
let globalSendingGps = false;
let globalLastGpsSentMs = 0;
let globalLastPoint = null;
let globalSpeedHistory = [];
let globalAccelData = {
  gx: null,
  gy: null,
  gz: null,
  g_magnitude: null,
  acceleration_mps2: null,
  sensor_timestamp_ms: null,
  supported: false,
  permission_state: 'not_requested',
};

const numOrNull = (value) => (Number.isFinite(value) ? value : null);
const fmt = (value, decimals = 2) => (Number.isFinite(value) ? value.toFixed(decimals) : '--');
const toRad = (deg) => (deg * Math.PI) / 180;

const cleanServerUrl = (value) => value.trim().replace(/\/+$/, '');

const getCheckpointLabel = (checkpoint) => {
  if (!checkpoint) return '--';
  return checkpoint.nombre || `Checkpoint ${checkpoint.id}`;
};

const calculateMagnitude = (x, y, z) => {
  if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) return null;
  return Math.sqrt(x * x + y * y + z * z);
};

const haversineMeters = (lat1, lon1, lat2, lon2) => {
  const earthRadius = 6371000;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(toRad(lat1)) *
      Math.cos(toRad(lat2)) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
  return 2 * earthRadius * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
};

const createDeviceLabel = (deviceId) => {
  const prefix = Platform.OS === 'ios' ? 'iPhone' : Platform.OS === 'android' ? 'Android' : 'App';
  return `${prefix}-${deviceId.slice(0, 8)}`;
};

const calculateSpeed = (loc) => {
  const nowMs = Date.now();
  const lat = loc.coords.latitude;
  const lon = loc.coords.longitude;
  let speedMps = numOrNull(loc.coords.speed);
  let speedSource = Number.isFinite(speedMps) ? 'gps_sensor' : 'none';
  let accelerationMps2 = null;

  if (!Number.isFinite(speedMps) && globalLastPoint) {
    const distance = haversineMeters(globalLastPoint.lat, globalLastPoint.lon, lat, lon);
    const dt = (nowMs - globalLastPoint.timestamp_ms) / 1000;
    if (dt > 0) {
      speedMps = distance / dt;
      speedSource = 'calculated_gps_distance_time';
    }
  }

  if (Number.isFinite(speedMps)) {
    const previousSamplesNeeded = ACCELERATION_SAMPLE_WINDOW - 1;
    if (globalSpeedHistory.length >= previousSamplesNeeded) {
      const reference = globalSpeedHistory[0];
      const dt = (nowMs - reference.timestamp_ms) / 1000;
      if (dt > 0 && Number.isFinite(reference.speed_mps)) {
        accelerationMps2 = (speedMps - reference.speed_mps) / dt;
      }
    }

    globalSpeedHistory.push({ speed_mps: speedMps, timestamp_ms: nowMs });
    while (globalSpeedHistory.length > previousSamplesNeeded) {
      globalSpeedHistory.shift();
    }
  }

  globalLastPoint = { lat, lon, timestamp_ms: nowMs, speed_mps: speedMps };

  return {
    speed_mps: speedMps,
    speed_kmh: Number.isFinite(speedMps) ? speedMps * 3.6 : null,
    speed_source: speedSource,
    acceleration_mps2: accelerationMps2,
  };
};

const hydrateGlobals = async () => {
  if (!globalServerUrl) {
    globalServerUrl = (await AsyncStorage.getItem(SERVER_URL_KEY)) || '';
  }
  if (!globalParticipante) {
    globalParticipante = await AsyncStorage.getItem(PARTICIPANTE_KEY);
  }
  if (!globalDeviceId) {
    globalDeviceId = await AsyncStorage.getItem(DEVICE_ID_KEY);
  }
};

const sendGps = async (loc) => {
  await hydrateGlobals();
  if (!globalServerUrl || !globalParticipante || !globalDeviceId || !loc?.coords) return null;

  const nowMs = Date.now();
  if (globalSendingGps || nowMs - globalLastGpsSentMs < GPS_SEND_INTERVAL_MS) return null;

  globalSendingGps = true;
  globalLastGpsSentMs = nowMs;

  try {
    const speed = calculateSpeed(loc);
    globalAccelData = {
      ...globalAccelData,
      acceleration_mps2: speed.acceleration_mps2,
    };

    const resp = await fetch(`${globalServerUrl}/gps`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        latitude: loc.coords.latitude,
        longitude: loc.coords.longitude,
        accuracy: loc.coords.accuracy,
        altitude: loc.coords.altitude,
        altitude_accuracy: loc.coords.altitudeAccuracy,
        heading: loc.coords.heading,
        speed_mps: speed.speed_mps,
        speed_kmh: speed.speed_kmh,
        speed_source: speed.speed_source,
        accel_gx: globalAccelData.gx,
        accel_gy: globalAccelData.gy,
        accel_gz: globalAccelData.gz,
        accel_g_magnitude: globalAccelData.g_magnitude,
        acceleration_mps2: globalAccelData.acceleration_mps2,
        sensor_timestamp_ms: globalAccelData.sensor_timestamp_ms,
        client_timestamp_ms: nowMs,
        device_id: globalDeviceId,
        device_label: createDeviceLabel(globalDeviceId),
      }),
    });

    const data = await resp.json();
    if (!resp.ok && data.status !== 'limite_participantes') {
      throw new Error(data.msg || `Error del servidor: ${resp.status}`);
    }

    return { data, speed, sentAtMs: nowMs };
  } finally {
    globalSendingGps = false;
  }
};

TaskManager.defineTask(LOCATION_TASK_NAME, async ({ data, error }) => {
  if (error) {
    console.error('Error en background task:', error);
    return;
  }

  const loc = data?.locations?.[data.locations.length - 1];
  if (loc) {
    await sendGps(loc);
  }
});

export default function App() {
  const [serverUrl, setServerUrl] = useState('');
  const [participante, setParticipante] = useState(null);
  const [activo, setActivo] = useState(false);
  const [deviceId, setDeviceId] = useState('');
  const [status, setStatus] = useState({ text: 'Esperando...', tone: 'neutral' });
  const [location, setLocation] = useState(null);
  const [speedInfo, setSpeedInfo] = useState({
    speed_kmh: null,
    speed_mps: null,
    speed_source: 'esperando GPS',
    acceleration_mps2: null,
  });
  const [checkpointInfo, setCheckpointInfo] = useState({
    label: '--',
    distance: null,
  });
  const [accelData, setAccelData] = useState(globalAccelData);
  const accelerometerSubscriptionRef = useRef(null);
  const mountedRef = useRef(true);

  const canRegister = useMemo(() => cleanServerUrl(serverUrl).startsWith('http'), [serverUrl]);

  useEffect(() => {
    mountedRef.current = true;
    initializeDevice();

    return () => {
      mountedRef.current = false;
      stopCapture();
    };
  }, []);

  const setLog = (text, tone = 'neutral') => {
    setStatus({ text, tone });
  };

  const initializeDevice = async () => {
    let id = await AsyncStorage.getItem(DEVICE_ID_KEY);
    if (!id) {
      id = `app-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
      await AsyncStorage.setItem(DEVICE_ID_KEY, id);
    }

    const savedUrl = (await AsyncStorage.getItem(SERVER_URL_KEY)) || 'https://TU-TUNEL.trycloudflare.com';
    const savedParticipant = await AsyncStorage.getItem(PARTICIPANTE_KEY);

    globalDeviceId = id;
    globalServerUrl = cleanServerUrl(savedUrl);
    globalParticipante = savedParticipant;

    if (!mountedRef.current) return;
    setDeviceId(id);
    setServerUrl(savedUrl);
    setParticipante(savedParticipant);
    setLog(
      savedParticipant
        ? `${savedParticipant} listo. Inicia captura cuando quieras.`
        : 'Ingresa la URL del servidor y registra este celular.',
      savedParticipant ? 'ok' : 'neutral'
    );
  };

  const activateSensors = async () => {
    if (accelerometerSubscriptionRef.current) {
      return true;
    }

    try {
      Accelerometer.setUpdateInterval(500);
      accelerometerSubscriptionRef.current = Accelerometer.addListener((data) => {
        const nextAccel = {
          gx: numOrNull(data.x),
          gy: numOrNull(data.y),
          gz: numOrNull(data.z),
          g_magnitude: calculateMagnitude(data.x, data.y, data.z),
          acceleration_mps2: globalAccelData.acceleration_mps2,
          sensor_timestamp_ms: Date.now(),
          supported: true,
          permission_state: 'granted',
        };

        globalAccelData = nextAccel;
        setAccelData(nextAccel);
      });

      const nextAccel = { ...globalAccelData, supported: true, permission_state: 'granted' };
      globalAccelData = nextAccel;
      setAccelData(nextAccel);
      setLog('Acelerometro activado. Ahora puedes iniciar la captura.', 'ok');
      return true;
    } catch (error) {
      const nextAccel = { ...globalAccelData, supported: false, permission_state: 'error' };
      globalAccelData = nextAccel;
      setAccelData(nextAccel);
      setLog(`No se pudo activar el acelerometro:\n${error.message}`, 'error');
      return false;
    }
  };

  const registerParticipant = async () => {
    const url = cleanServerUrl(serverUrl);
    if (!url.startsWith('http')) {
      Alert.alert('URL invalida', 'Ingresa una URL http/https del servidor.');
      return;
    }
    if (!deviceId) {
      setLog('Preparando ID del dispositivo, intenta de nuevo en un momento.', 'error');
      return;
    }

    try {
      setLog('Registrando participante...', 'neutral');
      const resp = await fetch(`${url}/registrar`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          device_id: deviceId,
          device_label: createDeviceLabel(deviceId),
        }),
      });
      const data = await resp.json();

      if (!resp.ok || data.status !== 'ok') {
        throw new Error(data.msg || 'No se pudo registrar el dispositivo.');
      }

      await AsyncStorage.multiSet([
        [SERVER_URL_KEY, url],
        [PARTICIPANTE_KEY, data.participante],
      ]);

      globalServerUrl = url;
      globalParticipante = data.participante;
      setServerUrl(url);
      setParticipante(data.participante);
      setLog(`${data.participante} asignado.\nActiva captura para mandar GPS y acelerometro.`, 'ok');
    } catch (error) {
      setLog(`Error al registrar:\n${error.message}`, 'error');
    }
  };

  const requestLocationPermissions = async () => {
    const fg = await Location.requestForegroundPermissionsAsync();
    if (fg.status !== 'granted') {
      throw new Error('Se requiere permiso de ubicacion en primer plano.');
    }

    try {
      const bg = await Location.requestBackgroundPermissionsAsync();
      if (bg.status !== 'granted') {
        setLog('Permiso de fondo denegado. Funcionara mientras la app este abierta.', 'error');
      }
    } catch (error) {
      console.log('Segundo plano no disponible en este entorno:', error.message);
    }
  };

  const startCapture = async () => {
    if (!participante) {
      Alert.alert('Falta registro', 'Primero conecta y registra este celular.');
      return;
    }

    try {
      await requestLocationPermissions();
      await activateSensors();

      globalLastPoint = null;
      globalSpeedHistory = [];
      globalLastKnownLocation = null;
      setActivo(true);
      setLog('Obteniendo ubicacion y acelerometro...', 'neutral');

      try {
        await Location.startLocationUpdatesAsync(LOCATION_TASK_NAME, {
          accuracy: Location.Accuracy.BestForNavigation,
          timeInterval: GPS_SEND_INTERVAL_MS,
          distanceInterval: 0,
          showsBackgroundLocationIndicator: true,
          foregroundService: {
            notificationTitle: 'GPS Tracker activo',
            notificationBody: 'Enviando ubicacion al servidor...',
            notificationColor: '#2563eb',
          },
        });
      } catch (error) {
        console.log('Background location no disponible:', error.message);
      }

      globalLocationSubscription = await Location.watchPositionAsync(
        {
          accuracy: Location.Accuracy.BestForNavigation,
          timeInterval: GPS_SEND_INTERVAL_MS,
          distanceInterval: 0,
        },
        handleLocation
      );

      if (globalTimer) clearInterval(globalTimer);
      globalTimer = setInterval(() => {
        if (globalLastKnownLocation) {
          handleLocation(globalLastKnownLocation);
        }
      }, 500);
    } catch (error) {
      setActivo(false);
      setLog(error.message, 'error');
    }
  };

  const stopCapture = async () => {
    if (mountedRef.current) {
      setActivo(false);
    }

    if (globalTimer) {
      clearInterval(globalTimer);
      globalTimer = null;
    }
    if (globalLocationSubscription) {
      globalLocationSubscription.remove();
      globalLocationSubscription = null;
    }
    if (accelerometerSubscriptionRef.current) {
      accelerometerSubscriptionRef.current.remove();
      accelerometerSubscriptionRef.current = null;
    }

    try {
      const started = await Location.hasStartedLocationUpdatesAsync(LOCATION_TASK_NAME);
      if (started) {
        await Location.stopLocationUpdatesAsync(LOCATION_TASK_NAME);
      }
    } catch (error) {
      console.log('Location task ya estaba detenida:', error.message);
    }
  };

  const stopFromButton = async () => {
    await stopCapture();
    setLog('Captura detenida.', 'neutral');
  };

  const handleLocation = async (loc) => {
    globalLastKnownLocation = loc;

    try {
      const result = await sendGps(loc);
      if (!result || !mountedRef.current) return;

      const { data, speed } = result;
      const checkpoint = data.checkpoint_mas_cercano;
      const distance = Number(data.distancia_checkpoint_mas_cercano_m);

      if (data.status === 'cerrado') {
        await stopCapture();
        setLog('Sesion terminada por el servidor (limite de tiempo alcanzado).', 'error');
        return;
      }

      if (data.status === 'limite_participantes') {
        await stopCapture();
        setLog(data.msg || 'Limite de participantes alcanzado.', 'error');
        return;
      }

      if (data.participante && data.participante !== participante) {
        setParticipante(data.participante);
        globalParticipante = data.participante;
        await AsyncStorage.setItem(PARTICIPANTE_KEY, data.participante);
      }

      setLocation(loc);
      setSpeedInfo(speed);
      setAccelData(globalAccelData);
      setCheckpointInfo({
        label: getCheckpointLabel(checkpoint),
        distance: Number.isFinite(distance) ? distance : null,
      });
      setLog(
        `Ubicacion obtenida\n` +
          `Participante: ${globalParticipante}\n` +
          `Lat: ${loc.coords.latitude.toFixed(6)}\n` +
          `Lon: ${loc.coords.longitude.toFixed(6)}\n` +
          `Velocidad: ${fmt(speed.speed_kmh, 2)} km/h (${fmt(speed.speed_mps, 2)} m/s)\n` +
          `Aceleracion: ${fmt(speed.acceleration_mps2, 3)} m/s2\n` +
          `Acelerometro: ${globalAccelData.permission_state}\n` +
          `Precision: +/-${fmt(loc.coords.accuracy, 0)} m\n` +
          `Hora: ${new Date().toLocaleTimeString()}`,
        'ok'
      );
    } catch (error) {
      if (mountedRef.current) {
        setLog(`Datos obtenidos pero hubo error al enviar:\n${error.message}`, 'error');
      }
    }
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <StatusBar style="dark" />
      <Text style={styles.title}>GPS Tracker</Text>
      <Text style={styles.subtitle}>Captura ubicacion, velocidad y acelerometro del celular.</Text>

      <View style={styles.connectionPanel}>
        <Text style={styles.label}>URL del servidor</Text>
        <TextInput
          style={styles.input}
          value={serverUrl}
          onChangeText={setServerUrl}
          placeholder="https://...trycloudflare.com"
          autoCapitalize="none"
          autoCorrect={false}
          editable={!activo}
        />
        <TouchableOpacity
          style={[styles.button, styles.secondaryButton, (!canRegister || activo) && styles.disabledButton]}
          onPress={registerParticipant}
          disabled={!canRegister || activo}
        >
          <Text style={styles.buttonText}>Conectar y registrar</Text>
        </TouchableOpacity>
      </View>

      <TouchableOpacity
        style={[styles.button, styles.secondaryButton, accelData.permission_state === 'granted' && styles.disabledButton]}
        onPress={activateSensors}
        disabled={accelData.permission_state === 'granted'}
      >
        <Text style={styles.buttonText}>
          {accelData.permission_state === 'granted' ? 'Acelerometro activo' : 'Activar acelerometro manual'}
        </Text>
      </TouchableOpacity>

      <TouchableOpacity
        style={[styles.button, activo && styles.dangerButton]}
        onPress={activo ? stopFromButton : startCapture}
      >
        <Text style={styles.buttonText}>{activo ? 'Detener captura' : 'Iniciar captura'}</Text>
      </TouchableOpacity>

      <View style={styles.grid}>
        <MetricCard
          label="Velocidad"
          value={`${fmt(speedInfo.speed_kmh, 2)} km/h`}
          detail={`Fuente: ${speedInfo.speed_source || 'esperando GPS'}`}
        />
        <MetricCard
          label="Precision GPS"
          value={location ? `+/-${fmt(location.coords.accuracy, 0)} m` : '-- m'}
          detail={`Hora: ${location ? new Date(location.timestamp || Date.now()).toLocaleTimeString() : '--'}`}
        />
        <MetricCard
          full
          label="Checkpoint ponderado mas cercano"
          value={checkpointInfo.label}
          detail={`Distancia: ${fmt(checkpointInfo.distance, 2)} m`}
        />
        <View style={styles.cardFull}>
          <Text style={styles.label}>Acelerometro con gravedad</Text>
          <Text style={styles.small}>X: {fmt(accelData.gx, 3)} m/s2</Text>
          <Text style={styles.small}>Y: {fmt(accelData.gy, 3)} m/s2</Text>
          <Text style={styles.small}>Z: {fmt(accelData.gz, 3)} m/s2</Text>
          <Text style={styles.small}>Magnitud: {fmt(accelData.g_magnitude, 3)} m/s2</Text>
        </View>
        <MetricCard
          full
          label="Aceleracion"
          value={`${fmt(speedInfo.acceleration_mps2, 3)} m/s2`}
          detail="Velocidad / tiempo, 3 muestras"
        />
      </View>

      <View style={[styles.statusBox, styles[`status_${status.tone}`]]}>
        <Text style={[styles.statusText, styles[`statusText_${status.tone}`]]}>{status.text}</Text>
      </View>
    </ScrollView>
  );
}

function MetricCard({ label, value, detail, full = false }) {
  return (
    <View style={full ? styles.cardFull : styles.cardHalf}>
      <Text style={styles.label}>{label}</Text>
      <Text style={styles.value} numberOfLines={2} adjustsFontSizeToFit>
        {value}
      </Text>
      <Text style={styles.detail}>{detail}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f8fafc',
  },
  content: {
    padding: 20,
    paddingTop: 58,
    paddingBottom: 40,
  },
  title: {
    color: '#0f172a',
    fontSize: 30,
    fontWeight: '800',
    marginBottom: 6,
  },
  subtitle: {
    color: '#475569',
    fontSize: 14,
    lineHeight: 20,
    marginBottom: 18,
  },
  connectionPanel: {
    backgroundColor: '#ffffff',
    borderColor: '#e2e8f0',
    borderRadius: 8,
    borderWidth: 1,
    marginBottom: 12,
    padding: 14,
  },
  input: {
    backgroundColor: '#f1f5f9',
    borderColor: '#e2e8f0',
    borderRadius: 8,
    borderWidth: 1,
    color: '#0f172a',
    fontSize: 15,
    marginBottom: 10,
    paddingHorizontal: 12,
    paddingVertical: 12,
  },
  button: {
    alignItems: 'center',
    backgroundColor: '#2563eb',
    borderRadius: 8,
    marginBottom: 10,
    paddingHorizontal: 16,
    paddingVertical: 15,
  },
  secondaryButton: {
    backgroundColor: '#0f766e',
  },
  dangerButton: {
    backgroundColor: '#dc2626',
  },
  disabledButton: {
    backgroundColor: '#93c5fd',
  },
  buttonText: {
    color: '#ffffff',
    fontSize: 16,
    fontWeight: '800',
    textAlign: 'center',
  },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'space-between',
    marginTop: 4,
  },
  cardHalf: {
    backgroundColor: '#ffffff',
    borderColor: '#e2e8f0',
    borderRadius: 8,
    borderWidth: 1,
    marginBottom: 10,
    minHeight: 112,
    padding: 12,
    width: '48.5%',
  },
  cardFull: {
    backgroundColor: '#ffffff',
    borderColor: '#e2e8f0',
    borderRadius: 8,
    borderWidth: 1,
    marginBottom: 10,
    minHeight: 104,
    padding: 12,
    width: '100%',
  },
  label: {
    color: '#64748b',
    fontSize: 12,
    fontWeight: '700',
    marginBottom: 6,
    textTransform: 'uppercase',
  },
  value: {
    color: '#0f172a',
    fontSize: 23,
    fontWeight: '900',
    lineHeight: 28,
  },
  detail: {
    color: '#475569',
    fontSize: 13,
    lineHeight: 18,
    marginTop: 5,
  },
  small: {
    color: '#334155',
    fontFamily: Platform.select({ ios: 'Menlo', android: 'monospace', default: 'monospace' }),
    fontSize: 14,
    lineHeight: 21,
  },
  statusBox: {
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 4,
    padding: 14,
  },
  status_neutral: {
    backgroundColor: '#f1f5f9',
    borderColor: '#e2e8f0',
  },
  status_ok: {
    backgroundColor: '#dcfce7',
    borderColor: '#86efac',
  },
  status_error: {
    backgroundColor: '#fee2e2',
    borderColor: '#fecaca',
  },
  statusText: {
    fontSize: 14,
    lineHeight: 20,
    textAlign: 'left',
  },
  statusText_neutral: {
    color: '#334155',
  },
  statusText_ok: {
    color: '#166534',
  },
  statusText_error: {
    color: '#991b1b',
  },
});
