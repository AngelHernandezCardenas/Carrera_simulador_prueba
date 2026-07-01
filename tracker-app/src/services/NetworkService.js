import { cleanServerUrl, createDeviceLabel } from '../utils/FormatUtils';

class NetworkService {
  async registerDevice(serverUrl, deviceId) {
    const url = cleanServerUrl(serverUrl);
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
    return data;
  }

  async sendGpsData(serverUrl, payload) {
    const resp = await fetch(`${serverUrl}/gps`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    const respText = await resp.text();
    let data;
    try {
      data = JSON.parse(respText);
    } catch (e) {
      throw new Error(`Invalid GPS response (${resp.status}): ${respText.substring(0, 100)}`);
    }

    if (!resp.ok && data.status !== 'limite_participantes') {
      throw new Error(data.msg || `Error del servidor: ${resp.status}`);
    }

    return data;
  }

  async processVision(serverUrl, deviceId, participante, base64Image) {
    const resp = await fetch(`${serverUrl}/vision`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        device_id: deviceId || 'unknown',
        participante: participante || 'Desconocido',
        image: base64Image,
        mobile: true
      })
    });

    const respText = await resp.text();
    let data;
    try {
      data = JSON.parse(respText);
    } catch (e) {
      throw new Error(`Invalid server response (${resp.status}): ${respText.substring(0, 100)}`);
    }

    return data;
  }

  async getGallery(serverUrl) {
    const resp = await fetch(`${serverUrl}/galeria`);
    if (resp.ok) {
      return await resp.json();
    }
    throw new Error('No se pudo cargar la galería');
  }

  async clearGallery(serverUrl) {
    const resp = await fetch(`${serverUrl}/limpiar_galeria`, { method: 'POST' });
    const respText = await resp.text();
    let data;
    try {
      data = JSON.parse(respText);
    } catch (e) {
      throw new Error(`Invalid response (${resp.status}): ${respText.substring(0, 100)}`);
    }
    return data;
  }
}

export default new NetworkService();
