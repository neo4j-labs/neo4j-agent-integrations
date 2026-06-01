import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'Vercel AI SDK + Neo4j Agent Memory',
  description: 'Streaming chat with persistent research memory backed by Neo4j',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="bg-slate-900 text-white antialiased">{children}</body>
    </html>
  );
}
