import type { Metadata } from 'next';
import '@neo4j-ndl/base/lib/neo4j-ds-styles.css';
import './globals.css';

export const metadata: Metadata = {
  title: 'NAMS Chat',
  description: 'A Vercel AI SDK chat that remembers you, backed by Neo4j Agent Memory (NAMS).',
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