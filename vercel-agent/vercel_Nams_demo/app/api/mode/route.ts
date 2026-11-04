// Reports the NAMS_MODE the server was started with, so the header can show it.
export const dynamic = 'force-dynamic';

export async function GET() {
  return Response.json({ mode: (process.env.NAMS_MODE ?? 'provider').trim() });
}
