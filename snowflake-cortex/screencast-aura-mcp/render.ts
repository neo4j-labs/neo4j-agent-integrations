import fs from 'node:fs'
import {renderScreencasts} from '../../tools/screencast/render.ts'

// SCREENCAST_BLUR lives in ../screencast/.env, like the Snowflake sign-in.
for (const file of ['../screencast/.env', '.env']) if (fs.existsSync(file)) process.loadEnvFile(file)

await renderScreencasts({
    // At each showUrl() in the steps: where the screencast moves to another host.
    // The pill is drawn by the renderer, so the page's blur doesn't reach it.
    urlBar: {show: 'marked', durationMs: 4000, redact: process.env.SCREENCAST_BLUR?.split(',').filter(Boolean) ?? []},
    textRules: [
        // Hosts are spoken as "console dot neo4j dot io". Subtitles keep the dots.
        {pattern: '\\b([a-z0-9-]+)\\.(neo4j|snowflake)\\.(io|com)\\b', flags: 'g', replacement: '$1 dot $2 dot $3'},
    ],
})
