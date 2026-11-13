import ChatShell from '@/components/chat/ChatShell';
import { CHAT_MODES, memoryMode, rawMode } from '@/lib/mode';

// Read NAMS_MODE on every request, never at build time.
export const dynamic = 'force-dynamic';

export default function HomePage() {
  const mode = memoryMode();
  if (!mode) {
    return (
      <p style={{ padding: 24 }}>
        Unknown NAMS_MODE &quot;{rawMode()}&quot;. Use {CHAT_MODES.join(', ')}, or start the app with npm run dev.
      </p>
    );
  }
  return <ChatShell mode={mode} />;
}
