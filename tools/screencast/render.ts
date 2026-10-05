import os from 'node:os'
import path from 'node:path'
import fs from 'node:fs'
import {QwenTtsProvider, Recast, type UrlBarConfig} from 'playwright-recast'

type TextRule = {pattern: string, flags?: string, replacement: string}

export interface RenderOptions {
    /** Extra spoken-text rules, after the shared ones */
    textRules?: TextRule[]
    /** Voice to clone: a clean recording of the narrator and its exact transcript */
    voice?: {sample: string, transcript: string}
    /** Click sound: a sound file, `true` for playwright-recast's own, `false` for none. Default: `true` */
    clickSound?: string | boolean
    /** Click sound volume, 0.0-1.0. Default: 0.2, a quarter of playwright-recast's */
    clickVolume?: number
    /** URL pill, e.g. on host changes. Default: only at showUrl() markers, so none without them */
    urlBar?: UrlBarConfig
}

const DEFAULT_VOICE = {
    sample: path.join(import.meta.dirname, 'voices', 'female-voice.wav'),
    transcript: "Welcome! In this screencast, we'll walk through the key concepts step by step. By the end, you'll have a solid understanding of how everything fits together.",
}
const pythonBin = path.join(os.homedir(), '.venvs', 'playwright-recast', 'bin', 'python3')

const isHidden = (action: {title?: string}) => action.title?.startsWith('hidden - ') ?? false

/** Renders every recording in ./playwright-output to ./screencast-output. OUTPUT_NAME overrides the file name. */
export async function renderScreencasts(options: RenderOptions = {}) {
    const voice = options.voice ?? DEFAULT_VOICE
    const clickSound = options.clickSound ?? true
    const inputRoot = './playwright-output'
    const outputRoot = './screencast-output'
    fs.mkdirSync(outputRoot, {recursive: true})

    const testDirs = fs.readdirSync(inputRoot, {withFileTypes: true})
        .filter(entry => entry.isDirectory())
        .map(entry => entry.name)

    for (const dirName of testDirs) {
        const inputDir = path.join(inputRoot, dirName)
        const name = process.env.OUTPUT_NAME ?? dirName

        if (!fs.existsSync(pythonBin)) throw new Error(`python3 not found at ${pythonBin}`)
        await Recast
            .from(inputDir)
            .parse()
            .hideSteps(isHidden)
            .speedUp({
                duringIdle: 3.0,
                duringUserAction: 1.0,
                rules: [{
                    name: 'human-pace-around-actions',
                    match: ctx => ctx.timeSinceLastAction < 1000 || ctx.timeUntilNextAction < 10000,
                    speed: 1.0,
                }],
            })
            .subtitlesFromTrace({format: 'srt'})
            .textProcessing({
                builtins: true,
                rules: [
                    {pattern: '_', flags: 'g', replacement: ' '},
                    // Speaks the Bolt port digit by digit, not as "seven thousand six
                    // hundred eighty-seven". Subtitles keep 7687.
                    {pattern: '\\b7687\\b', flags: 'g', replacement: 'seven six eight seven'},
                    ...options.textRules ?? [],
                ],
            })
            .urlBar(options.urlBar ?? {show: 'marked'})
            .render({
                format: 'mp4',
                resolution: '1440p',
                // Consecutive code lines are a few pixels apart; without this the
                // camera sways between code-line zooms.
                zoom: {panStabilizationThreshold: 0.3},
                embedSubtitles: {language: 'en', title: 'English', default: true},
                cursorOverlay: true,
            })
            .cursorOverlay({easing: 'ease-in-out', hideAfterMs: 5000})
            .clickEffect({
                sound: clickSound === false ? undefined : clickSound,
                soundVolume: options.clickVolume ?? 0.2,
            })
            .voiceover(QwenTtsProvider({
                mode: 'clone',
                voiceSample: voice.sample,
                refText: voice.transcript,
                cacheAudio: true,
                language: 'English',
                pythonBin,
            }))
            .toFile(path.join(outputRoot, name + '.mp4'))

        for (const file of fs.readdirSync(outputRoot)) {
            if (file.endsWith('.srt') || file.endsWith('.vtt') || file === 'recast-report.json') {
                fs.unlinkSync(path.join(outputRoot, file))
            }
        }
    }
}
