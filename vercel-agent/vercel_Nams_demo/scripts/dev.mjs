// Asks whether memory is on, then which NAMS memory mode to run, then starts `next dev`.
import { spawn } from 'node:child_process';
import { dirname, join } from 'node:path';
import { createInterface } from 'node:readline/promises';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

const MODES = [
  { id: 'provider', blurb: 'A wrapper around the AI model. Adds memories before each answer and saves the turn after.' },
  { id: 'middleware', blurb: 'The same wrapper, placed on a model you already have.' },
  { id: 'tools', blurb: 'The AI model calls query_memory and store_memory itself. Memory calls show in the chat.' },
  { id: 'hooks', blurb: "This app's code loads the saved chat before each answer and saves every turn after." },
];

const DEFAULT_MODE = 'provider';

function parseChoice(answer) {
  const text = answer.trim().toLowerCase();
  const index = Number(text) - 1;
  if (Number.isInteger(index) && MODES[index]) return MODES[index].id;
  return MODES.find((mode) => mode.id === text)?.id ?? null;
}

async function askMemoryOn(rl) {
  for (;;) {
    const answer = (await rl.question('Memory on? [Y/n]: ')).trim().toLowerCase();
    if (answer === '' || answer === 'y' || answer === 'yes') return true;
    if (answer === 'n' || answer === 'no') return false;
    console.log(`Unknown answer "${answer}". Enter y or n.`);
  }
}

async function chooseMode() {
  const rl = createInterface({ input: process.stdin, output: process.stdout });
  rl.on('SIGINT', () => {
    rl.close();
    process.exit(130);
  });
  try {
    if (!(await askMemoryOn(rl))) return 'off';
    console.log('\nNAMS memory mode:');
    MODES.forEach((mode, i) => console.log(`  ${i + 1}) ${mode.id.padEnd(10)} ${mode.blurb}`));
    for (;;) {
      const answer = await rl.question(`Choose 1-${MODES.length} or a name [${DEFAULT_MODE}]: `);
      if (!answer.trim()) return DEFAULT_MODE;
      const choice = parseChoice(answer);
      if (choice) return choice;
      console.log(`Unknown choice "${answer.trim()}". Enter 1-${MODES.length} or ${MODES.map((m) => m.id).join(', ')}.`);
    }
  } finally {
    rl.close();
  }
}

process.env.NAMS_MODE = process.stdin.isTTY ? await chooseMode() : DEFAULT_MODE;
console.log(`\n[dev] NAMS_MODE=${process.env.NAMS_MODE}\n`);

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
