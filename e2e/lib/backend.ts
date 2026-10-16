/**
 * LG-055 backend fixture launcher (test setup, Node side).
 *
 * Starts the real Python FastAPI app + built frontend on an isolated temp root
 * and returns a handle the Playwright global setup/teardown can manage.  No
 * product model is called: the Python fixture injects a deterministic
 * responder and the environment sets the generation cap to 0.
 */
import { type ChildProcess, execFileSync, spawn } from 'node:child_process'
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  openSync,
  rmSync,
  symlinkSync,
} from 'node:fs'
import { createServer } from 'node:net'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

export const repoRoot = join(dirname(fileURLToPath(import.meta.url)), '..', '..')
export const e2eRoot = join(repoRoot, 'e2e')
export const runtimeDir = join(e2eRoot, '.runtime')
export const frontendDir = join(repoRoot, 'frontend')
export const frontendDist = join(frontendDir, 'dist')

export type BackendMode = 'team' | 'single' | 'stale'

export interface BackendHandle {
  mode: BackendMode
  url: string
  dataDir: string
  logPath: string
  stop: () => Promise<void>
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

/** The main worktree root (the first entry of `git worktree list`). */
function mainWorktreeRoot(): string | null {
  try {
    const output = execFileSync(
      'git',
      ['-C', repoRoot, 'worktree', 'list', '--porcelain'],
      { encoding: 'utf8' },
    )
    const line = output.split('\n').find((entry) => entry.startsWith('worktree '))
    return line ? line.slice('worktree '.length).trim() : null
  } catch {
    return null
  }
}

/**
 * Prefer an explicit interpreter, then any `.venv` in this worktree or the
 * main worktree, then `python3`.  This lets an isolated feature worktree reuse
 * the repository's existing installed backend dependencies without modifying
 * them.
 */
export function pythonBin(): string {
  const candidates = [
    process.env.LG_E2E_PYTHON,
    process.env.PYTHON_BIN,
    join(repoRoot, '.venv', 'bin', 'python'),
  ]
  const main = mainWorktreeRoot()
  if (main && main !== repoRoot) {
    candidates.push(join(main, '.venv', 'bin', 'python'))
  }
  for (const candidate of candidates) {
    if (candidate && existsSync(candidate)) return candidate
  }
  return 'python3'
}

export async function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = createServer()
    server.on('error', reject)
    server.listen(0, '127.0.0.1', () => {
      const address = server.address()
      const port = typeof address === 'object' && address ? address.port : 0
      server.close(() => resolve(port))
    })
  })
}

/** Whether a fixed loopback port is free (used for clear setup errors). */
export async function isPortFree(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const server = createServer()
    server.once('error', () => resolve(false))
    server.once('listening', () => server.close(() => resolve(true)))
    server.listen(port, '127.0.0.1')
  })
}

export async function waitForHealth(url: string, timeoutMs = 90_000): Promise<void> {
  const deadline = Date.now() + timeoutMs
  let lastError: unknown = null
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${url}/api/v1/health`)
      if (response.ok) {
        const body = (await response.json()) as { status?: string }
        if (body.status === 'ok') return
      }
      lastError = new Error(`health status ${response.status}`)
    } catch (error) {
      lastError = error
    }
    await sleep(250)
  }
  throw new Error(`backend at ${url} did not become healthy: ${String(lastError)}`)
}

/**
 * LG-062 isolation: the real backend fixture must never inherit real model or
 * provider credentials (e.g. an exported ``DEEPSEEK_API_KEY``) from the
 * developer shell.  The fixture uses a deterministic responder and
 * ``LIGHTGRAVITY_MAX_GENERATION_CALLS=0``; no credential is needed.  ``LG_E2E_*``
 * harness variables are preserved so nested launchers still work.
 */
const CREDENTIAL_ENV_PATTERN =
  /(api[_-]?key|token|secret|password|credential|deepseek|openai|anthropic|gemini|vertex)/i

export function sanitizedChildEnv(): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = {}
  for (const [key, value] of Object.entries(process.env)) {
    if (key.startsWith('LG_E2E_')) {
      env[key] = value
      continue
    }
    if (CREDENTIAL_ENV_PATTERN.test(key)) continue
    env[key] = value
  }
  return env
}

/** Reuse the main worktree's installed frontend deps via a read-only symlink. */
function ensureFrontendDeps(): void {
  const target = join(frontendDir, 'node_modules')
  if (existsSync(target)) return
  const main = mainWorktreeRoot()
  if (!main || main === repoRoot) return
  const source = join(main, 'frontend', 'node_modules')
  if (!existsSync(source)) return
  try {
    symlinkSync(source, target, 'dir')
  } catch {
    /* Best effort: a real install or PYTHON-style override may still work. */
  }
}

/** Build the real frontend once per run (skippable with LG_E2E_SKIP_BUILD=1). */
export function buildFrontend(): void {
  if (process.env.LG_E2E_SKIP_BUILD === '1') return
  ensureFrontendDeps()
  execFileSync('npm', ['--prefix', frontendDir, 'run', 'build'], {
    cwd: repoRoot,
    stdio: 'inherit',
  })
}

function waitForExit(child: ChildProcess, timeoutMs = 15_000): Promise<void> {
  if (child.exitCode !== null) return Promise.resolve()
  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      child.kill('SIGKILL')
      resolve()
    }, timeoutMs)
    child.once('exit', () => {
      clearTimeout(timer)
      resolve()
    })
  })
}

export interface StartBackendOptions {
  mode: BackendMode
  port?: number
}

export async function startBackend({ mode, port }: StartBackendOptions): Promise<BackendHandle> {
  mkdirSync(runtimeDir, { recursive: true })
  const resolvedPort = port ?? (await freePort())
  const url = `http://127.0.0.1:${resolvedPort}`
  const dataDir = mkdtempSync(join(tmpdir(), `lg051-e2e-${mode}-`))
  const logPath = join(runtimeDir, `backend-${mode}.log`)
  const logFd = openSync(logPath, 'a')

  const child = spawn(
    pythonBin(),
    [
      join(e2eRoot, 'backend', 'fixture_app.py'),
      '--mode',
      mode,
      '--port',
      String(resolvedPort),
      '--data-dir',
      dataDir,
      '--dist',
      frontendDist,
    ],
    {
      cwd: repoRoot,
      env: {
        ...sanitizedChildEnv(),
        PYTHONPATH: join(repoRoot, 'backend'),
        LIGHTGRAVITY_MAX_GENERATION_CALLS: '0',
      },
      stdio: ['ignore', logFd, logFd],
    },
  )

  try {
    await waitForHealth(url)
  } catch (error) {
    child.kill('SIGKILL')
    await waitForExit(child)
    rmSync(dataDir, { recursive: true, force: true })
    throw error
  }

  return {
    mode,
    url,
    dataDir,
    logPath,
    stop: async () => {
      child.kill('SIGTERM')
      await waitForExit(child)
      rmSync(dataDir, { recursive: true, force: true })
    },
  }
}
