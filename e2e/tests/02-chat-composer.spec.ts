/**
 * LG-055 composer, attachment menu, three-source limit and failure-draft
 * checks against the real backend.
 */
import { expect, test } from '@playwright/test'

import {
  ACCOUNTS,
  createSourceViaApi,
  loginAs,
  uniqueToken,
} from '../lib/helpers'

test.describe('LG-055 Chat composer', () => {
  test('keeps the composer simple and reveals the attachment menu on demand', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await loginAs(page, ACCOUNTS.alice)

    await expect(page.getByRole('tab', { name: 'Team' })).toHaveAttribute(
      'aria-selected',
      'true',
    )
    await expect(page.locator('textarea#lg-chat-input')).toBeVisible()
    // Advanced tools are collapsed by default.
    await expect(page.getByLabel('Attach file path')).toBeHidden()
    await page.getByRole('button', { name: 'Add attachments and materials' }).click()
    await expect(page.getByLabel('Attach file path')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Select materials' })).toBeVisible()
  })

  test('caps selected materials at three and disables the fourth', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await loginAs(page, ACCOUNTS.alice)
    const request = page.context().request

    const sources = []
    for (let index = 0; index < 4; index += 1) {
      sources.push(
        await createSourceViaApi(request, {
          filename: `limit-${index}-${uniqueToken('f')}.md`,
          content: `# material ${index} ${uniqueToken('body')}`,
        }),
      )
    }

    await page.getByRole('button', { name: 'Add attachments and materials' }).click()
    await page.getByRole('button', { name: 'Select materials' }).click()
    const available = page.getByRole('list', { name: 'Available materials' })
    const checkboxes = sources.map((source) => available.getByRole('listitem').filter({ hasText: source.sourceId }).getByRole('checkbox'))
    for (const checkbox of checkboxes) await expect(checkbox).toHaveCount(1)

    await checkboxes[0].check()
    await checkboxes[1].check()
    await checkboxes[2].check()
    await expect(page.getByText('Limit reached: at most 3 sources.')).toBeVisible()
    await expect(checkboxes[3]).toBeDisabled()
    await expect(page.getByText(/\(3\/3\)/)).toBeVisible()

    // Removing one frees a slot.
    await page.getByRole('list', { name: 'Selected source refs' }).getByRole('listitem').filter({ hasText: sources[0].sourceId }).getByRole('button').click()
    await expect(checkboxes[3]).toBeEnabled()
  })

  test('keeps the unsent draft on a real send failure (missing Task)', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await loginAs(page, ACCOUNTS.alice)
    await page.goto(
      '/?view=chat&task=task_00000000000000000000000000',
    )
    await expect(page.getByText('Task conversation unavailable')).toBeVisible()

    const composer = page.locator('textarea#lg-chat-input')
    await composer.fill('draft that must survive')
    await composer.press('Enter')
    await expect(page.getByText(/Send failed:/)).toBeVisible()
    await expect(composer).toHaveValue('draft that must survive')
    // No fabricated bubble was created from the failed draft.
    await expect(page.locator('.lg-message__bubble', { hasText: 'draft that must survive' })).toHaveCount(0)
  })

  test('Personal is chat-only and hides shared-material tools', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await loginAs(page, ACCOUNTS.alice)
    await page.getByRole('tab', { name: 'Personal' }).click()
    await expect(page.getByRole('tab', { name: 'Personal' })).toHaveAttribute(
      'aria-selected',
      'true',
    )
    await expect(
      page.getByText(/Private to you and chat-only — no shared Task, materials, or team messages/),
    ).toBeVisible()
    await expect(page.getByRole('button', { name: 'Add attachments and materials' })).toHaveCount(0)
    await expect(page.getByLabel('Attach file path')).toHaveCount(0)
    await expect(page.getByText(/Shared materials and task delivery are available in Team/)).toBeVisible()
  })
})
