/**
 * LG-112 QA global setup: starts the real candidate app on isolated loopback
 * ports with fresh temp data and a controlled fake protocol upstream.
 *
 * No product service (8123/5173/18123), user data, real key or vendor is used.
 */
import { execFileSync, spawn, type ChildProcess } from 'node:child_process'
import { existsSync, mkdirSync, mkdtempSync, openSync, readFileSync, writeFileSync } from 'node:fs'
import { createServer } from 'node:net'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const qaDir = dirname(fileURLToPath(import.meta.url))
const repoRoot = join(qaDir, '..', '..', '..')
const runtimeDir = join(qaDir, '.runtime')
const logDir = join(qaDir, 'logs')

const CREDENTIAL_ENV_PATTERN =
  /(api[_-]?key|token|secret|password|credential|deepseek|openai|anthropic|gemini|vertex|google_application)/i

function sanitizedEnv(): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = {}
  for (const [key, value] of Object.entries(process.env)) {
    if (CREDENTIAL_ENV_PATTERN.test(key)) continue
    if (key === 'LIGHTGRAVITY_MAX_GENERATION_CALLS') continue
    if (key === 'LIGHTGRAVITY_DATA_DIR' || key === 'LIGHTGRAVITY_SECRET_STORE') continue
    env[key] = value
  }
  return env
}

function freePort(): Promise<number> {
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

async function waitForHealth(baseUrl: string, timeoutMs = 90_000): Promise<void> {
  const deadline = Date.now() + timeoutMs
  let last: unknown = null
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${baseUrl}/api/v1/health`)
      if (response.ok) {
        const body = (await response.json()) as { status?: string }
        if (body.status === 'ok') return
      }
      last = new Error(`status ${response.status}`)
    } catch (error) {
      last = error
    }
    await new Promise((resolve) => setTimeout(resolve, 200))
  }
  throw new Error(`QA app did not become healthy: ${String(last)}`)
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

export default async function globalSetup(): Promise<() => Promise<void>> {
  mkdirSync(runtimeDir, { recursive: true })
  mkdirSync(logDir, { recursive: true })
  const base = mkdtempSync(join(tmpdir(), 'lg112-playwright-qa-'))
  const dataDir = join(base, 'data')
  const runLogDir = join(base, 'logs')
  mkdirSync(runLogDir, { recursive: true })
  const port = await freePort()
  const upstreamPort = await freePort()
  const baseUrl = `http://127.0.0.1:${port}`
  const backendLog = join(logDir, 'browser-backend.log')
  const logFd = openSync(backendLog, 'a')

  let mainWorktree = repoRoot
  try {
    const listed = execFileSync('git', ['-C', repoRoot, 'worktree', 'list', '--porcelain'], {
      encoding: 'utf8',
    })
    const line = listed.split('\n').find((entry) => entry.startsWith('worktree '))
    if (line) mainWorktree = line.slice('worktree '.length).trim()
  } catch {
    /* keep repoRoot */
  }
  const pythonCandidates = [
    process.env.LG_QA_PYTHON,
    process.env.PYTHON_BIN,
    join(repoRoot, '.venv', 'bin', 'python'),
    join(mainWorktree, '.venv', 'bin', 'python'),
  ].filter(Boolean) as string[]
  const python = pythonCandidates.find((candidate) => existsSync(candidate)) ?? 'python3'

  const env = {
    ...sanitizedEnv(),
    PYTHONPATH: join(repoRoot, 'backend') + ':' + qaDir,
  }

  const child = spawn(
    python,
    [
      join(qaDir, 'fixture_app.py'),
      '--port',
      String(port),
      '--upstream-port',
      String(upstreamPort),
      '--data-dir',
      dataDir,
      '--log-dir',
      runLogDir,
    ],
    {
      cwd: repoRoot,
      env,
      stdio: ['ignore', logFd, logFd],
    },
  )

  try {
    await waitForHealth(baseUrl)
  } catch (error) {
    child.kill('SIGKILL')
    await waitForExit(child)
    throw error
  }

  const seedPath = join(runLogDir, 'seed.json')
  const seed = existsSync(seedPath)
    ? (JSON.parse(readFileSync(seedPath, 'utf8')) as Record<string, unknown>)
    : {}
  const runtime = {
    baseUrl,
    dataDir,
    secretDir: join(dataDir, 'secrets'),
    logDir: runLogDir,
    requestLog: join(runLogDir, 'requests.jsonl'),
    upstreamLog: join(runLogDir, 'upstream.jsonl'),
    backendLog,
    upstreamBaseUrl: `http://127.0.0.1:${upstreamPort}`,
    seed,
  }
  writeFileSync(join(runtimeDir, 'runtime.json'), JSON.stringify(runtime, null, 2) + '\n')

  return async () => {
    child.kill('SIGTERM')
    await waitForExit(child)
    // Keep the temp evidence paths available to the QA driver; the report
    // records them explicitly and the operator can clean /tmp afterwards.
  }
}
