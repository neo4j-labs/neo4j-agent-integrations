// Asks whether memory is on, then which NAMS memory mode to run, then starts `next dev`.
import { spawn } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { stdin, stdout } from 'node:process';
import { createInterface } from 'node:readline/promises';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

const MODES = [
  { id: 'provider', blurb: 'createNamsProvider(): memory the model never sees' },
  { id: 'middleware', blurb: 'createNams().wrap(): the same, wrapping one model' },
  { id: 'tools', blurb: 'the model calls query_memory / store_memory itself' },
  { id: 'hooks', blurb: "the app's code loads and saves every turn, the model has no say" },
];
const ALL = [...MODES.map((m) => m.id), 'off'];

// The pick for this run, exported as NAMS_MODE to `next dev`. Files are never changed.
process.env.NAMS_MODE = await chooseMode();
announce(process.env.NAMS_MODE);

const nextBin = join(root, 'node_modules', 'next', 'dist', 'bin', 'next');
const child = spawn(process.execPath, [nextBin, 'dev', ...process.argv.slice(2)], {
  cwd: root,
  stdio: 'inherit',
  env: process.env,
});

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => child.kill(signal));
}
child.on('exit', (code, signal) => {
  process.exit(code ?? (signal ? 1 : 0));
});

async function chooseMode() {
  const fromEnv = (process.env.NAMS_MODE ?? readEnvVar('NAMS_MODE') ?? 'provider').trim().toLowerCase();
  const current = ALL.includes(fromEnv) ? fromEnv : 'provider';

  // No terminal (CI, piped input): use the environment as-is.
  if (!stdin.isTTY) return current;

  const currentChoice = MODES.find((m) => m.id === current) ?? MODES[0];
  const rl = createInterface({ input: stdin, output: stdout });
  rl.on('SIGINT', () => {
    rl.close();
    process.exit(130);
  });
  // Ctrl+D mid-prompt keeps the current mode.
  const ask = (q) => rl.question(q).then((s) => s.trim().toLowerCase(), () => null);

  try {
    const onByDefault = current !== 'off';
    const answer = await ask(`\n  Memory on? ${onByDefault ? '[Y/n]' : '[y/N]'} `);
    if (answer === null) return current;
    const on = answer === '' ? onByDefault : answer.startsWith('y');
    if (!on) return 'off';

    console.log('\n  Which mode?');
    MODES.forEach((m, i) => {
      const here = m === currentChoice ? '  ← current' : '';
      console.log(`    ${i + 1}) ${m.id.padEnd(10)} ${m.blurb}${here}`);
    });
    const pick = await ask(`\n  Pick 1-${MODES.length} or a name [${currentChoice.id}] `);
    if (pick === null || pick === '') return currentChoice.id;

    const chosen = MODES.find((m, i) => String(i + 1) === pick || m.id === pick);
    if (chosen) return chosen.id;

    console.log(`  "${pick}" isn't one of them, using ${currentChoice.id}.`);
    return currentChoice.id;
  } finally {
    rl.close();
    stdin.pause();
  }
}

function announce(mode) {
  if (mode === 'off') {
    console.log('\n  Memory: off. Each new chat starts from nothing.\n');
    return;
  }
  console.log(`\n  Memory: on · ${mode}  (NAMS_MODE=${mode})\n`);
  if (!process.env.NAMS_API_KEY && !readEnvVar('NAMS_API_KEY')) {
    console.log('  \x1b[33m⚠ NAMS_API_KEY is not set. Add it to .env.local before you chat.\x1b[0m\n');
  }
}

// Next.js reads .env.local before .env, so check them in that order.
function readEnvVar(key) {
  for (const file of ['.env.local', '.env']) {
    try {
      for (const line of readFileSync(join(root, file), 'utf8').split('\n')) {
        const match = line.replace(/\r$/, '').match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)$/);
        if (match && match[1] === key) return match[2].trim().replace(/^["']|["']$/g, '');
      }
    } catch {
      // no such file
    }
  }
  return undefined;
}
