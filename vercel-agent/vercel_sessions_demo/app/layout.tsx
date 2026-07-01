
import type { Metadata } from 'next';
import '@neo4j-ndl/base/lib/neo4j-ds-styles.css';
import './globals.css';

export const metadata: Metadata = {
  title: 'Neo4j AI Chat',
  description: 'Vercel AI SDK + Neo4j agent memory + NDL components',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, fontFamily: 'sans-serif' }}>
        {children}
      </body>
    </html>
  );
}
