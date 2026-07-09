import React, { useState, useEffect, useRef } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, Animated, Easing } from 'react-native';
import { CameraView } from 'expo-camera';

export default function ScannerCamera({
  cameraRef,
  contandoActivo,
  maxCounts,
  setMaxCounts,
  detectedBalls,
  onScanOnce,
  onReset,
  onSaveScore,
  onOpenGallery,
  juezAsignado,
  checkpointEstablecido,
  targetScanParticipant,
  checkpointConfirmado,
  scanResultMessage
}) {
  const [isCameraReady, setIsCameraReady] = useState(false);
  const [cameraLayout, setCameraLayout] = useState(null);
  const [visibleColors, setVisibleColors] = useState(['Rojo', 'Blanco', 'Negro']);
  const [showCheckpointConfirmMessage, setShowCheckpointConfirmMessage] = useState(false);
  
  useEffect(() => {
    if (checkpointConfirmado) {
      setShowCheckpointConfirmMessage(true);
      const timer = setTimeout(() => {
        setShowCheckpointConfirmMessage(false);
      }, 5000);
      return () => clearTimeout(timer);
    } else {
      setShowCheckpointConfirmMessage(false);
    }
  }, [checkpointConfirmado]);

  useEffect(() => {
    if (detectedBalls && detectedBalls.length > 0) {
      setVisibleColors(['Negro']);
      const t1 = setTimeout(() => setVisibleColors(['Negro', 'Blanco']), 300);
      const t2 = setTimeout(() => setVisibleColors(['Negro', 'Blanco', 'Rojo']), 600);
      return () => { clearTimeout(t1); clearTimeout(t2); };
    } else {
      setVisibleColors(['Rojo', 'Blanco', 'Negro']);
    }
  }, [detectedBalls]);

  const spinValue = useRef(new Animated.Value(0)).current;
  const loopRef = useRef(null);

  useEffect(() => {
    if (contandoActivo) {
      loopRef.current = Animated.loop(
        Animated.timing(spinValue, {
          toValue: 1,
          duration: 2000,
          easing: Easing.linear,
          useNativeDriver: true
        })
      );
      loopRef.current.start();
    } else {
      if (loopRef.current) {
        loopRef.current.stop();
      }
      spinValue.setValue(0);
    }
  }, [contandoActivo, spinValue]);

  const spin = spinValue.interpolate({
    inputRange: [0, 1],
    outputRange: ['0deg', '360deg']
  });

  const totalPts = (maxCounts.Rojo * 3) + (maxCounts.Blanco * 1) + (maxCounts.Negro * 5);

  let statusText = "Waiting connection...";
  if (showCheckpointConfirmMessage) {
    statusText = `Checkpoint ${checkpointEstablecido} confirmed!`;
  } else if (juezAsignado) {
    let cleanJudge = juezAsignado.replace(/Judge_Checkpoint_/i, '').replace(/Judge_/i, '');
    statusText = `Judge: ${cleanJudge}`;
    if (checkpointConfirmado && checkpointEstablecido) {
      let cpName = (checkpointEstablecido === "4" || checkpointEstablecido === 4) ? "Home-Base" : checkpointEstablecido;
      statusText += `, Checkpoint: ${cpName}`;
      if (targetScanParticipant) {
        let cleanTeam = targetScanParticipant.replace(/Participante_/i, 'Team ');
        statusText += `, Team: ${cleanTeam}`;
      }
    }
  }

  return (
    <View style={styles.connectionPanel}>
      <Text style={styles.label}>CAMERA AND YOLO SCANNER</Text>

      <View style={{ marginBottom: 15, padding: 10, backgroundColor: '#f0fdf4', borderRadius: 8, borderWidth: 1, borderColor: '#bbf7d0', alignItems: 'center' }}>
        <Text style={{ fontSize: 16, fontWeight: 'bold', color: '#166534', marginBottom: 2 }}>{statusText}</Text>
      </View>

      {scanResultMessage && (
        <View style={{ marginBottom: 15, padding: 10, backgroundColor: '#dbeafe', borderRadius: 8, borderWidth: 1, borderColor: '#bfdbfe', alignItems: 'center' }}>
          <Text style={{ fontSize: 16, fontWeight: 'bold', color: '#1e40af' }}>{scanResultMessage}</Text>
        </View>
      )}

      {totalPts === 10 && (
         <View style={{ marginBottom: 15, padding: 10, backgroundColor: '#fef3c7', borderRadius: 8, borderWidth: 1, borderColor: '#fde68a', alignItems: 'center' }}>
           <Text style={{ fontSize: 16, fontWeight: 'bold', color: '#d97706' }}>Limit reached ({totalPts} pts)</Text>
         </View>
      )}

      {totalPts > 10 && (
         <View style={{ marginBottom: 15, padding: 10, backgroundColor: '#fee2e2', borderRadius: 8, borderWidth: 1, borderColor: '#fecaca', alignItems: 'center' }}>
           <Text style={{ fontSize: 16, fontWeight: 'bold', color: '#dc2626' }}>Limit exceeded ({totalPts} pts)</Text>
         </View>
      )}

      <View
        style={styles.cameraContainer}
        onLayout={(e) => {
          const { width, height } = e.nativeEvent.layout;
          setCameraLayout({ width, height });
        }}
      >
        <CameraView
          style={{ flex: 1 }}
          facing="back"
          ref={cameraRef}
          onCameraReady={() => setIsCameraReady(true)}
        />

        {/* Contorno del límite de detección (círculo central) */}
        {cameraLayout && (
          <Animated.View style={{
            position: 'absolute',
            left: cameraLayout.width / 2 - (Math.min(cameraLayout.width, cameraLayout.height) * 0.38),
            top: cameraLayout.height / 2 - (Math.min(cameraLayout.width, cameraLayout.height) * 0.38),
            width: Math.min(cameraLayout.width, cameraLayout.height) * 0.76,
            height: Math.min(cameraLayout.width, cameraLayout.height) * 0.76,
            borderRadius: Math.min(cameraLayout.width, cameraLayout.height) * 0.38,
            borderWidth: 1.5,
            borderColor: 'rgba(255, 255, 255, 0.6)',
            borderStyle: 'dashed',
            transform: [{ rotate: spin }]
          }} />
        )}

        {/* Contorno de las pelotas detectadas */}
        {cameraLayout && (() => {
          const colorCounts = { Rojo: 0, Blanco: 0, Negro: 0 };
          return detectedBalls.filter(b => visibleColors.includes(b.color)).map((b, i) => {
            const colorMap = { 'Rojo': '#ef4444', 'Blanco': '#ffffff', 'Negro': '#111111' };
            colorCounts[b.color] = (colorCounts[b.color] || 0) + 1;
            const currentCount = colorCounts[b.color];
            
            const cx = b.x_norm * cameraLayout.width;
            const cy = b.y_norm * cameraLayout.height;
            const r = b.r_norm * cameraLayout.width;

            return (
              <View key={i} style={StyleSheet.absoluteFill} pointerEvents="none">
                <View style={{
                  position: 'absolute',
                  left: cx - r,
                  top: cy - r,
                  width: r * 2,
                  height: r * 2,
                  borderRadius: r,
                  borderWidth: 3,
                  borderColor: colorMap[b.color] || '#00ff00'
                }} />
                <View style={{
                  position: 'absolute',
                  left: cx - 4,
                  top: cy - 4,
                  width: 8,
                  height: 8,
                  borderRadius: 4,
                  backgroundColor: colorMap[b.color] || '#00ff00'
                }} />
                <View style={{
                  position: 'absolute',
                  left: cx - r,
                  top: Math.max(18, cy - r - 25),
                  paddingHorizontal: 4,
                  paddingVertical: 2,
                }}>
                  <View>
                    <Text style={{ position: 'absolute', left: -1, top: -1, fontSize: 16, fontWeight: '900', color: b.color === 'Negro' ? 'white' : 'black' }}>{currentCount}</Text>
                    <Text style={{ position: 'absolute', left: 1, top: -1, fontSize: 16, fontWeight: '900', color: b.color === 'Negro' ? 'white' : 'black' }}>{currentCount}</Text>
                    <Text style={{ position: 'absolute', left: -1, top: 1, fontSize: 16, fontWeight: '900', color: b.color === 'Negro' ? 'white' : 'black' }}>{currentCount}</Text>
                    <Text style={{ position: 'absolute', left: 1, top: 1, fontSize: 16, fontWeight: '900', color: b.color === 'Negro' ? 'white' : 'black' }}>{currentCount}</Text>
                    <Text style={{ 
                      color: b.color === 'Blanco' ? 'white' : (b.color === 'Negro' ? 'black' : 'red'), 
                      fontSize: 16, 
                      fontWeight: '900' 
                    }}>
                      {currentCount}
                    </Text>
                  </View>
                </View>
              </View>
            );
          });
        })()}
      </View>

      {/* Botones */}
      <View style={{ marginBottom: 20 }}>
        <View style={{ flexDirection: 'row', marginBottom: 10 }}>
          <TouchableOpacity
            style={[styles.button, styles.secondaryButton, { flex: 1, backgroundColor: contandoActivo ? '#7f8c8d' : '#2563eb' }]}
            onPress={onScanOnce}
            disabled={contandoActivo || !isCameraReady}
          >
            <Text style={styles.buttonText}>
              {contandoActivo ? 'Processing...' : 'Scan Balls'}
            </Text>
          </TouchableOpacity>
        </View>
        <View style={{ flexDirection: 'row', marginBottom: 10 }}>
          <TouchableOpacity style={[styles.button, styles.dangerButton, { flex: 1, marginRight: 5 }]} onPress={onReset}>
            <Text style={styles.buttonText}>Reset</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[styles.button, { flex: 1, backgroundColor: '#059669', marginHorizontal: 5, alignItems: 'center' }]} onPress={onSaveScore}>
            <Text style={styles.buttonText}>Save Score</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[styles.button, { flex: 1, backgroundColor: '#8e44ad', marginLeft: 5, alignItems: 'center' }]} onPress={onOpenGallery}>
            <Text style={styles.buttonText}>Gallery</Text>
          </TouchableOpacity>
        </View>
      </View>

      {/* Contadores Manuales */}
      <View style={styles.countersContainer}>
        <View style={styles.counterPanel}>
          <View style={[styles.counterCircle, { backgroundColor: 'white', borderWidth: 1, borderColor: '#ccc' }]}>
            <Text style={styles.counterTextBlack}>White</Text>
          </View>
          <View style={styles.stepperContainer}>
            <TextInput
              style={styles.manualInputStepper}
              keyboardType="numeric"
              placeholder="0"
              value={maxCounts.Blanco === 0 ? "" : maxCounts.Blanco.toString()}
              onChangeText={(val) => {
                const num = parseInt(val) || 0;
                if (setMaxCounts) setMaxCounts(prev => ({ ...prev, Blanco: num }));
              }}
            />
          </View>
        </View>

        <View style={styles.counterPanel}>
          <View style={[styles.counterCircle, { backgroundColor: '#ef4444' }]}>
            <Text style={styles.counterTextWhite}>Red</Text>
          </View>
          <View style={styles.stepperContainer}>
            <TextInput
              style={styles.manualInputStepper}
              keyboardType="numeric"
              placeholder="0"
              value={maxCounts.Rojo === 0 ? "" : maxCounts.Rojo.toString()}
              onChangeText={(val) => {
                const num = parseInt(val) || 0;
                if (setMaxCounts) setMaxCounts(prev => ({ ...prev, Rojo: num }));
              }}
            />
          </View>
        </View>

        <View style={styles.counterPanel}>
          <View style={[styles.counterCircle, { backgroundColor: '#111111' }]}>
            <Text style={styles.counterTextWhite}>Black</Text>
          </View>
          <View style={styles.stepperContainer}>
            <TextInput
              style={styles.manualInputStepper}
              keyboardType="numeric"
              placeholder="0"
              value={maxCounts.Negro === 0 ? "" : maxCounts.Negro.toString()}
              onChangeText={(val) => {
                const num = parseInt(val) || 0;
                if (setMaxCounts) setMaxCounts(prev => ({ ...prev, Negro: num }));
              }}
            />
          </View>
        </View>
      </View>

      {/* Escaner de carga visual */}
      <View style={styles.scoreContainer}>
        <Text style={styles.scoreLabel}>Visual load scanner</Text>
        <View style={{ flexDirection: 'row', alignItems: 'baseline' }}>
          <Text style={styles.scoreValue}>{totalPts}</Text>
          <Text style={[styles.scoreValue, { marginLeft: 4 }]}>pts</Text>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  connectionPanel: {
    backgroundColor: '#ffffff',
    borderColor: '#e2e8f0',
    borderRadius: 12,
    borderWidth: 1,
    marginBottom: 16,
    padding: 20,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  label: {
    color: '#64748b',
    fontSize: 12,
    fontWeight: '700',
    marginBottom: 6,
    textTransform: 'uppercase',
  },
  cameraContainer: {
    width: '100%',
    height: 300,
    backgroundColor: 'black',
    borderRadius: 8,
    overflow: 'hidden',
    marginBottom: 10,
  },
  button: {
    alignItems: 'center',
    backgroundColor: '#2563eb',
    borderRadius: 8,
    paddingHorizontal: 16,
    paddingVertical: 15,
  },
  secondaryButton: {
    backgroundColor: '#0f766e',
  },
  dangerButton: {
    backgroundColor: '#dc2626',
  },
  buttonText: {
    color: '#ffffff',
    fontSize: 16,
    fontWeight: 'bold',
    fontFamily: 'Times New Roman', // matching App.js default
    textAlign: 'center',
  },
  countersContainer: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    marginBottom: 20,
    backgroundColor: '#f8fafc',
    padding: 10,
    borderRadius: 8,
  },
  counterPanel: {
    alignItems: 'center',
    backgroundColor: '#ffffff',
    padding: 10,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#e2e8f0',
    width: '30%',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
    elevation: 2,
  },
  counterCircle: {
    width: 50,
    height: 50,
    borderRadius: 25,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 10,
  },
  counterTextWhite: {
    color: 'white',
    fontWeight: 'bold',
    fontSize: 16,
  },
  counterTextBlack: {
    color: 'black',
    fontWeight: 'bold',
    fontSize: 16,
  },
  stepperContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    width: '100%',
  },
  stepperButton: {
    backgroundColor: '#e2e8f0',
    borderRadius: 4,
    padding: 5,
    width: 30,
    alignItems: 'center',
    justifyContent: 'center',
  },
  stepperText: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#334155',
  },
  manualInputStepper: {
    borderWidth: 1,
    borderColor: '#ccc',
    borderRadius: 5,
    padding: 5,
    width: 40,
    textAlign: 'center',
    marginHorizontal: 5,
    fontSize: 16,
    backgroundColor: '#fff',
  },
  scoreContainer: {
    backgroundColor: 'white',
    padding: 14,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#e2e8f0',
  },
  scoreLabel: { fontSize: 12, color: '#64748b', marginBottom: 4 },
  scoreValue: { fontSize: 20, fontWeight: '800', color: '#0f172a' },
});
