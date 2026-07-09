import AsyncStorage from '@react-native-async-storage/async-storage';

class StorageService {
  DEVICE_ID_KEY = 'gps_tracker_device_id';
  SERVER_URL_KEY = 'gps_tracker_server_url';
  PARTICIPANTE_KEY = 'gps_tracker_participante';
  CHECKPOINT_KEY = '@tracker_checkpoint';

  async getDeviceId() {
    return await AsyncStorage.getItem(this.DEVICE_ID_KEY);
  }

  async setDeviceId(id) {
    await AsyncStorage.setItem(this.DEVICE_ID_KEY, id);
  }

  async getServerUrl() {
    return await AsyncStorage.getItem(this.SERVER_URL_KEY);
  }

  async setServerUrl(url) {
    await AsyncStorage.setItem(this.SERVER_URL_KEY, url);
  }

  async getParticipante() {
    return await AsyncStorage.getItem(this.PARTICIPANTE_KEY);
  }

  async setParticipante(participante) {
    await AsyncStorage.setItem(this.PARTICIPANTE_KEY, participante);
  }

  async getCheckpoint() {
    return await AsyncStorage.getItem(this.CHECKPOINT_KEY);
  }

  async setCheckpoint(cp) {
    await AsyncStorage.setItem(this.CHECKPOINT_KEY, cp);
  }

  async multiSet(data) {
    await AsyncStorage.multiSet(data);
  }
}

export default new StorageService();
