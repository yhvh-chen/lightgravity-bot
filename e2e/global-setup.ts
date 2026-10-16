/**
 * LG-055 Playwright global setup.
 *
 * Builds the real frontend once, starts two isolated real backends (team and
 * single mode), and records their URLs for the workers.  The returned teardown
 * stops both processes and removes their temp roots.
 */
import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'

import {
  buildFrontend,
  isPortFree,
  runtimeDir,
  startBackend,
  type BackendHandle,
} from './lib/backend'

function portFor(name: 'team' | 'single', fallback: number): number {
  const raw = process.env[`LG_E2E_${name.toUpperCase()}_PORT`]
  return raw ? Number(raw) : fallback
}

export default async function globalSetup(): Promise<() => Promise<void>> {
  buildFrontend()
  mkdirSync(runtimeDir, { recursive: true })

  const teamPort = portFor('team', 8791)
  const singlePort = portFor('single', 8792)
  for (const [name, port] of [
    ['team', teamPort],
    ['single', singlePort],
  ] as const) {
    if (!(await isPortFree(port))) {
      throw new Error(
        `LG-055 e2e port ${port} (${name}) is already in use; ` +
          `set LG_E2E_${name.toUpperCase()}_PORT to a free port`,
      )
    }
  }

  const handles: BackendHandle[] = []
  const team = await startBackend({ mode: 'team', port: teamPort })
  handles.push(team)
  const single = await startBackend({ mode: 'single', port: singlePort })
  handles.push(single)

  const urls = { team: team.url, single: single.url }
  writeFileSync(join(runtimeDir, 'servers.json'), JSON.stringify(urls, null, 2))
  process.env.LG_E2E_TEAM_URL = team.url
  process.env.LG_E2E_SINGLE_URL = single.url

  return async () => {
    for (const handle of handles) {
      await handle.stop()
    }
  }
}
