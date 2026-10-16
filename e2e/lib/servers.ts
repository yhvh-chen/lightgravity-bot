/** Resolve the isolated backend URLs started by `global-setup.ts`. */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

import { runtimeDir } from './backend'

export interface ServerUrls {
  team: string
  single: string
}

let cached: ServerUrls | null = null

export function servers(): ServerUrls {
  if (cached) return cached
  const envTeam = process.env.LG_E2E_TEAM_URL
  const envSingle = process.env.LG_E2E_SINGLE_URL
  if (envTeam && envSingle) {
    cached = { team: envTeam, single: envSingle }
    return cached
  }
  cached = JSON.parse(
    readFileSync(join(runtimeDir, 'servers.json'), 'utf8'),
  ) as ServerUrls
  return cached
}

export function teamUrl(): string {
  return servers().team
}

export function singleUrl(): string {
  return servers().single
}
