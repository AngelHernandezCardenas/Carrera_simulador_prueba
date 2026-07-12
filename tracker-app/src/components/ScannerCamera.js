import React, { useState, useEffect, useRef } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Animated, Easing } from 'react-native';
import { CameraView } from 'expo-camera';

export default function ScannerCamera({
  cameraRef,
  contandoActivo,
  detectedBalls,
  onScanOnce,
  onOpenGallery,
}) {
  const [isCameraReady, setIsCameraReady] = useState(false);
  const [cameraLayout, setCameraLayout] = useState(null);
  const [visibleColors, setVisibleColors] = useState(['Rojo', 'Blanco', 'Negro']);
  
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

  return (
    <View style={{ flex: 1 }}>
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
      <View>
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
        <View style={{ flexDirection: 'row' }}>
          <TouchableOpacity style={[styles.button, { flex: 1, backgroundColor: '#8e44ad', alignItems: 'center', marginBottom: 0 }]} onPress={onOpenGallery}>
            <Text style={styles.buttonText}>Gallery</Text>
          </TouchableOpacity>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
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
  buttonText: {
    color: '#ffffff',
    fontSize: 16,
    fontWeight: 'bold',
    fontFamily: 'Times New Roman',
    textAlign: 'center',
  },
});

