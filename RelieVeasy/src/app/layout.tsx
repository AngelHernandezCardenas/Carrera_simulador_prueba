import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { ThemeProvider } from "./theme-provider";
import { ThemeToggle } from "./components/ThemeToggle";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "RelieVeasy Control Center",
  description: "Advanced simulator control dashboard",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={inter.className}>
        <ThemeProvider attribute="class" defaultTheme="light" enableSystem={false}>
          <nav style={{ padding: '1rem 2rem', borderBottom: '1px solid var(--border-color)', display: 'flex', gap: '20px', alignItems: 'center', background: 'var(--nav-bg)', backdropFilter: 'blur(10px)', position: 'sticky', top: 0, zIndex: 50 }}>
            <div style={{ fontSize: '1.25rem', fontWeight: 'bold', color: 'var(--text-main)', marginRight: '2rem' }}>
              <span style={{color: '#3b82f6'}}>Relie</span>Veasy
            </div>
            <a href="/challenges" className="nav-link">Challenges</a>
            <a href="/logs" className="nav-link">Database Logs</a>
            <div style={{ marginLeft: 'auto' }}>
              <ThemeToggle />
            </div>
          </nav>
          <main style={{ padding: '2rem', maxWidth: '1400px', margin: '0 auto' }}>
            {children}
          </main>
        </ThemeProvider>
      </body>
    </html>
  );
}
