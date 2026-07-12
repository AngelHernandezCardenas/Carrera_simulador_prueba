import { Platform } from 'react-native';

export const numOrNull = (value) => (Number.isFinite(value) ? value : null);

export const fmt = (value, decimals = 2) => (Number.isFinite(value) ? value.toFixed(decimals) : '--');

export const cleanServerUrl = (value) => value.trim().replace(/\/+$/, '');

export const getCheckpointLabel = (checkpoint) => {
  if (!checkpoint) return '--';
  if (typeof checkpoint === 'object' && checkpoint.nombre) {
    return checkpoint.nombre;
  }
  return `Checkpoint ${checkpoint.id || checkpoint}`;
};

export const createDeviceLabel = (deviceId) => {
  const prefix = Platform.OS === 'ios' ? 'iPhone' : Platform.OS === 'android' ? 'Android' : 'App';
  return `${prefix}-${deviceId.slice(0, 8)}`;
};
