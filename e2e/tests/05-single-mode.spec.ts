/**
 * LG-055 single-user mode and explicit wrong-backend failure state.
 *
 * The single-mode backend is started by the global setup; the deliberately
 * outdated backend is started inside its own test so the explicit
 * incompatibility state can be observed without touching the main backends.
 */
import { expect, test } from '@playwright/test'

import { startBackend } from '../lib/backend'
import { singleUrl, uniqueToken } from '../lib/helpers'

test.describe('LG-055 single-user mode', () => {
  test('Personal is available and Team is a disabled, truthful entry', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto(`${singleUrl()}/?view=chat`)

    await expect(page.getByRole('banner')).toBeVisible()
    const personal = page.getByRole('tab', { name: 'Personal' })
    const team = page.getByRole('tab', { name: 'Team' })
    await expect(personal).toHaveAttribute('aria-selected', 'true')
    await expect(team).toBeDisabled()
    await expect(team).toHaveAttribute(
      'title',
      'Enable team mode on the backend to use the shared team conversation',
    )
    await expect(page.getByText(/Team mode is not enabled on this backend/)).toBeVisible()
    // Single-user Personal keeps the legacy Global label and is not chat-only.
    await expect(page.getByLabel('Message for Global')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Add attachments and materials' })).toBeVisible()
  })

  test('single-user global delivery and Files keep the task in Personal across refresh and back', async ({ page }) => {
    await page.goto(`${singleUrl()}/?view=chat`)
    const composer = page.getByLabel('Message for Global', { exact: true })
    await expect(composer).toBeVisible()
    const response = page.waitForResponse((reply) => reply.url().endsWith('/api/v1/conversations/global/messages') && reply.request().method() === 'POST')
    await composer.fill(`implement a new feature ${uniqueToken('single-delivery')}`)
    await composer.press('Enter')
    const sent = await response
    expect(sent.ok()).toBeTruthy()
    const outcome = await sent.json() as { task_id: string }
    expect(outcome.task_id).toBeTruthy()
    await expect(page.getByLabel(`Message for ${outcome.task_id}`, { exact: true })).toBeVisible()
    await expect(page.getByRole('tab', { name: 'Personal', exact: true })).toHaveAttribute('aria-selected', 'true')
    await expect(page.getByRole('tab', { name: 'Team', exact: true })).toBeDisabled()
    expect(new URL(page.url()).searchParams.get('channel')).toBe('personal')

    await page.getByRole('navigation', { name: 'Primary navigation' }).getByRole('button', { name: 'Files', exact: true }).click()
    const entry = page.getByRole('region', { name: 'Task directories' }).locator(`button[title="${outcome.task_id}"]`)
    await entry.click()
    await expect(page.getByLabel(`Message for ${outcome.task_id}`, { exact: true })).toBeVisible()
    await page.reload()
    await expect(page.getByLabel(`Message for ${outcome.task_id}`, { exact: true })).toBeVisible()
    await page.goBack()
    await expect(page.getByRole('heading', { name: 'Tasks /', exact: true })).toBeVisible()
  })

  test('single-user task chat still uploads and selects versioned material', async ({ page }) => {
    await page.goto(`${singleUrl()}/?view=chat`)
    await expect(page.getByRole('banner')).toBeVisible()
    // Use an absolute request URL: the default Playwright baseURL is the team server.
    const created = await page.request.post(`${singleUrl()}/api/v1/tasks`, { data: { request_id: uniqueToken('single-task'), title: uniqueToken('Single material task'), objective: 'Upload and select a versioned material in the single-user task conversation.' } })
    expect(created.ok()).toBeTruthy()
    const task = await created.json() as { task_id: string }
    await page.getByRole('button', { name: 'Files', exact: true }).click()
    await page.getByRole('region', { name: 'Task directories' }).locator(`button[title="${task.task_id}"]`).click()
    await expect(page.getByLabel(`Message for ${task.task_id}`, { exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Add attachments and materials', exact: true }).click()
    const filename = `${uniqueToken('single-source')}.md`
    const upload = page.waitForResponse((reply) => reply.url() === `${singleUrl()}/api/v1/sources` && reply.request().method() === 'POST')
    await page.getByLabel('Upload files to this conversation', { exact: true }).setInputFiles({ name: filename, mimeType: 'text/markdown', buffer: Buffer.from('# A single-user material\nText context for this task.') })
    const uploaded = await upload
    expect(uploaded.ok()).toBeTruthy()
    const source = (await uploaded.json()) as { source: { source_id: string; source_version: number } }
    expect(source.source.source_version).toBeGreaterThan(0)
    await page.getByRole('button', { name: 'Select materials', exact: true }).click()
    const row = page.getByRole('list', { name: 'Available materials' }).getByRole('listitem').filter({ hasText: source.source.source_id })
    await row.getByRole('checkbox').check()
    const selected = page.getByRole('list', { name: 'Selected source refs' })
    await expect(selected).toContainText(source.source.source_id)
    await expect(selected).toContainText(`v${source.source.source_version}`)
    await expect(page.getByRole('tab', { name: 'Personal', exact: true })).toHaveAttribute('aria-selected', 'true')
    await expect(page.getByRole('tab', { name: 'Team', exact: true })).toBeDisabled()
  })
})

test.describe('LG-055 wrong backend failure state', () => {
  test('an outdated backend is reported explicitly, not silently trusted', async ({ page }) => {
    const stale = await startBackend({ mode: 'stale' })
    try {
      await page.goto(`${stale.url}/?view=chat`)
      // The authentication discovery endpoint is missing on the old backend.
      await expect(page.getByText(/authentication discovery \/auth\/me is missing/)).toBeVisible()
      await expect(page.getByRole('navigation', { name: 'Primary navigation' })).toHaveCount(0)
      await expect(page.getByRole('main', { name: 'Sign in' })).toHaveCount(0)

      const health = await page.request.get(`${stale.url}/api/v1/health`)
      expect(((await health.json()) as { contract_version: string }).contract_version).toBe(
        '1.0.0',
      )
    } finally {
      await stale.stop()
    }
  })
})
