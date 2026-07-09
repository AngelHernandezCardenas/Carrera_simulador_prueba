import * as Location from 'expo-location';
import { haversineMeters } from '../utils/MathUtils';
import { numOrNull } from '../utils/FormatUtils';

const GPS_SEND_INTERVAL_MS = 2000;
const ACCELERATION_SAMPLE_WINDOW = 3;

class LocationService {
  constructor() {
    this.lastPoint = null;
    this.speedHistory = [];
    this.locationSubscription = null;
    this.lastKnownLocation = null;
  }

  async requestPermissions() {
    const fg = await Location.requestForegroundPermissionsAsync();
    if (fg.status !== 'granted') {
      throw new Error('Se requiere permiso de ubicacion en primer plano.');
    }

    try {
      const bg = await Location.requestBackgroundPermissionsAsync();
      if (bg.status !== 'granted') {
        return false; // Background denied
      }
    } catch (error) {
      console.log('Segundo plano no disponible en este entorno:', error.message);
      return false;
    }
    return true; // All granted or foreground granted
  }

  calculateSpeed(loc) {
    const nowMs = Date.now();
    const lat = loc.coords.latitude;
    const lon = loc.coords.longitude;
    let speedMps = numOrNull(loc.coords.speed);
    let speedSource = Number.isFinite(speedMps) ? 'gps_sensor' : 'none';
    let accelerationMps2 = null;

    if (!Number.isFinite(speedMps) && this.lastPoint) {
      const distance = haversineMeters(this.lastPoint.lat, this.lastPoint.lon, lat, lon);
      const dt = (nowMs - this.lastPoint.timestamp_ms) / 1000;
      if (dt > 0) {
        speedMps = distance / dt;
        speedSource = 'calculated_gps_distance_time';
      }
    }

    if (Number.isFinite(speedMps)) {
      const previousSamplesNeeded = ACCELERATION_SAMPLE_WINDOW - 1;
      if (this.speedHistory.length >= previousSamplesNeeded) {
        const reference = this.speedHistory[0];
        const dt = (nowMs - reference.timestamp_ms) / 1000;
        if (dt > 0 && Number.isFinite(reference.speed_mps)) {
          accelerationMps2 = (speedMps - reference.speed_mps) / dt;
        }
      }

      this.speedHistory.push({ speed_mps: speedMps, timestamp_ms: nowMs });
      while (this.speedHistory.length > previousSamplesNeeded) {
        this.speedHistory.shift();
      }
    }

    this.lastPoint = { lat, lon, timestamp_ms: nowMs, speed_mps: speedMps };

    return {
      speed_mps: speedMps,
      speed_kmh: Number.isFinite(speedMps) ? speedMps * 3.6 : null,
      speed_source: speedSource,
      acceleration_mps2: accelerationMps2,
    };
  }

  async startTracking(taskName, onLocationUpdate) {
    this.lastPoint = null;
    this.speedHistory = [];
    this.lastKnownLocation = null;

    try {
      await Location.startLocationUpdatesAsync(taskName, {
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

    try {
      const currentLoc = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.BestForNavigation });
      this.lastKnownLocation = currentLoc;
      if (onLocationUpdate) onLocationUpdate(currentLoc);
    } catch (e) {
      console.log('No se pudo obtener la ubicacion inicial:', e.message);
    }

    this.locationSubscription = await Location.watchPositionAsync(
      {
        accuracy: Location.Accuracy.BestForNavigation,
        timeInterval: GPS_SEND_INTERVAL_MS,
        distanceInterval: 0,
      },
      (loc) => {
        this.lastKnownLocation = loc;
        if (onLocationUpdate) onLocationUpdate(loc);
      }
    );
  }

  async stopTracking(taskName) {
    if (this.locationSubscription) {
      this.locationSubscription.remove();
      this.locationSubscription = null;
    }

    try {
      const started = await Location.hasStartedLocationUpdatesAsync(taskName);
      if (started) {
        await Location.stopLocationUpdatesAsync(taskName);
      }
    } catch (error) {
      console.log('Location task ya estaba detenida:', error.message);
    }
  }

  getLastKnownLocation() {
    return this.lastKnownLocation;
  }
}

export default new LocationService();
