"use client";
import { useState, useEffect } from "react";

const CHALLENGES_LIST = [
  { name: "Wheelbarrow Race", url: "https://docs.google.com/spreadsheets/d/12XWCYO1ZQnaXqPCrHneu70BThHSja_hduYWnIFZxQYw/edit?gid=1990819987#gid=1990819987" },
  { name: "EcoPlate", url: "https://docs.google.com/spreadsheets/d/12XWCYO1ZQnaXqPCrHneu70BThHSja_hduYWnIFZxQYw/edit?gid=94782152#gid=94782152" },
  { name: "Memory Match", url: "https://docs.google.com/spreadsheets/d/12XWCYO1ZQnaXqPCrHneu70BThHSja_hduYWnIFZxQYw/edit?gid=2044892813#gid=2044892813" },
  { name: "Blind Pour", url: "https://docs.google.com/spreadsheets/d/12XWCYO1ZQnaXqPCrHneu70BThHSja_hduYWnIFZxQYw/edit?gid=1297792115#gid=1297792115" },
  { name: "Word Search", url: "https://docs.google.com/spreadsheets/d/12XWCYO1ZQnaXqPCrHneu70BThHSja_hduYWnIFZxQYw/edit?gid=1649707949#gid=1649707949" },
  { name: "Pop Quiz", url: "https://docs.google.com/spreadsheets/d/12XWCYO1ZQnaXqPCrHneu70BThHSja_hduYWnIFZxQYw/edit?gid=1022682713#gid=1022682713" },
  { name: "Electromagnetic", url: "https://docs.google.com/spreadsheets/d/12XWCYO1ZQnaXqPCrHneu70BThHSja_hduYWnIFZxQYw/edit?gid=1993434725#gid=1993434725" },
  { name: "Cup Toss Challenge", url: "https://docs.google.com/spreadsheets/d/12XWCYO1ZQnaXqPCrHneu70BThHSja_hduYWnIFZxQYw/edit?gid=1796908438#gid=1796908438" },
  { name: "Wheel It Right", url: "https://docs.google.com/spreadsheets/d/12XWCYO1ZQnaXqPCrHneu70BThHSja_hduYWnIFZxQYw/edit?gid=1859103238#gid=1859103238" },
  { name: "Charades / Pin the...", url: "https://docs.google.com/spreadsheets/d/12XWCYO1ZQnaXqPCrHneu70BThHSja_hduYWnIFZxQYw/edit?gid=1495608565#gid=1495608565" }
];

export default function Challenges() {
  const [participants, setParticipants] = useState<any[]>([]);
  const [equipo, setEquipo] = useState("");
  const [juez, setJuez] = useState("");
  const [selectedChallenge, setSelectedChallenge] = useState("");
  const [score, setScore] = useState("");
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    const fetchTeams = async () => {
      try {
        const WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbyPuwgHDjEGDk5HIVQD4AyEnguvZksDQ_HZcScslRM_BuH4fdWu27NPC3afXMyPhVWv/exec";
        const res = await fetch(`${WEBHOOK_URL}?action=getTeams&t=${Date.now()}`, { cache: "no-store" });
        const data = await res.json();
        
        // Convert array of Objects to { nombre: "Team Name" }
        const teamNames = data.map((row: any) => {
          const key = Object.keys(row)[0];
          return { nombre: row[key] };
        }).filter((t: any) => t.nombre);
        
        setParticipants(teamNames);
      } catch (error) {
        console.error("Error fetching teams from Google Sheets:", error);
      }
    };
    fetchTeams();
  }, []);

  const handleSubmit = async (e: any) => {
    e.preventDefault();
    if (!selectedChallenge) {
      setMsg("❌ Please select a challenge from the list.");
      return;
    }
    if (!juez) {
      setMsg("❌ Please select a judge.");
      return;
    }
    setLoading(true);
    setMsg("");
    try {
      const WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbyPuwgHDjEGDk5HIVQD4AyEnguvZksDQ_HZcScslRM_BuH4fdWu27NPC3afXMyPhVWv/exec";
      // We will send this to Apps Script with action=logChallenge
      const payload = {
        action: "logChallenge",
        data: {
          equipo: equipo,
          reto: selectedChallenge,
          puntos: parseFloat(score),
          juez: juez
        }
      };

      const res = await fetch(WEBHOOK_URL, {
        method: "POST",
        headers: { "Content-Type": "text/plain;charset=utf-8" },
        body: JSON.stringify(payload)
      });
      
      const result = await res.json();
      if (result.status === "success") {
        setMsg("✅ Score registered successfully in Google Sheets!");
        setEquipo("");
        setSelectedChallenge("");
        setScore("");
        setJuez(""); // Optional reset
      } else {
        setMsg("❌ Error from Google Sheets: " + (result.message || "Unknown error"));
      }
    } catch (err) {
      setMsg("❌ Connection error to Google Sheets.");
    }
    setLoading(false);
  };

  return (
    <div>
      <h1 style={{ fontSize: '2.5rem', marginBottom: '2rem', fontWeight: 800, textAlign: 'center' }}>Challenges Evaluation</h1>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2rem', alignItems: 'start' }}>
        
        {/* Panel 1: Challenges List */}
        <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 600, color: '#3b82f6', marginBottom: '1rem' }}>Select Challenge</h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '400px', overflowY: 'auto', paddingRight: '10px' }}>
            {CHALLENGES_LIST.map((challenge, idx) => (
              <div 
                key={idx} 
                onClick={() => setSelectedChallenge(challenge.name)}
                style={{
                  padding: '12px 16px',
                  background: selectedChallenge === challenge.name ? 'rgba(59, 130, 246, 0.3)' : 'rgba(255, 255, 255, 0.05)',
                  border: selectedChallenge === challenge.name ? '1px solid #3b82f6' : '1px solid var(--glass-border)',
                  borderRadius: '8px',
                  cursor: 'pointer',
                  transition: 'all 0.2s ease',
                  fontWeight: selectedChallenge === challenge.name ? 'bold' : 'normal',
                  color: selectedChallenge === challenge.name ? '#60a5fa' : 'var(--text-main)',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center'
                }}
              >
                <span>{challenge.name}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Panel 2: Form */}
        <div className="glass-panel" style={{ position: 'sticky', top: '100px' }}>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 600, color: '#10b981', marginBottom: '1.5rem' }}>Assign Score</h2>
          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <label style={{ fontWeight: 600, color: '#cbd5e1' }}>Target Team:</label>
              <select 
                className="input-glass" 
                style={{ fontSize: '1.2rem', padding: '12px', background: 'rgba(0,0,0,0.5)' }}
                value={equipo} 
                onChange={e => setEquipo(e.target.value)} 
                required 
              >
                <option value="" disabled>Select a team...</option>
                {participants.map((p, idx) => (
                  <option key={p.nombre || idx} value={p.nombre}>{p.nombre}</option>
                ))}
              </select>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <label style={{ fontWeight: 600, color: '#cbd5e1' }}>Select Judge:</label>
              <select 
                className="input-glass" 
                style={{ fontSize: '1.2rem', padding: '12px', background: 'rgba(0,0,0,0.5)' }}
                value={juez} 
                onChange={e => setJuez(e.target.value)} 
                required 
              >
                <option value="" disabled>Select a judge...</option>
                <option value="Juez 1">Juez 1</option>
                <option value="Juez 2">Juez 2</option>
                <option value="Juez 3">Juez 3</option>
                <option value="Juez 4">Juez 4</option>
                <option value="Juez 5">Juez 5</option>
              </select>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <label style={{ fontWeight: 600, color: '#cbd5e1' }}>Selected Challenge:</label>
              <div style={{ 
                padding: '12px', 
                background: 'rgba(0,0,0,0.3)', 
                borderRadius: '8px', 
                color: selectedChallenge ? '#60a5fa' : '#64748b',
                fontStyle: selectedChallenge ? 'normal' : 'italic'
              }}>
                {selectedChallenge || "None"}
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <label style={{ fontWeight: 600, color: '#cbd5e1' }}>Score:</label>
              <input 
                className="input-glass" 
                type="number" 
                step="0.5" 
                style={{ fontSize: '1.5rem', padding: '12px', fontWeight: 'bold' }}
                value={score} 
                onChange={e => setScore(e.target.value)} 
                placeholder="0" 
                required 
              />
            </div>

            <button type="submit" className="btn-primary" disabled={loading} style={{ marginTop: '1rem', padding: '15px', fontSize: '1.1rem' }}>
              {loading ? "Sending..." : "SUBMIT SCORE"}
            </button>
          </form>
          {msg && <div style={{ marginTop: '1.5rem', textAlign: 'center', fontSize: '1.1rem', fontWeight: 'bold' }}>{msg}</div>}
        </div>

      </div>
    </div>
  );
}
