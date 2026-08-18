import type { Metadata } from 'next';
import '@neo4j-ndl/base/lib/neo4j-ds-styles.css';
import './globals.css';

export const metadata: Metadata = {
  title: 'NAMS Chat — Neo4j Memory Provider',
  description: 'Vercel AI SDK + direct Neo4j memory (self-hosted NAMS)',
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