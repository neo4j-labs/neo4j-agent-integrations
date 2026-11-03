/** GET /api/mode — reports the NAMS_MODE the server was started with. */

import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { GET } from '../app/api/mode/route';

const savedMode = process.env.NAMS_MODE;

beforeEach(() => {
  delete process.env.NAMS_MODE;
});

afterEach(() => {
  if (savedMode === undefined) delete process.env.NAMS_MODE;
  else process.env.NAMS_MODE = savedMode;
});

describe('GET /api/mode', () => {
  it('reports the mode the server was started with', async () => {
    process.env.NAMS_MODE = 'tools';

    const res = await GET();

    expect(await res.json()).toEqual({ mode: 'tools' });
  });

  it('reports off when memory is off', async () => {
    process.env.NAMS_MODE = 'off';

    const res = await GET();

    expect(await res.json()).toEqual({ mode: 'off' });
  });

  it('defaults to provider when NAMS_MODE is unset', async () => {
    const res = await GET();

    expect(await res.json()).toEqual({ mode: 'provider' });
  });
});
