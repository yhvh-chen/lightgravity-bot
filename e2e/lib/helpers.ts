/**
 * Shared LG-055 Playwright helpers.
 *
 * All helpers talk to the real isolated backends over HTTP.  No route mocking
 * (`page.route`/`fulfill`) is used anywhere: browser tests exercise the real
 * frontend build against real routes and real file/JSONL persistence.
 */
import { expect, type APIRequestContext, type Browser, type BrowserContext, type Page } from '@playwright/test'

import { singleUrl, teamUrl } from './servers'

export const ACCOUNTS = {
  admin: { username: 'admin', password: 'lg-admin-test-pw' },
  alice: { username: 'alice', password: 'lg-alice-test-pw' },
  bob: { username: 'bob', password: 'lg-bob-test-pw' },
} as const

export type AccountName = keyof typeof ACCOUNTS

export function uniqueToken(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

export { teamUrl, singleUrl }

/** Log in through the real login gate and wait for the workspace. */
export async function loginAs(
  page: Page,
  account: { username: string; password: string },
  base: string = teamUrl(),
): Promise<void> {
  await page.goto(`${base}/?view=chat`)
  const gate = page.getByRole('main', { name: 'Sign in' })
  await expect(gate).toBeVisible()
  await page.getByLabel('Username').fill(account.username)
  await page.getByLabel('Password').fill(account.password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  // Workspace is up when the top bar is visible and the gate is gone; this
  // works at any viewport (the left rail becomes a drawer on phones).
  await expect(page.getByRole('main', { name: 'Sign in' })).toBeHidden()
  await expect(page.getByRole('banner')).toBeVisible()
}

/** Create a new context whose API requests and pages share the session cookie. */
export async function newLoggedInContext(
  browser: Browser,
  account: { username: string; password: string },
  base: string = teamUrl(),
): Promise<{ context: BrowserContext; page: Page }> {
  const context = await browser.newContext({ baseURL: base })
  const page = await context.newPage()
  await loginAs(page, account, base)
  return { context, page }
}

/** Authenticate an APIRequestContext (no page needed). */
export async function loginApi(
  request: APIRequestContext,
  account: { username: string; password: string },
): Promise<void> {
  const response = await request.post('/api/v1/auth/login', { data: account })
  expect(response.status(), `login failed: ${await response.text()}`).toBe(200)
}

export interface ConsoleWatch {
  errors: string[]
  pageErrors: string[]
  serverErrors: string[]
  badRequests: string[]
}

const BENIGN_CONSOLE = [
  // The production build should not emit these, but tolerate dev-only noise.
  'Download the React DevTools',
  'ResizeObserver loop',
]

/** Watch a page for fatal console/page/5xx problems. */
export function watchConsole(page: Page): ConsoleWatch {
  const watch: ConsoleWatch = {
    errors: [],
    pageErrors: [],
    serverErrors: [],
    badRequests: [],
  }
  page.on('console', (message) => {
    if (message.type() !== 'error') return
    const text = message.text()
    if (BENIGN_CONSOLE.some((benign) => text.includes(benign))) return
    watch.errors.push(text)
  })
  page.on('pageerror', (error) => watch.pageErrors.push(error.message))
  page.on('response', (response) => {
    const url = response.url()
    if (!url.includes('/api/')) return
    if (response.status() >= 500) watch.serverErrors.push(`${response.status()} ${url}`)
    if (response.status() === 404) watch.badRequests.push(`404 ${url}`)
  })
  return watch
}

export interface TaskFixture {
  taskId: string
  title: string
}

export async function createTaskViaApi(
  request: APIRequestContext,
  options: { title: string; objective?: string; requestId?: string },
): Promise<TaskFixture> {
  const response = await request.post('/api/v1/tasks', {
    data: {
      request_id: options.requestId ?? uniqueToken('req-task'),
      title: options.title,
      objective: options.objective ?? options.title,
    },
  })
  expect(response.ok(), `create task failed: ${response.status()} ${await response.text()}`).toBeTruthy()
  const body = (await response.json()) as { task_id: string }
  return { taskId: body.task_id, title: options.title }
}

export interface SourceFixture {
  sourceId: string
  token: string
}

export async function createSourceViaApi(
  request: APIRequestContext,
  options: { filename: string; content: string; taskRef?: string; requestId?: string },
): Promise<SourceFixture> {
  const response = await request.post('/api/v1/sources', {
    data: {
      request_id: options.requestId ?? uniqueToken('req-source'),
      filename: options.filename,
      media_type: 'text/markdown',
      content_base64: Buffer.from(options.content, 'utf8').toString('base64'),
      scope: { task_ref: options.taskRef ?? null },
    },
  })
  expect(response.ok(), `create source failed: ${response.status()} ${await response.text()}`).toBeTruthy()
  const body = (await response.json()) as { source: { source_id: string } }
  return { sourceId: body.source.source_id, token: options.content }
}

/** Wait until a source's lexical search finds the token (real index write). */
export async function waitForSearchHit(
  request: APIRequestContext,
  query: string,
  taskRef?: string,
): Promise<void> {
  await expect
    .poll(
      async () => {
        const response = await request.get('/api/v1/search', {
          params: {
            q: query,
            include_global: 'true',
            limit: '20',
            rebuild_if_missing: 'true',
            ...(taskRef ? { task_ref: taskRef } : {}),
          },
        })
        if (!response.ok()) return 0
        const body = (await response.json()) as { hits?: unknown[] }
        return body.hits?.length ?? 0
      },
      { timeout: 20_000, intervals: [500, 1000, 2000] },
    )
    .toBeGreaterThan(0)
}
