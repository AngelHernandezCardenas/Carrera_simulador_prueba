import { Accelerometer } from 'expo-sensors';
import { calculateMagnitude } from '../utils/MathUtils';
import { numOrNull } from '../utils/FormatUtils';

class SensorService {
  constructor() {
    this.subscription = null;
    this.accelData = {
      gx: null,
      gy: null,
      gz: null,
      g_magnitude: null,
      acceleration_mps2: null,
      sensor_timestamp_ms: null,
      supported: false,
      permission_state: 'not_requested',
    };
  }

  async activate(onUpdate) {
    if (this.subscription) {
      return true;
    }

    try {
      Accelerometer.setUpdateInterval(500);
      this.subscription = Accelerometer.addListener((data) => {
        const nextAccel = {
          gx: numOrNull(data.x),
          gy: numOrNull(data.y),
          gz: numOrNull(data.z),
          g_magnitude: calculateMagnitude(data.x, data.y, data.z),
          acceleration_mps2: this.accelData.acceleration_mps2, // Preserved from external updates if needed
          sensor_timestamp_ms: Date.now(),
          supported: true,
          permission_state: 'granted',
        };

        this.accelData = nextAccel;
        if (onUpdate) onUpdate(nextAccel);
      });

      this.accelData = { ...this.accelData, supported: true, permission_state: 'granted' };
      if (onUpdate) onUpdate(this.accelData);
      return true;
    } catch (error) {
      this.accelData = { ...this.accelData, supported: false, permission_state: 'error' };
      if (onUpdate) onUpdate(this.accelData);
      throw error;
    }
  }

  stop() {
    if (this.subscription) {
      this.subscription.remove();
      this.subscription = null;
    }
  }

  getData() {
    return this.accelData;
  }
  
  setAccelerationMps2(val) {
    this.accelData.acceleration_mps2 = val;
  }
}

export default new SensorService();
