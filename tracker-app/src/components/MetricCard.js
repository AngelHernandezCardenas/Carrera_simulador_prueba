import React from 'react';
import { StyleSheet, Text, View, Platform } from 'react-native';

export default function MetricCard({ label, value, detail, full = false }) {
  return (
    <View style={full ? styles.cardFull : styles.cardHalf}>
      <Text style={styles.label}>{label}</Text>
      <Text style={styles.value} numberOfLines={2} adjustsFontSizeToFit>
        {value}
      </Text>
      <Text style={styles.detail}>{detail}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  cardHalf: {
    backgroundColor: '#ffffff',
    borderColor: '#e2e8f0',
    borderRadius: 8,
    borderWidth: 1,
    marginBottom: 10,
    minHeight: 112,
    padding: 12,
    width: '48.5%',
  },
  cardFull: {
    backgroundColor: '#ffffff',
    borderColor: '#e2e8f0',
    borderRadius: 8,
    borderWidth: 1,
    marginBottom: 10,
    minHeight: 104,
    padding: 12,
    width: '100%',
  },
  label: {
    color: '#64748b',
    fontSize: 12,
    fontWeight: '700',
    marginBottom: 6,
    textTransform: 'uppercase',
  },
  value: {
    color: '#0f172a',
    fontSize: 23,
    fontWeight: '900',
    lineHeight: 28,
  },
  detail: {
    color: '#475569',
    fontSize: 13,
    lineHeight: 18,
    marginTop: 5,
  },
});
