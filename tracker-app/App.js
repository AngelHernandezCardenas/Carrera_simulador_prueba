import React, { useEffect, useRef, useState, useMemo } from 'react';
import { Alert, Platform, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View, LogBox } from 'react-native';
import { StatusBar } from 'expo-status-bar';
import * as TaskManager from 'expo-task-manager';
import { useCameraPermissions } from 'expo-camera';

import StorageService from './src/services/StorageService';
import NetworkService from './src/services/NetworkService';
import LocationService from './src/services/LocationService';
import SensorService from './src/services/SensorService';
import { fmt, cleanServerUrl, getCheckpointLabel } from './src/utils/FormatUtils';

import MetricCard from './src/components/MetricCard';
import ScannerCamera from './src/components/ScannerCamera';
import GalleryModal from './src/components/GalleryModal';
import ErrorBoundary from './src/ErrorBoundary';

const isScannerMode = Platform.OS === 'web' && typeof window !== 'undefined' && window.location.pathname.endsWith('/scan');

// LogBox.ignoreAllLogs();
const LOCATION_TASK_NAME = 'background-location-task';

// Globals for Background Task (since TaskManager is out of React context)
let globalServerUrl = '';
let globalParticipante = null;
let globalDeviceId = null;
let globalCheckpoint = 0;
let globalSendingGps = false;
let globalLastGpsSentMs = 0;
const GPS_SEND_INTERVAL_MS = 2000;

const hydrateGlobals = async () => {
  if (!globalServerUrl) globalServerUrl = await StorageService.getServerUrl() || '';
  if (!globalParticipante) globalParticipante = await StorageService.getParticipante();
  if (!globalDeviceId) globalDeviceId = await StorageService.getDeviceId();
};

const sendGps = async (loc) => {
  await hydrateGlobals();
  if (!globalServerUrl || !globalParticipante || !globalDeviceId || !loc?.coords) return null;

  const nowMs = Date.now();
  if (globalSendingGps || nowMs - globalLastGpsSentMs < GPS_SEND_INTERVAL_MS) return null;

  globalSendingGps = true;
  globalLastGpsSentMs = nowMs;

  try {
    const speed = LocationService.calculateSpeed(loc);
    const accelData = SensorService.getData();
    // Update accelData internally just to keep consistency in case we want to fetch it later
    SensorService.setAccelerationMps2(speed.acceleration_mps2);

    const payload = {
      latitude: loc.coords.latitude,
      longitude: loc.coords.longitude,
      accuracy: loc.coords.accuracy,
      altitude: loc.coords.altitude,
      altitude_accuracy: loc.coords.altitudeAccuracy,
      heading: loc.coords.heading,
      speed_mps: speed.speed_mps,
      speed_kmh: speed.speed_kmh,
      speed_source: speed.speed_source,
      accel_gx: accelData.gx,
      accel_gy: accelData.gy,
      accel_gz: accelData.gz,
      accel_g_magnitude: accelData.g_magnitude,
      acceleration_mps2: speed.acceleration_mps2,
      sensor_timestamp_ms: accelData.sensor_timestamp_ms,
      client_timestamp_ms: nowMs,
      device_id: globalDeviceId,
      participante: globalParticipante,
    };

    const data = await NetworkService.sendGpsData(globalServerUrl, payload);
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
  const [status, setStatus] = useState({ text: 'Waiting...', tone: 'neutral' });
  const [checkpointConfirmado, setCheckpointConfirmado] = useState(false);
  
  const [galeriaVisible, setGaleriaVisible] = useState(false);
  const [galeriaImagenes, setGaleriaImagenes] = useState([]);
  
  const [location, setLocation] = useState(null);
  const [speedInfo, setSpeedInfo] = useState({
    speed_kmh: null,
    speed_mps: null,
    speed_source: 'waiting GPS',
    acceleration_mps2: null,
  });
  const [checkpointInfo, setCheckpointInfo] = useState({ label: '--', distance: null });
  const [accelData, setAccelData] = useState(SensorService.getData());
  
  const mountedRef = useRef(true);
  let globalTimer = useRef(null);

  // CAMERA AND YOLO STATE
  const [permission, requestPermission] = useCameraPermissions();
  const [contandoActivo, setContandoActivo] = useState(false);
  const [maxCounts, setMaxCounts] = useState({ Rojo: 0, Blanco: 0, Negro: 0 });
  const [detectedBalls, setDetectedBalls] = useState([]);
  const [targetScanParticipant, setTargetScanParticipant] = useState("Desconocido");
  
  const cameraRef = useRef(null);
  const scanningRef = useRef(false);
  const countsRef = useRef({ Rojo: 0, Blanco: 0, Negro: 0 });

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
    let id = await StorageService.getDeviceId();
    if (!id) {
      id = `app-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
      await StorageService.setDeviceId(id);
    }

    let savedUrl = await StorageService.getServerUrl();
    if (!savedUrl && Platform.OS === 'web') {
      savedUrl = window.location.origin;
    }
    let savedParticipant = await StorageService.getParticipante();
    if (isScannerMode && savedParticipant && savedParticipant.toLowerCase().includes('participante')) {
      savedParticipant = null; // Do not load previous participant in scanner mode so backend assigns Judge
    } else if (!isScannerMode && savedParticipant && (savedParticipant.toLowerCase().includes('judge') || savedParticipant.toLowerCase().includes('juez'))) {
      savedParticipant = null; // Do not load previous judge in participant mode so backend assigns Participant
    }
    const savedCheckpoint = await StorageService.getCheckpoint();

    globalDeviceId = id;
    globalServerUrl = cleanServerUrl(savedUrl);
    globalParticipante = savedParticipant;
    if (savedCheckpoint) globalCheckpoint = parseInt(savedCheckpoint, 10);

    if (!mountedRef.current) return;
    setDeviceId(id);
    setServerUrl(savedUrl);
    setParticipante(savedParticipant);
    if (savedCheckpoint) setCheckpointInfo(prev => ({ ...prev, id: parseInt(savedCheckpoint, 10) }));
    setLog(
      savedParticipant
        ? `${savedParticipant} ready. Start capture when ready.`
        : 'Enter Server URL and register device.',
      savedParticipant ? 'ok' : 'neutral'
    );
  };

  const activateSensors = async () => {
    try {
      await SensorService.activate((data) => setAccelData(data));
      setLog('Accelerometer active. You can now start capture.', 'ok');
      return true;
    } catch (error) {
      setAccelData(SensorService.getData());
      setLog(`Could not activate accelerometer:\n${error.message}`, 'error');
      return false;
    }
  };

  const registerParticipant = async () => {
    const url = cleanServerUrl(serverUrl);
    if (!url.startsWith('http')) {
      Alert.alert('Invalid URL', 'Enter a valid http/https server URL.');
      return;
    }
    if (!deviceId) {
      setLog('Preparing device ID, try again in a moment.', 'error');
      return;
    }

    try {
      setLog('Registering participant...', 'neutral');
      
      const customName = !isScannerMode ? (participante || "") : undefined;
      
      const respData = await NetworkService.registerDevice(serverUrl, deviceId, customName);
      
      const assigned = respData.participante || participante || 'Unknown Participant';
      setParticipante(assigned);
      globalParticipante = assigned;
      await StorageService.multiSet([
        [StorageService.SERVER_URL_KEY, url],
        [StorageService.PARTICIPANTE_KEY, assigned],
      ]);
      
      globalServerUrl = url;
      setServerUrl(url);
      setLog(`Registered correctly: ${assigned}`, 'ok');
      setActivo(true);
      setCheckpointConfirmado(false); // Reset checkpoint confirmation
      return assigned;
    } catch (error) {
      console.warn('Error registering device:', error);
      setLog(`Registration error: ${error.message}`, 'error');
      return null;
    }
  };

  const confirmarCheckpoint = async () => {
    if (!checkpointInfo.id) {
      Alert.alert("Error", "Select a checkpoint first.");
      return;
    }
    try {
      setLog('Confirming checkpoint...', 'neutral');
      await NetworkService.confirmJudgeCheckpoint(serverUrl, deviceId, checkpointInfo.id);
      setCheckpointConfirmado(true);
      setLog(`Checkpoint ${checkpointInfo.id} confirmed.`, 'ok');
    } catch (error) {
      console.warn('Error confirming checkpoint:', error);
      Alert.alert("Error", error.message);
      setLog(error.message, 'error');
    }
  };

  const startCapture = async () => {
    if (!participante && !globalParticipante) {
      if (!isScannerMode) {
        // Auto-register runners if they just click Start Capture
        const assigned = await registerParticipant();
        if (!assigned) return; // Registration failed
      } else {
        Alert.alert('Missing registration', 'Connect and register this device first.');
        return;
      }
    }

    try {
      const hasPermissions = await LocationService.requestPermissions();
      if (!hasPermissions) {
        setLog('Background permission denied. Will function while app is open.', 'error');
      }
      await activateSensors();

      setActivo(true);
      setLog('Getting location and accelerometer...', 'neutral');

      await LocationService.startTracking(LOCATION_TASK_NAME, handleLocation);

      if (globalTimer.current) clearInterval(globalTimer.current);
      globalTimer.current = setInterval(() => {
        const lastKnown = LocationService.getLastKnownLocation();
        if (lastKnown) {
          handleLocation(lastKnown);
        }
      }, 500);
    } catch (error) {
      setActivo(false);
      setLog(error.message, 'error');
    }
  };

  const stopCapture = async () => {
    if (mountedRef.current) setActivo(false);
    if (globalTimer.current) {
      clearInterval(globalTimer.current);
      globalTimer.current = null;
    }
    SensorService.stop();
    await LocationService.stopTracking(LOCATION_TASK_NAME);
  };

  const stopFromButton = async () => {
    await stopCapture();
    setLog('Capture stopped.', 'neutral');
  };

  const handleLocation = async (loc) => {
    try {
      const result = await sendGps(loc);
      if (!result || !mountedRef.current) return;

      const { data, speed } = result;
      const checkpoint = data.checkpoint_mas_cercano;
      const distance = Number(data.distancia_checkpoint_mas_cercano_m);

      if (data.status === 'cerrado') {
        await stopCapture();
        setLog('Session terminated by server (time limit reached).', 'error');
        return;
      }

      if (data.status === 'limite_participantes') {
        await stopCapture();
        setLog(data.msg || 'Participant limit reached.', 'error');
        return;
      }

      if (data.participante && data.participante !== participante) {
        setParticipante(data.participante);
        globalParticipante = data.participante;
        await StorageService.setParticipante(data.participante);
      }

      setLocation(loc);
      setSpeedInfo(speed);
      setAccelData(SensorService.getData());
      setCheckpointInfo(prev => ({
        ...prev,
        label: getCheckpointLabel(checkpoint),
        distance: Number.isFinite(distance) ? distance : null,
      }));
      if (isScannerMode) {
        setLog(`Location obtained\nJudge: ${globalParticipante.replace('Judge_', '')}`, 'ok');
      } else {
        setLog(
          `Location obtained\nParticipant: ${globalParticipante.replace(/participante_/i, '')}\nLat: ${loc.coords.latitude.toFixed(6)}\nLon: ${loc.coords.longitude.toFixed(6)}\nSpeed: ${fmt(speed.speed_kmh, 2)} km/h (${fmt(speed.speed_mps, 2)} m/s)\nAcceleration: ${fmt(speed.acceleration_mps2, 3)} m/s2\nAccelerometer: ${SensorService.getData().permission_state}\nAccuracy: +/-${fmt(loc.coords.accuracy, 0)} m\nTime: ${new Date().toLocaleTimeString()}`,
          'ok'
        );
      }
    } catch (error) {
      if (mountedRef.current) {
        setLog(`Location obtained but failed to send:\n${error.message}`, 'error');
      }
    }
  };

  // CAMERA SCANNING FUNCTIONS
  const escanearUnaVez = async () => {
    if (scanningRef.current || !cameraRef.current) return;
    
    const ptsActuales = (countsRef.current.Rojo * 1) + (countsRef.current.Blanco * 5) + (countsRef.current.Negro * 3);
    if (ptsActuales >= 10) return;

    scanningRef.current = true;
    setContandoActivo(true);
    setLog('Procesando imagen (Rápido 150%)...', 'info');

    try {
      const photo = await cameraRef.current.takePictureAsync({ base64: true, quality: 0.8, shutterSound: false });
      const data = await NetworkService.processVision(globalServerUrl, globalDeviceId, targetScanParticipant, photo.base64, globalCheckpoint);

      if (data.status === 'ok') {
        setDetectedBalls(data.balls || []);
        if (data.counts) {
          for (const color of ['Rojo', 'Blanco', 'Negro']) {
            let val = data.counts[color] || 0;
            countsRef.current[color] = Math.max(countsRef.current[color], val);
          }
          setMaxCounts({ ...countsRef.current });

          const pts = (countsRef.current.Rojo * 1) + (countsRef.current.Blanco * 5) + (countsRef.current.Negro * 3);
          setLog(`Scan ready: ${pts} points.`, 'success');
          
          try {
            await NetworkService.saveWeight(globalServerUrl, targetScanParticipant, pts, countsRef.current, globalParticipante, globalCheckpoint);
            setLog(`Saved ${pts} kg for ${targetScanParticipant}`, 'success');
          } catch (err) {
            setLog(`Error saving weight: ${err.message}`, 'error');
          }

          setTimeout(() => {
            if (mountedRef.current) setDetectedBalls([]);
          }, 3000);
        }
      }
    } catch (e) {
      setLog('Error connecting to server', 'error');
    }

    scanningRef.current = false;
    setContandoActivo(false);
  };

  const reiniciarEscaneo = () => {
    countsRef.current = { Rojo: 0, Blanco: 0, Negro: 0 };
    setMaxCounts({ Rojo: 0, Blanco: 0, Negro: 0 });
    setDetectedBalls([]);
    setLog('Escaneo reiniciado', 'neutral');
  };

  const handleSaveScore = async () => {
    const currentMax = maxCounts; // since we might have manually edited maxCounts
    const pts = (currentMax.Rojo * 1) + (currentMax.Blanco * 5) + (currentMax.Negro * 3);
    try {
      await NetworkService.saveWeight(globalServerUrl, targetScanParticipant, pts, currentMax, globalParticipante, globalCheckpoint);
      setLog(`Saved manually: ${pts} kg for ${targetScanParticipant}`, 'success');
    } catch (err) {
      setLog(`Error saving weight: ${err.message}`, 'error');
    }
  };

  const abrirGaleria = async () => {
    try {
      const data = await NetworkService.getGallery(globalServerUrl, targetScanParticipant);
      setGaleriaImagenes(data);
      setGaleriaVisible(true);
    } catch (e) {
      setLog('Error loading gallery', 'error');
    }
  };

  const limpiarGaleria = async () => {
    try {
      await NetworkService.clearGallery(globalServerUrl);
      setGaleriaImagenes([]);
      setLog('Gallery cleared', 'neutral');
    } catch (e) {
      setLog('Error clearing gallery', 'error');
    }
  };

  return (
    <ErrorBoundary>
      <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <StatusBar style="dark" />
      <Text style={styles.title}>Tracker & Scanner</Text>
      <Text style={styles.subtitle}>Capture location and scan balls with YOLO.</Text>

      {/* CAMERA AND YOLO */}
      {isScannerMode && (
        !permission ? (
          <View style={styles.connectionPanel}><Text>Loading camera permissions...</Text></View>
        ) : !permission.granted ? (
          <View style={styles.connectionPanel}>
            <Text style={styles.label}>CAMERA AND YOLO SCANNER</Text>
            <Text style={{ marginBottom: 10 }}>We need permission to use the camera</Text>
            <TouchableOpacity style={[styles.button, styles.secondaryButton]} onPress={requestPermission}>
              <Text style={styles.buttonText}>Grant Permission</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <ScannerCamera
            cameraRef={cameraRef}
            contandoActivo={contandoActivo}
            maxCounts={maxCounts}
            setMaxCounts={setMaxCounts}
            detectedBalls={detectedBalls}
            onScanOnce={escanearUnaVez}
            onReset={reiniciarEscaneo}
            onSaveScore={handleSaveScore}
            onOpenGallery={abrirGaleria}
          />
        )
      )}

      {/* METRICS */}
      {!isScannerMode && location && (
        <View style={styles.grid}>
          <MetricCard label="Latitude" value={fmt(location.coords.latitude, 5)} />
          <MetricCard label="Longitude" value={fmt(location.coords.longitude, 5)} />
          <MetricCard label="Altitude" value={fmt(location.coords.altitude, 1)} detail="meters" />
          <MetricCard label="Speed" value={fmt(speedInfo?.speed_kmh, 2)} detail="km/h" />
          <MetricCard label="Accuracy" value={fmt(location.coords.accuracy, 1)} detail="meters" />
          <MetricCard full label="Nearest weighted checkpoint" value={checkpointInfo.label} detail={`Distance: ${fmt(checkpointInfo.distance, 2)} m`} />
        </View>
      )}

      {/* SERVER AND REGISTRATION */}
      <View style={styles.connectionPanel}>
        <Text style={styles.label}>Server URL</Text>
        <TextInput
          style={styles.input}
          value={serverUrl}
          onChangeText={setServerUrl}
          placeholder="https://...trycloudflare.com"
          autoCapitalize="none"
          autoCorrect={false}
          editable={!activo}
        />
        {!isScannerMode ? (
          <>
            <Text style={styles.label}>PARTICIPANT / DEVICE NAME</Text>
            <TextInput
              style={[styles.input, { backgroundColor: '#e2e8f0', color: '#475569' }]}
              value={participante}
              onChangeText={setParticipante}
              placeholder="Automatic assignment..."
              editable={false}
            />
          </>
        ) : (
          <>
            <Text style={styles.label}>Select Checkpoint (Judge)</Text>
            <select
              style={{ ...styles.input, height: 40, padding: 8 }}
              value={checkpointInfo.id ? checkpointInfo.id.toString() : ""}
              onChange={(e) => {
                const rawVal = e.target.value;
                if (!rawVal) {
                  setCheckpointInfo(prev => ({ ...prev, id: null }));
                  StorageService.setCheckpoint("");
                  globalCheckpoint = null;
                } else {
                  const val = parseInt(rawVal, 10);
                  setCheckpointInfo(prev => ({ ...prev, id: val }));
                  StorageService.setCheckpoint(val.toString());
                  globalCheckpoint = val;
                }
                setCheckpointConfirmado(false);
              }}
              disabled={checkpointConfirmado}
            >
              <option value="">-- Select Checkpoint --</option>
              <option value="1">Checkpoint 1</option>
              <option value="2">Checkpoint 2</option>
              <option value="3">Checkpoint 3</option>
              <option value="4">Checkpoint 4</option>
              <option value="5">Checkpoint 5</option>
              <option value="6">Checkpoint 6</option>
              <option value="7">Checkpoint 7</option>
              <option value="8">Checkpoint 8</option>
              <option value="9">Checkpoint 9</option>
              <option value="10">Checkpoint 10</option>
            </select>
            
            <TouchableOpacity
              style={[styles.button, { backgroundColor: '#f59e0b', marginBottom: 15 }, (checkpointConfirmado || !checkpointInfo.id) && styles.disabledButton]}
              onPress={confirmarCheckpoint}
              disabled={checkpointConfirmado || !checkpointInfo.id}
            >
              <Text style={styles.buttonText}>{checkpointConfirmado ? 'Checkpoint Confirmed' : 'Confirm Checkpoint'}</Text>
            </TouchableOpacity>

            <Text style={styles.label}>Participant to Scan</Text>
            <select
              style={{ ...styles.input, height: 40, padding: 8 }}
              value={targetScanParticipant || "Desconocido"}
              onChange={(e) => {
                setTargetScanParticipant(e.target.value);
                reiniciarEscaneo();
              }}
            >
              <option value="Desconocido">-- Select Participant --</option>
              <option value="Participante_1">Participant 1</option>
              <option value="Participante_2">Participant 2</option>
              <option value="Participante_3">Participant 3</option>
              <option value="Participante_4">Participant 4</option>
              <option value="Participante_5">Participant 5</option>
              <option value="Participante_6">Participant 6</option>
              <option value="Participante_7">Participant 7</option>
              <option value="Participante_8">Participant 8</option>
              <option value="Participante_9">Participant 9</option>
              <option value="Participante_10">Participant 10</option>
              <option value="Participante_11">Participant 11</option>
              <option value="Participante_12">Participant 12</option>
              <option value="Participante_13">Participant 13</option>
              <option value="Participante_14">Participant 14</option>
              <option value="Participante_15">Participant 15</option>
            </select>
          </>
        )}

        <TouchableOpacity
          style={[styles.button, styles.secondaryButton, (!canRegister || activo) && styles.disabledButton]}
          onPress={async () => {
            const assigned = await registerParticipant();
            if (assigned) {
              startCapture();
            }
          }}
          disabled={!canRegister || activo}
        >
          <Text style={styles.buttonText}>Connect and register</Text>
        </TouchableOpacity>
      </View>

      <TouchableOpacity
        style={[styles.button, activo && styles.dangerButton]}
        onPress={activo ? stopFromButton : startCapture}
      >
        <Text style={styles.buttonText}>{activo ? 'Stop capture' : 'Start capture'}</Text>
      </TouchableOpacity>

      {/* STATUS BOX */}
      <View style={[styles.statusBox, styles[`status_${status.tone}`]]}>
        <Text style={[styles.statusText, styles[`statusText_${status.tone}`]]}>{status.text}</Text>
      </View>

      <GalleryModal
        visible={galeriaVisible}
        onClose={() => setGaleriaVisible(false)}
        onClear={limpiarGaleria}
        galeriaImagenes={galeriaImagenes}
        serverUrl={serverUrl}
      />
    </ScrollView>
    </ErrorBoundary>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f8fafc' },
  content: { padding: 20, paddingTop: 58, paddingBottom: 40, width: '100%', maxWidth: 700, alignSelf: 'center' },
  title: { color: '#0f172a', fontSize: 30, fontWeight: '800', marginBottom: 6, textAlign: 'center' },
  subtitle: { color: '#475569', fontSize: 14, lineHeight: 20, marginBottom: 18, textAlign: 'center' },
  connectionPanel: { backgroundColor: '#ffffff', borderColor: '#e2e8f0', borderRadius: 12, borderWidth: 1, marginBottom: 16, padding: 20, shadowColor: '#000', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.05, shadowRadius: 4, elevation: 2 },
  input: { backgroundColor: '#f1f5f9', borderColor: '#e2e8f0', borderRadius: 8, borderWidth: 1, color: '#0f172a', fontSize: 15, marginBottom: 10, paddingHorizontal: 12, paddingVertical: 12 },
  button: { alignItems: 'center', backgroundColor: '#2563eb', borderRadius: 8, marginBottom: 10, paddingHorizontal: 16, paddingVertical: 15 },
  secondaryButton: { backgroundColor: '#0f766e' },
  dangerButton: { backgroundColor: '#dc2626' },
  disabledButton: { backgroundColor: '#93c5fd' },
  buttonText: { color: '#ffffff', fontSize: 16, fontWeight: 'bold', fontFamily: 'Times New Roman', textAlign: 'center' },
  grid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', marginTop: 4 },
  cardFull: { backgroundColor: '#ffffff', borderColor: '#e2e8f0', borderRadius: 8, borderWidth: 1, marginBottom: 10, minHeight: 104, padding: 12, width: '100%' },
  label: { color: '#64748b', fontSize: 12, fontWeight: '700', marginBottom: 6, textTransform: 'uppercase' },
  small: { color: '#334155', fontFamily: Platform.select({ ios: 'Menlo', android: 'monospace', default: 'monospace' }), fontSize: 14, lineHeight: 21 },
  statusBox: { borderRadius: 8, borderWidth: 1, marginTop: 4, padding: 14 },
  status_neutral: { backgroundColor: '#f1f5f9', borderColor: '#e2e8f0' },
  status_ok: { backgroundColor: '#dcfce7', borderColor: '#86efac' },
  status_error: { backgroundColor: '#fee2e2', borderColor: '#fecaca' },
  statusText: { fontSize: 14, lineHeight: 20, textAlign: 'left' },
  statusText_neutral: { color: '#334155' },
  statusText_ok: { color: '#166534' },
  statusText_error: { color: '#991b1b' }
});