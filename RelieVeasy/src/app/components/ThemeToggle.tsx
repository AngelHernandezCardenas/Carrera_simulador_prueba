"use client"

import * as React from "react"
import { useTheme } from "next-themes"

export function ThemeToggle() {
  const { theme, setTheme } = useTheme()
  const [mounted, setMounted] = React.useState(false)

  // Ensure component is mounted to avoid hydration mismatch
  React.useEffect(() => {
    setMounted(true)
  }, [])

  if (!mounted) {
    return <button style={toggleStyle}>◐</button>
  }

  return (
    <button
      onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
      style={toggleStyle}
      title="Toggle Theme"
    >
      {theme === "dark" ? "🌙" : "☀️"}
    </button>
  )
}

const toggleStyle = {
  background: 'transparent',
  border: '1px solid var(--border-color)',
  borderRadius: '50%',
  width: '40px',
  height: '40px',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  fontSize: '1.2rem',
  cursor: 'pointer',
  color: 'var(--text-main)',
  transition: 'all 0.2s ease',
}
