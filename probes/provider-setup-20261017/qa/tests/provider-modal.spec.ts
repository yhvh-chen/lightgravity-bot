/**
 * LG-112 independent real-browser acceptance for the LG-104 provider milestone.
 *
 * Every request goes to the real candidate FastAPI app + built frontend over
 * HTTP, with fresh temp data and fixed fake accounts.  The only protocol double
 * is the isolated loopback fake OpenAI/Gemini upstream described in the QA
 * report; it is never a real vendor.  No page.route/fulfill or mocked API is
 * used.
 */
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

const specDir = dirname(fileURLToPath(import.meta.url))
const qaDir = join(specDir, '..')
const screenshots = join(qaDir, 'screenshots')

interface Runtime {
  baseUrl: string
  dataDir: string
  secretDir: string
  logDir: string
  requestLog: string
  upstreamLog: string
  backendLog: string
  upstreamBaseUrl: string
  seed: Record<string, unknown>
}

let cachedRuntime: Runtime | null = null
function runtime(): Runtime {
  if (cachedRuntime) return cachedRuntime
  cachedRuntime = JSON.parse(
    readFileSync(join(qaDir, '.runtime', 'runtime.json'), 'utf8'),
  ) as Runtime
  return cachedRuntime
}

const ACCOUNTS = {
  admin: { username: 'qa-admin', password: 'qa-admin-pw' },
  member: { username: 'qa-member', password: 'qa-member-pw' },
} as const

async function loginAs(
  page: Page,
  account: { username: string; password: string },
): Promise<void> {
  await page.goto(`${runtime().baseUrl}/?view=chat`)
  const gate = page.getByRole('main', { name: 'Sign in' })
  await expect(gate).toBeVisible()
  await page.getByLabel('Username').fill(account.username)
  await page.getByLabel('Password').fill(account.password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('main', { name: 'Sign in' })).toBeHidden()
  await expect(page.getByRole('banner')).toBeVisible()
}

async function openSettings(page: Page, query = ''): Promise<void> {
  await page.goto(`${runtime().baseUrl}/?view=settings${query}`)
  await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible()
}

function dialog(page: Page) {
  return page.getByRole('dialog')
}

function field(page: Page, label: string) {
  const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return page
    .locator('.lg-field__label')
    .filter({ hasText: new RegExp(`^${escaped}$`) })
    .first()
    .locator('xpath=..')
    .locator('input, select')
    .first()
}

function row(page: Page, title: string) {
  return page.locator('.lg-connection-row').filter({ hasText: title })
}

function readJsonl(path: string): Array<Record<string, unknown>> {
  try {
    return readFileSync(path, 'utf8')
      .split('\n')
      .filter(Boolean)
      .flatMap((line) => {
        try {
          return [JSON.parse(line) as Record<string, unknown>]
        } catch {
          return []
        }
      })
  } catch {
    return []
  }
}

async function qaState(page: Page): Promise<{
  generation: { count: number; limit: number | null; corrupt: boolean }
  upstream_requests: number
  upstream_base_url: string
}> {
  const response = await page.request.get(`${runtime().baseUrl}/__qa__/state`)
  expect(response.ok(), await response.text()).toBeTruthy()
  return (await response.json()) as {
    generation: { count: number; limit: number | null; corrupt: boolean }
    upstream_requests: number
    upstream_base_url: string
  }
}

function settingsRequestsSince(records: Array<Record<string, unknown>>, index: number) {
  return records.slice(index).filter((entry) => String(entry.path).startsWith('/api/v1/settings'))
}

function unique(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
}

test.describe.configure({ mode: 'serial' })

test('landing, compact modal, deep links, responsive widths, no always-open editor', async ({
  page,
}) => {
  const rt = runtime()
  await page.setViewportSize({ width: 1440, height: 900 })
  await loginAs(page, ACCOUNTS.admin)
  await openSettings(page)

  await expect(row(page, 'QA custom loopback')).toBeVisible()
  await expect(dialog(page)).toHaveCount(0)
  await expect(page.getByText('Connections', { exact: true })).toBeVisible()

  // Defaults are a separate section, initially collapsed.
  const defaultsSummary = page.getByText('Default models', { exact: true }).first()
  await expect(defaultsSummary).toBeVisible()
  await defaultsSummary.click()
  await expect(page.locator('section[aria-label="Default models"]')).toBeVisible()
  await page.screenshot({ path: join(screenshots, '1440-settings-landing.png'), fullPage: true })

  // Deep link opens exactly the matching saved record once.
  const item = encodeURIComponent('settings:connection:qa-custom')
  await page.goto(
    `${rt.baseUrl}/?view=settings&item=${item}&task=task-qa-112&run=run-qa-112&channel=personal`,
  )
  const modal = dialog(page)
  await expect(modal).toBeVisible()
  await expect(modal.getByRole('heading', { name: 'Edit QA custom loopback' })).toBeVisible()
  const box = await modal.boundingBox()
  expect(box?.width ?? 0).toBeGreaterThanOrEqual(480)
  expect(box?.width ?? 0).toBeLessThanOrEqual(560)
  expect(page.url()).toContain('task=task-qa-112')
  expect(page.url()).toContain('run=run-qa-112')
  expect(page.url()).toContain('channel=personal')
  expect(page.url()).toContain('item=settings%3Aconnection%3Aqa-custom')

  // Escape closes without reopening and preserves the route context.
  await page.keyboard.press('Escape')
  await expect(modal).toBeHidden()
  await page.waitForTimeout(500)
  await expect(dialog(page)).toHaveCount(0)
  expect(page.url()).toContain('task=task-qa-112')
  expect(page.url()).toContain('run=run-qa-112')
  expect(page.url()).toContain('channel=personal')

  // Unknown stable target is a visible miss; no alternate connection selected.
  await page.goto(`${rt.baseUrl}/?view=settings&item=${encodeURIComponent('settings:connection:missing-qa-112')}`)
  await expect(page.getByText(/does not exist in this workspace/)).toBeVisible()
  await expect(dialog(page)).toHaveCount(0)
  await expect(page.locator('.lg-connection-row[aria-selected="true"]')).toHaveCount(0)
  await expect(row(page, 'QA custom loopback')).toBeVisible()

  // 1024 and 390 compact widths; controls visible and no horizontal overflow.
  await page.setViewportSize({ width: 1024, height: 900 })
  await openSettings(page)
  await page.getByRole('button', { name: 'New connection' }).first().click()
  let modalBox = await dialog(page).boundingBox()
  expect(modalBox?.width ?? 0).toBeGreaterThanOrEqual(480)
  expect(modalBox?.width ?? 0).toBeLessThanOrEqual(560)
  await page.screenshot({ path: join(screenshots, '1024-new-modal.png'), fullPage: true })
  await page.keyboard.press('Escape')

  await page.setViewportSize({ width: 390, height: 844 })
  await openSettings(page)
  await page.getByRole('button', { name: 'New connection' }).first().click()
  modalBox = await dialog(page).boundingBox()
  expect(modalBox?.width ?? 0).toBeGreaterThanOrEqual(360)
  expect(modalBox?.width ?? 0).toBeLessThanOrEqual(390)
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  expect(overflow).toBeLessThanOrEqual(1)
  await expect(dialog(page).getByRole('button', { name: 'Test connection' })).toBeVisible()
  await expect(dialog(page).getByRole('button', { name: 'Cancel' })).toBeVisible()
  await expect(dialog(page).getByRole('button', { name: 'Save connection' })).toBeVisible()
  await page.screenshot({ path: join(screenshots, '390-new-modal.png'), fullPage: true })
  await page.keyboard.press('Escape')
})

test('draft Test before Save: no writes, one minimal request, inline failure, stale, separate Save', async ({
  page,
}) => {
  const rt = runtime()
  const title = `QA New Custom ${unique('new')}`
  await page.setViewportSize({ width: 1440, height: 900 })
  await loginAs(page, ACCOUNTS.admin)
  await openSettings(page)

  const logBefore = readJsonl(rt.requestLog).length
  const stateBefore = await qaState(page)
  await page.getByRole('button', { name: 'New connection' }).first().click()
  const modal = dialog(page)
  await expect(modal).toBeVisible()

  await field(page, 'Provider').selectOption('custom-openai')
  await field(page, 'Name').fill(title)
  await field(page, 'Base URL').fill(`${rt.upstreamBaseUrl}/v1`)
  await field(page, 'API key (write-only)').fill('sk-browser-draft-not-real')
  await field(page, 'Model').fill('qa-echo')

  // Opening/selecting never sends a test or vendor request.
  expect((await qaState(page)).upstream_requests).toBe(stateBefore.upstream_requests)
  let newEntries = settingsRequestsSince(readJsonl(rt.requestLog), logBefore)
  expect(newEntries.filter((entry) => entry.path === '/api/v1/settings/connections/test-draft')).toHaveLength(0)

  await modal.getByRole('button', { name: 'Test connection' }).click()
  await expect(modal.locator('.lg-test__overall')).toContainText('verified')
  await expect(modal.locator('.lg-test__overall')).toContainText('draft · not saved')

  const stateAfterTest = await qaState(page)
  expect(stateAfterTest.upstream_requests - stateBefore.upstream_requests).toBe(1)
  newEntries = settingsRequestsSince(readJsonl(rt.requestLog), logBefore)
  expect(
    newEntries.filter((entry) => entry.path === '/api/v1/settings/connections/test-draft'),
  ).toHaveLength(1)
  expect(
    newEntries.filter(
      (entry) => entry.method === 'POST' && entry.path === '/api/v1/settings/connections',
    ),
  ).toHaveLength(0)
  expect(
    newEntries.filter((entry) => ['PATCH', 'DELETE'].includes(String(entry.method))),
  ).toHaveLength(0)

  const upstream = readJsonl(rt.upstreamLog).at(-1) ?? {}
  expect(String(upstream.path)).toBe('/v1/chat/completions')
  expect(String(upstream.authorization)).toBe('Bearer sk-browser-draft-not-real')
  const body = String(upstream.body)
  expect(body).toContain('"max_tokens": 1')
  expect(body).toContain('"stream": false')
  expect(body).not.toContain('"tools"')

  // Field edits invalidate the result immediately.
  await field(page, 'Model').fill('qa-echo-changed')
  await expect(modal.getByText('stale', { exact: true })).toBeVisible()
  await field(page, 'API key (write-only)').fill('sk-browser-changed-not-real')
  await expect(modal.getByText('stale', { exact: true })).toBeVisible()

  // Inline failure preserves the current inputs.
  await field(page, 'Model').fill('qa-fail-model')
  await modal.getByRole('button', { name: 'Test connection' }).click()
  await expect(modal.locator('.lg-test__overall')).toContainText('failed')
  await expect(field(page, 'Model')).toHaveValue('qa-fail-model')
  await expect(field(page, 'API key (write-only)')).toHaveValue('sk-browser-changed-not-real')
  await expect(modal.locator('.lg-test__overall')).not.toContainText('verified')
  await page.screenshot({ path: join(screenshots, '1440-inline-failure.png'), fullPage: true })

  // Save is independent of Test; it closes and selects the real new row.
  const stateBeforeSave = await qaState(page)
  await field(page, 'Model').fill('qa-echo')
  await modal.getByRole('button', { name: 'Save connection' }).click()
  await expect(dialog(page)).toBeHidden()
  await expect(row(page, title)).toBeVisible()
  await expect(row(page, title).getByText('Not tested')).toBeVisible()
  await expect(row(page, title).getByText(/verified/)).toHaveCount(0)

  const stateAfterSave = await qaState(page)
  expect(stateAfterSave.upstream_requests).toBe(stateBeforeSave.upstream_requests)
  newEntries = settingsRequestsSince(readJsonl(rt.requestLog), logBefore)
  expect(
    newEntries.filter(
      (entry) => entry.method === 'POST' && entry.path === '/api/v1/settings/connections',
    ),
  ).toHaveLength(1)
  const list = (await (await page.request.get(`${rt.baseUrl}/api/v1/settings/connections`)).json()) as {
    items: Array<{ id: string; title: string }>
  }
  const created = list.items.find((entry) => entry.title === title)
  expect(created).toBeTruthy()
  expect(await page.content()).not.toContain('sk-browser-changed-not-real')

  // A custom loopback host is not default-eligible.
  await page.getByText('Default models', { exact: true }).first().click()
  const options = await page
    .locator('section[aria-label="Default models"] select')
    .first()
    .locator('option')
    .evaluateAll((nodes) => nodes.map((node) => (node as HTMLOptionElement).value))
  expect(options).not.toContain(created?.id)
  await page.screenshot({ path: join(screenshots, '1440-saved-list.png'), fullPage: true })
})

test('Gemini/Vertex provider forms, installed SDK fake protocol, ADC honesty and blocked custom host', async ({
  page,
}) => {
  const rt = runtime()
  const geminiTitle = `QA Gemini ${unique('gemini')}`
  const vertexTitle = `QA Vertex ADC ${unique('vertex')}`
  await page.setViewportSize({ width: 1440, height: 900 })
  await loginAs(page, ACCOUNTS.admin)
  await openSettings(page)
  const logBefore = readJsonl(rt.requestLog).length
  const upstreamBefore = (await qaState(page)).upstream_requests

  // Gemini API: real installed SDK config + controlled loopback protocol.
  await page.getByRole('button', { name: 'New connection' }).first().click()
  let modal = dialog(page)
  await field(page, 'Provider').selectOption('gemini-api')
  await field(page, 'Name').fill(geminiTitle)
  await expect(field(page, 'Model')).toHaveValue('gemini-3.8-flash')
  await field(page, 'API key (write-only)').fill('sk-browser-gemini-not-real')
  await modal.getByRole('button', { name: 'Test connection' }).click()
  await expect(modal.locator('.lg-test__overall')).toContainText('verified')
  expect((await qaState(page)).upstream_requests - upstreamBefore).toBe(1)
  const geminiUpstream = readJsonl(rt.upstreamLog).at(-1) ?? {}
  expect(String(geminiUpstream.path)).toContain('/v1beta/models/gemini-3.8-flash:streamGenerateContent')
  expect(String(geminiUpstream.authorization)).toBe('sk-browser-gemini-not-real')
  await modal.getByRole('button', { name: 'Save connection' }).click()
  await expect(dialog(page)).toBeHidden()
  await expect(row(page, geminiTitle).getByText('Not tested')).toBeVisible()

  // Vertex Project + ADC without a real ADC prerequisite must not fake pass.
  await page.getByRole('button', { name: 'New connection' }).first().click()
  modal = dialog(page)
  await field(page, 'Provider').selectOption('vertex-adc')
  await field(page, 'Name').fill(vertexTitle)
  await field(page, 'Project ID').fill('qa-project')
  await field(page, 'Location').fill('us-central1')
  await modal.getByRole('button', { name: 'Test connection' }).click()
  await expect(modal.locator('.lg-test__overall')).toContainText('not_run')
  await expect(modal.locator('.lg-test__overall')).not.toContainText('verified')
  await modal.getByText('Layer details', { exact: true }).click()
  await expect(modal.getByText(/ADC prerequisite not detected/)).toBeVisible()
  await modal.getByRole('button', { name: 'Save connection' }).click()
  await expect(dialog(page)).toBeHidden()
  await expect(row(page, vertexTitle)).toBeVisible()

  // Arbitrary custom host is blocked honestly before network, preserving inputs.
  await page.getByRole('button', { name: 'New connection' }).first().click()
  modal = dialog(page)
  await field(page, 'Provider').selectOption('custom-openai')
  await field(page, 'Name').fill('QA blocked custom')
  await field(page, 'Base URL').fill('https://custom.invalid/v1')
  await field(page, 'API key (write-only)').fill('sk-browser-blocked-not-real')
  await field(page, 'Model').fill('qa-echo')
  const upstreamBeforeBlocked = (await qaState(page)).upstream_requests
  await modal.getByRole('button', { name: 'Test connection' }).click()
  await expect(modal.getByText(/not authorized/)).toBeVisible()
  await expect(field(page, 'Base URL')).toHaveValue('https://custom.invalid/v1')
  await expect(field(page, 'Model')).toHaveValue('qa-echo')
  expect((await qaState(page)).upstream_requests).toBe(upstreamBeforeBlocked)
  await page.screenshot({ path: join(screenshots, '1440-custom-host-blocked.png'), fullPage: true })

  // Dirty cancel must ask first and discard without writing.
  await modal.getByRole('button', { name: 'Cancel' }).click()
  await expect(modal.getByText(/Discard this unsaved draft and close/)).toBeVisible()
  const newEntries = settingsRequestsSince(readJsonl(rt.requestLog), logBefore)
  expect(
    newEntries.filter(
      (entry) => entry.method === 'POST' && entry.path === '/api/v1/settings/connections',
    ),
  ).toHaveLength(2) // gemini + vertex only
  await modal.getByRole('button', { name: 'Discard and close' }).click()
  await expect(dialog(page)).toBeHidden()
})

test('Edit key handling, dirty discard/keep, save keep, revision conflict, explicit remove', async ({
  page,
}) => {
  const rt = runtime()
  const id = `qa-edit-${Date.now().toString(36)}`
  const originalTitle = `QA edit key ${id}`
  await page.setViewportSize({ width: 1440, height: 900 })
  await loginAs(page, ACCOUNTS.admin)

  const createdResponse = await page.request.post(`${rt.baseUrl}/api/v1/settings/connections`, {
    data: {
      id,
      title: originalTitle,
      backend: 'openai-compat',
      model: 'qa-echo',
      base_url: `${rt.upstreamBaseUrl}/v1`,
      auth_mode: 'proxy_api_key',
      credential_ref: `${id}-key`,
      credential_value: 'sk-browser-edit-not-real',
    },
  })
  expect(createdResponse.status(), await createdResponse.text()).toBe(201)
  const created = (await createdResponse.json()) as {
    credential: { configured: boolean; version: string | null }
  }
  expect(created.credential.configured).toBe(true)

  await openSettings(page)
  const trigger = page.getByRole('button', { name: `Edit ${originalTitle}` })
  await trigger.click()
  const modal = dialog(page)
  await expect(modal.getByRole('heading', { name: `Edit ${originalTitle}` })).toBeVisible()
  await expect(field(page, 'API key (write-only)')).toHaveValue('')
  await expect(modal.getByText('Configured', { exact: true }).first()).toBeVisible()

  // Dirty Cancel asks inside the modal; Keep editing preserves fields.
  await field(page, 'Name').fill(`${originalTitle} dirty`)
  await modal.getByRole('button', { name: 'Cancel' }).click()
  await expect(modal.getByText(/Discard this unsaved draft and close/)).toBeVisible()
  await modal.getByRole('button', { name: 'Keep editing' }).click()
  await expect(field(page, 'Name')).toHaveValue(`${originalTitle} dirty`)
  // Discard closes with no writes.
  const logBeforeDiscard = readJsonl(rt.requestLog).length
  await modal.getByRole('button', { name: 'Cancel' }).click()
  await modal.getByRole('button', { name: 'Discard and close' }).click()
  await expect(dialog(page)).toBeHidden()
  const discardWrites = settingsRequestsSince(readJsonl(rt.requestLog), logBeforeDiscard).filter(
    (entry) => entry.method === 'PATCH' || entry.method === 'POST' || entry.method === 'DELETE',
  )
  expect(discardWrites).toHaveLength(0)
  await expect(row(page, originalTitle)).toBeVisible()
  await expect(row(page, `${originalTitle} dirty`)).toHaveCount(0)

  // Reopen: key stays blank/configured; empty key + Save keeps the same version.
  await page.getByRole('button', { name: `Edit ${originalTitle}` }).click()
  await expect(field(page, 'API key (write-only)')).toHaveValue('')
  await expect(dialog(page).getByText('Configured', { exact: true }).first()).toBeVisible()
  const savedTitle = `${originalTitle} saved`
  await field(page, 'Name').fill(savedTitle)
  await dialog(page).getByRole('button', { name: 'Save changes' }).click()
  await expect(dialog(page)).toBeHidden()
  await expect(row(page, savedTitle)).toBeVisible()
  const afterKeep = (await (
    await page.request.get(`${rt.baseUrl}/api/v1/settings/connections/${id}`)
  ).json()) as { credential: { configured: boolean; version: string | null }; revision: number }
  expect(afterKeep.credential.configured).toBe(true)
  expect(afterKeep.credential.version).toBe(created.credential.version)

  // Reopen and force a real revision conflict; draft fields stay in place.
  await page.getByRole('button', { name: `Edit ${savedTitle}` }).click()
  await expect(field(page, 'API key (write-only)')).toHaveValue('')
  await field(page, 'Name').fill(`${savedTitle} conflict draft`)
  const external = await page.request.patch(`${rt.baseUrl}/api/v1/settings/connections/${id}`, {
    data: { expected_revision: afterKeep.revision, title: `${savedTitle} external` },
  })
  expect(external.status(), await external.text()).toBe(200)
  const externalBody = (await external.json()) as { revision: number }
  await dialog(page).getByRole('button', { name: 'Save changes' }).click()
  await expect(dialog(page).getByText('Revision conflict')).toBeVisible()
  await expect(field(page, 'Name')).toHaveValue(`${savedTitle} conflict draft`)
  await expect(dialog(page)).toBeVisible()
  const afterConflict = (await (
    await page.request.get(`${rt.baseUrl}/api/v1/settings/connections/${id}`)
  ).json()) as { revision: number; title: string }
  expect(afterConflict.revision).toBe(externalBody.revision)
  expect(afterConflict.title).toBe(`${savedTitle} external`)
  await dialog(page).getByRole('button', { name: 'Cancel' }).click()
  await dialog(page).getByRole('button', { name: 'Discard and close' }).click()
  await expect(dialog(page)).toBeHidden()

  // Explicit replace then remove: replacement is write-only; remove is explicit.
  await page.getByRole('button', { name: `Edit ${savedTitle} external` }).click()
  await field(page, 'API key (write-only)').fill('sk-browser-replacement-not-real')
  await dialog(page).getByRole('button', { name: 'Save changes' }).click()
  await expect(dialog(page)).toBeHidden()
  const afterReplace = (await (
    await page.request.get(`${rt.baseUrl}/api/v1/settings/connections/${id}`)
  ).json()) as { credential: { configured: boolean; version: string | null } }
  expect(afterReplace.credential.configured).toBe(true)
  expect(afterReplace.credential.version).not.toBe(created.credential.version)

  await page.getByRole('button', { name: `Edit ${savedTitle} external` }).click()
  await dialog(page).getByText('Advanced', { exact: true }).click()
  await dialog(page).getByRole('button', { name: /Remove saved credential/ }).click()
  await dialog(page).getByRole('button', { name: 'Remove credential', exact: true }).click()
  await expect(dialog(page).getByText(/Credential removed/)).toBeVisible()
  const afterRemove = (await (
    await page.request.get(`${rt.baseUrl}/api/v1/settings/connections/${id}`)
  ).json()) as { credential: { configured: boolean } }
  expect(afterRemove.credential.configured).toBe(false)
})

test('focus trap, background inert, Escape focus return, late Test after close/reopen, narrow controls', async ({
  page,
}) => {
  const rt = runtime()
  await page.setViewportSize({ width: 1440, height: 900 })
  await loginAs(page, ACCOUNTS.admin)
  await openSettings(page)
  const trigger = page.getByRole('button', { name: 'Edit QA custom loopback' })
  await trigger.click()
  const modal = dialog(page)
  await expect(modal).toBeVisible()

  const bodyInert = await page.evaluate(() =>
    Array.from(document.body.children)
      .filter((element) => !element.classList.contains('lg-modal-backdrop'))
      .map((element) => ({
        tag: element.tagName,
        id: element.id,
        inert: element.hasAttribute('inert'),
        ariaHidden: element.getAttribute('aria-hidden'),
      })),
  )
  expect(bodyInert.some((entry) => entry.inert && entry.ariaHidden === 'true')).toBe(true)

  // Tab from the last focusable wraps to the first inside the dialog.
  await modal.evaluate((element) => {
    const selector =
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    const nodes = Array.from(element.querySelectorAll<HTMLElement>(selector))
    nodes[nodes.length - 1]?.focus()
  })
  await page.keyboard.press('Tab')
  expect(await page.evaluate(() => Boolean(document.querySelector('.lg-modal')?.contains(document.activeElement)))).toBe(true)

  // Clean Escape closes and returns focus to the trigger.
  await page.keyboard.press('Escape')
  await expect(dialog(page)).toBeHidden()
  await expect(trigger).toBeFocused()
  await page.waitForTimeout(400)
  await expect(dialog(page)).toHaveCount(0)

  // A late Test response after close/reopen must not fill a new draft or reopen.
  await trigger.click()
  await expect(dialog(page)).toBeVisible()
  await field(page, 'Model').fill('slow-model')
  await dialog(page).getByRole('button', { name: 'Test connection' }).click()
  await page.waitForTimeout(200)
  await dialog(page).getByRole('button', { name: 'Cancel' }).click()
  await expect(dialog(page).getByText(/Discard this unsaved draft and close/)).toBeVisible()
  await dialog(page).getByRole('button', { name: 'Discard and close' }).click()
  await expect(dialog(page)).toBeHidden()
  await page.waitForTimeout(2200)
  await expect(dialog(page)).toHaveCount(0)

  await page.getByRole('button', { name: 'Edit QA custom loopback' }).click()
  await page.waitForTimeout(2200)
  await expect(dialog(page)).toBeVisible()
  await expect(field(page, 'Model')).toHaveValue('qa-echo')
  await expect(dialog(page).locator('.lg-test__overall')).toHaveCount(0)
  await expect(page.getByRole('dialog').getByText('verified', { exact: true })).toHaveCount(0)

  await page.setViewportSize({ width: 390, height: 844 })
  await expect(dialog(page).getByRole('button', { name: 'Cancel' })).toBeVisible()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  expect(overflow).toBeLessThanOrEqual(1)
  await page.screenshot({ path: join(screenshots, '390-edit-modal.png'), fullPage: true })
  await page.keyboard.press('Escape')
  await expect(dialog(page)).toBeHidden()
})

test('saved last_test staleness, default eligibility, referenced delete block, UI delete success', async ({
  page,
}) => {
  const rt = runtime()
  const title = `QA deletable ${unique('delete')}`
  await page.setViewportSize({ width: 1440, height: 900 })
  await loginAs(page, ACCOUNTS.admin)
  await openSettings(page)

  // Seed qa-tested persisted a verified result; an edit makes it stale.
  await expect(row(page, 'QA saved tested').getByText(/verified/)).toBeVisible()
  await page.getByRole('button', { name: 'Edit QA saved tested' }).click()
  await field(page, 'Name').fill('QA saved tested edited')
  await dialog(page).getByRole('button', { name: 'Save changes' }).click()
  await expect(dialog(page)).toBeHidden()
  await expect(row(page, 'QA saved tested edited').getByText(/verified · stale/)).toBeVisible()

  // Defaults only list actual executable/host-eligible records.
  await page.getByText('Default models', { exact: true }).first().click()
  const defaultsSection = page.locator('section[aria-label="Default models"]')
  const optionValues = await defaultsSection
    .locator('select')
    .first()
    .locator('option')
    .evaluateAll((nodes) => nodes.map((node) => (node as HTMLOptionElement).value))
  expect(optionValues).toContain('qa-deepseek')
  expect(optionValues).not.toContain('qa-custom')
  expect(optionValues).not.toContain('qa-gemini')
  expect(optionValues).not.toContain('qa-tested')

  // Referenced record is blocked; the row/default/agent stay intact.
  await page.getByRole('button', { name: 'Delete QA DeepSeek eligible' }).click()
  const qaDeepseekRow = row(page, 'QA DeepSeek eligible')
  await qaDeepseekRow.getByRole('button', { name: 'Delete connection' }).click()
  await expect(qaDeepseekRow.getByText(/still referenced by/)).toBeVisible()
  await expect(qaDeepseekRow).toBeVisible()

  // Unreferenced UI delete succeeds and removes only that row.
  const created = await page.request.post(`${rt.baseUrl}/api/v1/settings/connections`, {
    data: {
      id: `qa-del-${Date.now().toString(36)}`,
      title,
      backend: 'openai-compat',
      model: 'deepseek-v4-flash',
      base_url: 'https://api.deepseek.com/v1',
      auth_mode: 'proxy_api_key',
      credential_ref: `qa-del-${Date.now().toString(36)}-key`,
      credential_value: 'sk-browser-delete-not-real',
    },
  })
  expect(created.status(), await created.text()).toBe(201)
  await page.reload()
  await expect(row(page, title)).toBeVisible()
  await page.getByRole('button', { name: `Delete ${title}` }).click()
  await row(page, title).getByRole('button', { name: 'Delete connection' }).click()
  await expect(row(page, title)).toHaveCount(0)
})

test('member My Account/admin notice without config fetch, endpoint 403/401, admin Accounts regression', async ({
  page,
  browser,
  request,
}) => {
  const rt = runtime()
  await page.setViewportSize({ width: 1440, height: 900 })
  await loginAs(page, ACCOUNTS.member)
  const logBefore = readJsonl(rt.requestLog).length
  await page.goto(
    `${rt.baseUrl}/?view=settings&item=${encodeURIComponent('settings:connection:qa-custom')}`,
  )
  await expect(page.getByText(/configuration is managed by administrators/)).toBeVisible()
  await expect(page.getByRole('heading', { name: 'My Account' })).toBeVisible()
  await expect(page.locator('.lg-settings-tabs')).toHaveCount(0)
  await expect(page.getByRole('tab', { name: 'Models & Providers' })).toHaveCount(0)
  await expect(page.locator('div[aria-label="My Account"]')).toBeVisible()
  await expect(page.getByText('qa-member').first()).toBeVisible()
  const memberEntries = settingsRequestsSince(readJsonl(rt.requestLog), logBefore)
  expect(memberEntries).toHaveLength(0)

  for (const [method, path, data] of [
    ['GET', '/api/v1/settings/connections', undefined],
    ['GET', '/api/v1/settings', undefined],
    ['POST', '/api/v1/settings/connections/test-draft', { connection: { backend: 'gemini', model: 'm' } }],
    ['DELETE', '/api/v1/settings/connections/qa-custom', { expected_revision: 0 }],
  ] as const) {
    const response = await page.request.fetch(`${rt.baseUrl}${path}`, { method, data })
    expect(response.status(), `${method} ${path}`).toBe(403)
  }
  const accounts = await page.request.get(`${rt.baseUrl}/api/v1/accounts`)
  expect(accounts.status()).toBe(403)

  for (const [method, path, data] of [
    ['GET', '/api/v1/settings/connections', undefined],
    ['POST', '/api/v1/settings/connections/test-draft', { connection: { backend: 'gemini', model: 'm' } }],
    ['DELETE', '/api/v1/settings/connections/qa-custom', { expected_revision: 0 }],
  ] as const) {
    const response = await request.fetch(`${rt.baseUrl}${path}`, { method, data })
    expect(response.status(), `anonymous ${method} ${path}`).toBe(401)
  }

  // Admin Accounts/My Account regression in a fresh context.
  const adminContext = await browser.newContext()
  const adminPage = await adminContext.newPage()
  try {
    await loginAs(adminPage, ACCOUNTS.admin)
    await openSettings(adminPage)
    await expect(adminPage.getByRole('tab', { name: 'Models & Providers' })).toBeVisible()
    await adminPage.getByRole('tab', { name: 'Accounts' }).click()
    await expect(adminPage.locator('div[aria-label="Accounts"]')).toBeVisible()
    await expect(adminPage.getByText('qa-admin').first()).toBeVisible()
    await expect(adminPage.getByText('qa-member').first()).toBeVisible()
    await adminPage.getByRole('tab', { name: 'My Account' }).click()
    await expect(adminPage.locator('div[aria-label="My Account"]')).toBeVisible()
    await expect(adminPage.getByText('qa-admin').first()).toBeVisible()
  } finally {
    await adminContext.close()
  }
})
