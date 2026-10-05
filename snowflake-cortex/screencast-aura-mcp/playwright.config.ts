import fs from 'node:fs'
import {screencastConfig} from '../../tools/screencast/config.ts'

// The Snowflake sign-in is shared with ../screencast; this directory's .env
// adds the Aura values and may override the rest.
if (fs.existsSync('../screencast/.env')) process.loadEnvFile('../screencast/.env')

export default screencastConfig()
