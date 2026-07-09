import { cleanServerUrl, createDeviceLabel } from '../utils/FormatUtils';

class NetworkService {
  async registerDevice(serverUrl, deviceId, customName) {
    const url = cleanServerUrl(serverUrl);
    
    const payload = {
      device_id: deviceId,
      device_label: createDeviceLabel(deviceId),
    };
    if (customName !== undefined && customName !== null) {
      payload.custom_name = customName || "";
    }

    const resp = await fetch(`${url}/registrar`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    
    const data = await resp.json();
    if (!resp.ok || data.status !== 'ok') {
      throw new Error(data.msg || 'No se pudo registrar el dispositivo.');
    }
    return data;
  }

  async confirmJudgeCheckpoint(serverUrl, deviceId, checkpointId) {
    const url = cleanServerUrl(serverUrl);
    const resp = await fetch(`${url}/set_judge_checkpoint`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        device_id: deviceId,
        checkpoint_id: checkpointId,
      }),
    });
    
    const data = await resp.json();
    if (!resp.ok || data.status !== 'ok') {
      throw new Error(data.msg || 'No se pudo confirmar el checkpoint.');
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

  async processVision(serverUrl, deviceId, participante, base64Image, checkpointId) {
    const resp = await fetch(`${serverUrl}/vision`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        device_id: deviceId || 'unknown',
        participante: participante || 'Desconocido',
        image: base64Image,
        mobile: true,
        checkpoint_id: checkpointId || 0
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

  async getGallery(serverUrl, participante = null) {
    let url = `${serverUrl}/galeria`;
    if (participante) {
      url += `?participante=${encodeURIComponent(participante)}`;
    }
    const resp = await fetch(url);
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

  async saveWeight(serverUrl, participante, peso_kg, counts = {}, juez = "Desconocido", checkpoint = "") {
    const url = serverUrl.replace(/\/$/, '');
    const resp = await fetch(`${url}/api/registrar_peso`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        participante,
        peso_kg,
        counts,
        juez,
        checkpoint
      })
    });
    const text = await resp.text();
    let data;
    try { data = JSON.parse(text); } catch(e) { throw new Error(`Invalid response (${resp.status}): ${text.substring(0, 100)}`); }
    if (!resp.ok) throw new Error(data.msg || "Error registrando peso");
    return data;
  }
}

export default new NetworkService();
