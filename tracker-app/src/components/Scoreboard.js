import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, ActivityIndicator, Dimensions } from 'react-native';

const { width } = Dimensions.get('window');
const isMobile = width < 768;

export default function Scoreboard({ serverUrl }) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchScoreboard = async () => {
    try {
      setLoading(true);
      // Usamos la URL del Google Apps Script para obtener los datos directamente
      const scriptUrl = 'https://script.google.com/macros/s/AKfycbwcRWtZNa6_tv3r3i22esWhdYdQ9A-7aP4z1y6hInwM9gqclwdRJbNyQzrdsn5Vtuxk/exec';
      const response = await fetch(`${scriptUrl}?action=getScoreboard`);
      if (!response.ok) throw new Error('Network response was not ok');
      const text = await response.text();
      try {
        const json = JSON.parse(text);
        if (json.error) {
          throw new Error(json.error);
        }
        setData(json);
      } catch (err) {
        throw new Error("El script de Google no devolvió datos válidos. Asegúrate de tener la función doGet en tu Apps Script.");
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (serverUrl) {
      fetchScoreboard();
      const interval = setInterval(fetchScoreboard, 30000); // Poll every 30s
      return () => clearInterval(interval);
    } else {
      setLoading(false);
    }
  }, [serverUrl]);

  if (!serverUrl) {
    return (
      <View style={styles.center}>
        <Text style={styles.errorText}>Falta configurar la URL del servidor en la pantalla principal.</Text>
      </View>
    );
  }

  const leadingTeam = data.length > 0 ? data[0] : null;

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {/* HEADER */}
      <View style={styles.headerBox}>
        <Text style={styles.headerText}>LIVE RESULTS</Text>
      </View>

      {/* LEADING TEAM */}
      <View style={styles.subHeaderBox}>
        <Text style={styles.subHeaderText}>LEADING TEAM</Text>
      </View>

      {leadingTeam ? (
        <View style={styles.leadingContainer}>
          <Text style={styles.leadingTeamName}>{leadingTeam.Team}</Text>
          <View style={styles.leadingStatsContainer}>
            <View style={styles.leadingStatBox}>
              <Text style={styles.statLabel}>Loading</Text>
              <Text style={styles.statValue}>{leadingTeam['Load (%)']}</Text>
            </View>
            <View style={[styles.leadingStatBox, { backgroundColor: '#fef3c7' }]}>
              <Text style={[styles.statLabel, { color: '#b45309' }]}>POINTS</Text>
              <Text style={[styles.statValue, { color: '#b45309' }]}>{leadingTeam['Total (-/100)']}</Text>
            </View>
          </View>
        </View>
      ) : loading ? (
        <View style={styles.leadingContainer}><ActivityIndicator size="large" color="#0F8277" /></View>
      ) : (
        <View style={styles.leadingContainer}><Text>No data available</Text></View>
      )}

      {/* SCOREBOARD TABLE */}
      <View style={styles.headerBox}>
        <Text style={styles.headerText}>SCOREBOARD</Text>
      </View>

      {loading && data.length === 0 ? (
        <ActivityIndicator size="large" color="#1B2A47" style={{ marginTop: 20 }} />
      ) : error ? (
        <Text style={styles.errorText}>{error}</Text>
      ) : (
        <View style={styles.tableContainer}>
          {/* Table Header */}
          <View style={[styles.tableRow, styles.tableHeader]}>
            <Text style={[styles.tableCell, styles.headerCell, { flex: 0.5 }]}>Rank</Text>
            <Text style={[styles.tableCell, styles.headerCell, { flex: 1.5 }]}>Team</Text>
            {!isMobile && <Text style={[styles.tableCell, styles.headerCell]}>Load</Text>}
            {!isMobile && <Text style={[styles.tableCell, styles.headerCell]}>Energy</Text>}
            {!isMobile && <Text style={[styles.tableCell, styles.headerCell]}>Time</Text>}
            {!isMobile && <Text style={[styles.tableCell, styles.headerCell]}>Challenges</Text>}
            <Text style={[styles.tableCell, styles.headerCell, { flex: 1.2 }]}>Total</Text>
          </View>
          
          {/* Table Rows */}
          {data.map((row, idx) => (
            <View key={idx} style={[styles.tableRow, idx % 2 === 0 ? styles.rowEven : styles.rowOdd]}>
              <Text style={[styles.tableCell, { flex: 0.5, fontWeight: 'bold', color: '#1B2A47' }]}>{row.Rank}</Text>
              <Text style={[styles.tableCell, { flex: 1.5, fontWeight: 'bold' }]}>{row.Team}</Text>
              {!isMobile && <Text style={styles.tableCell}>{row['Load (%)']}</Text>}
              {!isMobile && <Text style={styles.tableCell}>{row['Energy (%)']}</Text>}
              {!isMobile && <Text style={styles.tableCell}>{row['Time (%)']}</Text>}
              {!isMobile && <Text style={styles.tableCell}>{row['Challenges (%)']}</Text>}
              <Text style={[styles.tableCell, { flex: 1.2, fontWeight: 'bold' }]}>{row['Total (-/100)']}</Text>
            </View>
          ))}
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F8FAFC',
  },
  content: {
    padding: 20,
    maxWidth: 1000,
    marginHorizontal: 'auto',
    width: '100%'
  },
  center: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20
  },
  headerBox: {
    backgroundColor: '#1B2A47',
    paddingVertical: 12,
    alignItems: 'center',
    marginTop: 20
  },
  headerText: {
    color: 'white',
    fontSize: 22,
    fontWeight: 'bold',
    letterSpacing: 1.5
  },
  subHeaderBox: {
    backgroundColor: '#0F8277',
    paddingVertical: 6,
    alignItems: 'center'
  },
  subHeaderText: {
    color: 'white',
    fontSize: 16,
    fontWeight: 'bold',
    letterSpacing: 1
  },
  leadingContainer: {
    backgroundColor: 'white',
    padding: 20,
    alignItems: 'center',
    borderBottomWidth: 1,
    borderLeftWidth: 1,
    borderRightWidth: 1,
    borderColor: '#E2E8F0',
    marginBottom: 20
  },
  leadingTeamName: {
    fontSize: 36,
    fontWeight: 'bold',
    color: '#1E293B',
    marginBottom: 20
  },
  leadingStatsContainer: {
    flexDirection: 'row',
    width: '100%',
    justifyContent: 'center',
    gap: 20
  },
  leadingStatBox: {
    flex: 1,
    backgroundColor: '#F1F5F9',
    padding: 15,
    alignItems: 'center',
    borderRadius: 8
  },
  statLabel: {
    fontSize: 14,
    fontWeight: 'bold',
    color: '#475569',
    marginBottom: 5,
    textTransform: 'uppercase'
  },
  statValue: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#0F172A'
  },
  tableContainer: {
    backgroundColor: 'white',
    borderWidth: 1,
    borderColor: '#E2E8F0',
    borderTopWidth: 0
  },
  tableRow: {
    flexDirection: 'row',
    borderBottomWidth: 1,
    borderColor: '#E2E8F0',
    paddingVertical: 12,
    paddingHorizontal: 10
  },
  tableHeader: {
    backgroundColor: '#E2E8F0',
    borderBottomWidth: 2,
    borderColor: '#CBD5E1'
  },
  rowEven: {
    backgroundColor: '#F8FAFC'
  },
  rowOdd: {
    backgroundColor: '#FFFFFF'
  },
  tableCell: {
    flex: 1,
    textAlign: 'center',
    fontSize: 14,
    color: '#334155'
  },
  headerCell: {
    fontWeight: 'bold',
    color: '#1E293B'
  },
  errorText: {
    color: '#EF4444',
    textAlign: 'center',
    margin: 20,
    fontSize: 16
  }
});
