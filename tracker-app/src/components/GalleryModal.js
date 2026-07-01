import React, { useState } from 'react';
import { View, Text, Modal, FlatList, TouchableOpacity, Image } from 'react-native';
import ImageViewer from 'react-native-image-zoom-viewer';

export default function GalleryModal({ visible, onClose, onClear, galeriaImagenes, serverUrl }) {
  const [imagenExpandida, setImagenExpandida] = useState(null);
  const [mostrarContorno, setMostrarContorno] = useState(true);

  const formatParticipantName = (name) => {
    if (!name || String(name).toLowerCase() === 'desconocido') return 'Unknown Participant';
    return String(name).replace(/participante[_ ]?/i, 'Participant ');
  };

  return (
    <>
      <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
        <View style={{ flex: 1, backgroundColor: '#f8fafc', paddingTop: 40 }}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', paddingHorizontal: 20, marginBottom: 10 }}>
            <Text style={{ fontSize: 24, fontWeight: 'bold' }}>Scan Gallery</Text>
            <View style={{ flexDirection: 'row' }}>
              <TouchableOpacity onPress={onClear} style={{ backgroundColor: '#f59e0b', padding: 8, borderRadius: 8, marginRight: 10 }}>
                <Text style={{ color: 'white', fontWeight: 'bold' }}>Clear</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={onClose} style={{ backgroundColor: '#ef4444', padding: 8, borderRadius: 8 }}>
                <Text style={{ color: 'white', fontWeight: 'bold' }}>Close</Text>
              </TouchableOpacity>
            </View>
          </View>
          
          <FlatList
            data={galeriaImagenes}
            keyExtractor={(item) => item.filename}
            renderItem={({ item }) => (
              <View style={{ marginBottom: 20, padding: 10, backgroundColor: 'white', marginHorizontal: 10, borderRadius: 12, shadowColor: '#000', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.1, shadowRadius: 4, elevation: 3 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 5 }}>
                  <Text style={{ fontWeight: 'bold', marginRight: 10 }}>{formatParticipantName(item.participante || item.device_id)} Detections:</Text>
                  {item.detections && Object.entries(item.detections).map(([color, count]) => {
                    if (count === 0) return null;
                    const colorStr = String(color).toLowerCase();
                    const isWhite = colorStr.includes('blanco') || colorStr.includes('white');
                    const isRed = colorStr.includes('rojo') || colorStr.includes('red');
                    const isBlack = colorStr.includes('negro') || colorStr.includes('black');

                    let textColor = '#000000';
                    let strokeColor = '#d1d5db';
                    if (isWhite) { textColor = '#ffffff'; strokeColor = '#000000'; }
                    if (isRed) { textColor = '#ef4444'; strokeColor = '#000000'; }
                    
                    return (
                      <View key={color} style={{ marginRight: 15, alignItems: 'center', justifyContent: 'center' }}>
                        <View>
                          <Text style={{ position: 'absolute', left: -1, top: -1, fontSize: 12, fontFamily: 'serif', fontWeight: '900', color: strokeColor }}>{`${color}: ${count}`}</Text>
                          <Text style={{ position: 'absolute', left: 1, top: -1, fontSize: 12, fontFamily: 'serif', fontWeight: '900', color: strokeColor }}>{`${color}: ${count}`}</Text>
                          <Text style={{ position: 'absolute', left: -1, top: 1, fontSize: 12, fontFamily: 'serif', fontWeight: '900', color: strokeColor }}>{`${color}: ${count}`}</Text>
                          <Text style={{ position: 'absolute', left: 1, top: 1, fontSize: 12, fontFamily: 'serif', fontWeight: '900', color: strokeColor }}>{`${color}: ${count}`}</Text>
                          <Text style={{ fontSize: 12, fontFamily: 'serif', fontWeight: '900', color: textColor }}>{`${color}: ${count}`}</Text>
                        </View>
                      </View>
                    );
                  })}
                </View>
                <Text style={{ fontSize: 12, color: 'gray', marginBottom: 10 }}>{new Date(item.timestamp * 1000).toLocaleString()} - {formatParticipantName(item.participante || item.device_id)}</Text>
                <TouchableOpacity onPress={() => { setImagenExpandida(item); setMostrarContorno(true); }}>
                  <Image
                    source={{ uri: `${serverUrl}/capturas/${item.filename}` }}
                    style={{ width: '100%', height: 250, resizeMode: 'contain', borderRadius: 8 }}
                  />
                </TouchableOpacity>
              </View>
            )}
            ListEmptyComponent={<Text style={{ textAlign: 'center', marginTop: 50, color: 'gray' }}>No images in the gallery.</Text>}
          />
        </View>
      </Modal>

      <Modal visible={!!imagenExpandida} transparent={true} animationType="fade" onRequestClose={() => setImagenExpandida(null)}>
        {imagenExpandida && (
          <ImageViewer
            imageUrls={[
              { url: mostrarContorno 
                ? `${serverUrl}/capturas/${imagenExpandida.filename}` 
                : `${serverUrl}/capturas/${imagenExpandida.filename.replace('.jpg', '_clean.jpg')}` }
            ]}
            index={0}
            enableSwipeDown={true}
            onSwipeDown={() => setImagenExpandida(null)}
            renderIndicator={() => null}
            saveToLocalByLongPress={false}
            renderHeader={() => (
              <View style={{ position: 'absolute', top: 40, left: 0, right: 0, zIndex: 10, paddingHorizontal: 20, flexDirection: 'row', justifyContent: 'space-between' }}>
                <TouchableOpacity onPress={() => setMostrarContorno(!mostrarContorno)} style={{ backgroundColor: '#2563eb', padding: 10, borderRadius: 8 }}>
                  <Text style={{ color: 'white', fontWeight: 'bold' }}>{mostrarContorno ? 'Hide Contours' : 'Show Contours'}</Text>
                </TouchableOpacity>
                <TouchableOpacity onPress={() => setImagenExpandida(null)} style={{ backgroundColor: '#ef4444', padding: 10, borderRadius: 8 }}>
                  <Text style={{ color: 'white', fontWeight: 'bold' }}>Close</Text>
                </TouchableOpacity>
              </View>
            )}
          />
        )}
      </Modal>
    </>
  );
}
