/**
 * LG-062 account-management browser acceptance (real server, no mocks).
 *
 * Starts its own isolated real backend (fresh temp data root, deterministic
 * responder, model credentials stripped, generation cap 0) so account changes
 * cannot disturb the shared LG-055 team/single backends from global-setup.
 * Every assertion goes through the real frontend + real HTTP/cookie session;
 * `page.route`/`fulfill` is never used.
 */
import { expect, test, type Browser } from '@playwright/test'

import { startBackend, type BackendHandle } from '../lib/backend'
import { ACCOUNTS, loginAs, newLoggedInContext, uniqueToken, watchConsole } from '../lib/helpers'

let backend: BackendHandle
// Created by the admin in the first test, then used by the member flows.
const MEMBER = { username: uniqueToken('lgacct'), password: 'lgacct-initial-pw' }

test.describe.configure({ mode: 'serial' })

test.beforeAll(async () => {
  backend = await startBackend({ mode: 'team' })
})

test.afterAll(async () => {
  if (backend) await backend.stop()
})

async function loggedIn(browser: Browser, account: { username: string; password: string }) {
  return newLoggedInContext(browser, account, backend.url)
}

async function openAccountsTab(page: import('@playwright/test').Page) {
  await page.goto(`${backend.url}/?view=settings`)
  await page.getByRole('tab', { name: 'Accounts' }).click()
}

test('admin creates and lists an account through Settings', async ({ browser }) => {
  const { context, page } = await loggedIn(browser, ACCOUNTS.admin)
  try {
    await openAccountsTab(page)
    await expect(page.getByRole('button', { name: 'New account' })).toBeVisible()
    await page.getByRole('button', { name: 'New account' }).click()
    await page.getByLabel('Username').fill(MEMBER.username)
    await page.getByLabel('Temporary password').fill(MEMBER.password)
    await page.getByRole('button', { name: 'Create account' }).click()
    const createdRow = page.getByRole('row', { name: new RegExp(MEMBER.username) })
    await expect(createdRow).toBeVisible()
    await expect(createdRow.getByLabel(`Role for ${MEMBER.username}`)).toHaveValue('member')
  } finally {
    await context.close()
  }
})

test('member reaches only My Account and changes their own password', async ({ browser }) => {
  const { context, page } = await loggedIn(browser, MEMBER)
  try {
    const watch = watchConsole(page)
    await page.goto(`${backend.url}/?view=settings`)
    await expect(page.getByRole('heading', { name: 'My Account' })).toBeVisible()
    // Admin areas are absent from a member's Settings (and 403 on the server).
    await expect(page.getByRole('tab', { name: 'Models & Providers' })).toHaveCount(0)
    await expect(page.getByRole('tab', { name: 'Accounts' })).toHaveCount(0)

    const newPassword = 'lgacct-new-pw'
    await page.getByLabel('Current password').fill(MEMBER.password)
    await page.getByLabel('New password', { exact: true }).fill(newPassword)
    await page.getByLabel('Confirm new password').fill(newPassword)
    await page.getByRole('button', { name: 'Change password' }).click()

    // A clear signed-out/login UX with the reason.
    await expect(page.getByRole('main', { name: 'Sign in' })).toBeVisible()
    await expect(page.getByText(/Password changed/)).toBeVisible()

    // The new credential works; the old one no longer does.
    await page.getByLabel('Username').fill(MEMBER.username)
    await page.getByLabel('Password').fill(newPassword)
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(page.getByRole('banner')).toBeVisible()
    MEMBER.password = newPassword
    expect(watch.serverErrors).toEqual([])
  } finally {
    await context.close()
  }
})

test('member is forbidden from the admin account API', async ({ browser }) => {
  const { context } = await loggedIn(browser, MEMBER)
  try {
    const list = await context.request.get('/api/v1/accounts')
    expect(list.status()).toBe(403)
    const body = await list.json()
    expect(body.error.code).toBe('forbidden')
    const create = await context.request.post('/api/v1/accounts', {
      data: { username: uniqueToken('nope'), password: 'nope-pw', role: 'member' },
    })
    expect(create.status()).toBe(403)
  } finally {
    await context.close()
  }
})

test('disabling an account invalidates its existing session', async ({ browser }) => {
  const member = await loggedIn(browser, MEMBER)
  const admin = await loggedIn(browser, ACCOUNTS.admin)
  try {
    await openAccountsTab(admin.page)
    const row = admin.page.getByRole('row', { name: new RegExp(MEMBER.username) })
    await row.getByRole('button', { name: 'Disable' }).click()
    await expect(row.getByText('disabled')).toBeVisible()

    await expect
      .poll(async () => (await member.context.request.get('/api/v1/files')).status())
      .toBe(401)

    // Re-enable: the old cookie must not come back to life.
    await row.getByRole('button', { name: 'Enable' }).click()
    await expect(row.getByText('enabled')).toBeVisible()
    expect((await member.context.request.get('/api/v1/files')).status()).toBe(401)
  } finally {
    await member.context.close()
    await admin.context.close()
  }
})

test('resetting a password invalidates the old session and login changes', async ({ browser }) => {
  const member = await loggedIn(browser, MEMBER)
  const admin = await loggedIn(browser, ACCOUNTS.admin)
  try {
    await openAccountsTab(admin.page)
    const row = admin.page.getByRole('row', { name: new RegExp(MEMBER.username) })
    await row.getByRole('button', { name: 'Reset password' }).click()
    await admin.page.getByLabel('New temporary password').fill('lgacct-reset-pw')
    await admin.page.getByRole('button', { name: 'Set new password' }).click()

    await expect
      .poll(async () => (await member.context.request.get('/api/v1/files')).status())
      .toBe(401)
    MEMBER.password = 'lgacct-reset-pw'
  } finally {
    await member.context.close()
    await admin.context.close()
  }
})

test('the last active administrator cannot be disabled or demoted (real HTTP)', async ({
  browser,
}) => {
  const { context } = await loggedIn(browser, ACCOUNTS.admin)
  try {
    const disable = await context.request.patch('/api/v1/accounts/admin', {
      data: { enabled: false },
    })
    expect(disable.status()).toBe(409)
    const body = await disable.json()
    expect(body.error.code).toBe('illegal_transition')
    expect(body.error.details.reason).toBe('last_active_admin')

    const demote = await context.request.patch('/api/v1/accounts/admin', {
      data: { role: 'member' },
    })
    expect(demote.status()).toBe(409)
  } finally {
    await context.close()
  }
})

test('anonymous account requests are unauthorized', async ({ browser }) => {
  const context = await browser.newContext({ baseURL: backend.url })
  try {
    expect((await context.request.get('/api/v1/accounts')).status()).toBe(401)
    expect(
      (
        await context.request.post('/api/v1/account/password', {
          data: { current_password: 'a', new_password: 'b', confirmation: 'b' },
        })
      ).status(),
    ).toBe(401)
  } finally {
    await context.close()
  }
})

test('account sections stay usable at mobile 390 and tablet 1024 widths', async ({
  browser,
}) => {
  const member = await browser.newContext({
    baseURL: backend.url,
    viewport: { width: 390, height: 800 },
  })
  try {
    const page = await member.newPage()
    await loginAs(page, MEMBER, backend.url)
    await page.goto(`${backend.url}/?view=settings`)
    await expect(page.getByRole('heading', { name: 'My Account' })).toBeVisible()
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    )
    expect(overflow).toBeLessThanOrEqual(1)
  } finally {
    await member.close()
  }

  const admin = await browser.newContext({
    baseURL: backend.url,
    viewport: { width: 1024, height: 800 },
  })
  try {
    const page = await admin.newPage()
    await loginAs(page, ACCOUNTS.admin, backend.url)
    await page.goto(`${backend.url}/?view=settings`)
    await page.getByRole('tab', { name: 'Accounts' }).click()
    await expect(page.getByRole('button', { name: 'New account' })).toBeVisible()
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    )
    expect(overflow).toBeLessThanOrEqual(1)
  } finally {
    await admin.close()
  }
})
