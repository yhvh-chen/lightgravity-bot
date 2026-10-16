/**
 * LG-055 meta, navigation, layout and responsive checks (real backend, real
 * built frontend).  No route mocking.
 */
import { expect, test } from '@playwright/test'

import { ACCOUNTS, loginAs, watchConsole } from '../lib/helpers'

const WORK_AND_RESOURCES = [
  'Chat',
  'Board',
  'Files',
  'Team',
  'Connections',
  'Session Profiles',
  'Hooks',
  'MCP',
  'Tools',
  'Triggers',
  'Skills',
]
const ALL_NAV = [...WORK_AND_RESOURCES, 'Settings']

async function navLabels(page: import('@playwright/test').Page): Promise<string[]> {
  return page
    .getByRole('navigation', { name: 'Primary navigation' })
    .getByRole('button')
    .evaluateAll((elements) =>
      elements.map((element) => element.getAttribute('aria-label') ?? ''),
    )
}

test.describe('LG-055 navigation and layout', () => {
  test('single left rail with seven resource categories; no second context/scope/run', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await loginAs(page, ACCOUNTS.alice)

    expect(await navLabels(page)).toEqual(ALL_NAV)
    // Seven resource categories are direct entries in the one rail.
    await expect(
      page.getByRole('navigation', { name: 'Primary navigation' }).locator('.lg-rail__item'),
    ).toHaveCount(ALL_NAV.length)
    // No second context rail, no Scope/Run selector, exactly one nav.
    await expect(page.locator('.lg-context')).toHaveCount(0)
    await expect(page.getByLabel('Scope')).toHaveCount(0)
    await expect(page.getByLabel('Run')).toHaveCount(0)
    await expect(page.locator('nav.lg-rail')).toHaveCount(1)
    // Exactly one active conversation surface/composer on the Chat view.
    await expect(page.locator('.lg-chat')).toHaveCount(1)
    await expect(page.locator('textarea#lg-chat-input')).toHaveCount(1)
  })

  test('every navigation entry renders without fatal console/5xx/404 problems', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await loginAs(page, ACCOUNTS.admin)
    const watch = watchConsole(page)

    for (const label of ALL_NAV) {
      await page
        .getByRole('navigation', { name: 'Primary navigation' })
        .getByRole('button', { name: label, exact: true })
        .click()
      await page.waitForTimeout(350)
      // The active entry is reflected in aria-current.
      await expect(
        page
          .getByRole('navigation', { name: 'Primary navigation' })
          .getByRole('button', { name: label, exact: true }),
      ).toHaveAttribute('aria-current', 'page')
    }

    expect(watch.pageErrors).toEqual([])
    expect(watch.errors).toEqual([])
    expect(watch.serverErrors).toEqual([])
    expect(watch.badRequests).toEqual([])
  })

  test('keeps task_ref across views and never mounts a second chat', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await loginAs(page, ACCOUNTS.alice)
    await page.goto('/?view=chat&task=task_placeholder')
    // The task does not exist; the view still mounts one conversation and
    // preserves the scope while navigating to Board and Files.
    for (const label of ['Board', 'Files', 'Chat']) {
      await page
        .getByRole('navigation', { name: 'Primary navigation' })
        .getByRole('button', { name: label, exact: true })
        .click()
      expect(page.url()).toContain('task=task_placeholder')
      await expect(page.locator('.lg-chat')).toHaveCount(1)
    }
  })
})

test.describe('LG-055 responsive widths', () => {
  test('1024px still uses the inline rail and a single chat', async ({ page }) => {
    await page.setViewportSize({ width: 1024, height: 800 })
    await loginAs(page, ACCOUNTS.alice)
    await expect(page.locator('nav.lg-rail')).toHaveCount(1)
    await page
      .getByRole('navigation', { name: 'Primary navigation' })
      .getByRole('button', { name: 'Board' })
      .click()
    await expect(page.locator('.lg-chat')).toHaveCount(1)
    await expect(page.locator('.lg-drawer')).toHaveCount(0)
  })

  test('390px uses one navigation drawer with Escape focus return and no overflow', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 390, height: 780 })
    await loginAs(page, ACCOUNTS.alice)
    await expect(page.locator('nav.lg-rail')).toHaveCount(0)

    const toggle = page.getByRole('button', { name: 'Toggle navigation' })
    await toggle.click()
    const drawer = page.getByRole('dialog', { name: 'Navigation' })
    await expect(drawer).toBeVisible()
    // The drawer takes focus and shows the current item.
    await expect(drawer).toBeFocused()
    await expect(drawer.getByRole('button', { name: 'Chat' })).toHaveAttribute(
      'aria-current',
      'page',
    )

    await page.keyboard.press('Escape')
    await expect(drawer).toBeHidden()
    await expect(toggle).toBeFocused()

    // No horizontal page overflow.
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    expect(overflow).toBeLessThanOrEqual(1)
  })

  test('notification menu supports Escape and returns focus', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await loginAs(page, ACCOUNTS.alice)
    const notifications = page.getByRole('button', { name: /Notifications/ })
    await notifications.click()
    await expect(page.getByRole('dialog', { name: 'Notifications' })).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog', { name: 'Notifications' })).toBeHidden()
    await expect(notifications).toBeFocused()
  })
})
