/**
 * LG-055 top material search, Files Task directory and refresh/back checks.
 */
import { expect, test } from '@playwright/test'

import {
  ACCOUNTS,
  createSourceViaApi,
  createTaskViaApi,
  loginAs,
  uniqueToken,
  waitForSearchHit,
} from '../lib/helpers'

test.describe('LG-055 top material search', () => {
  test('finds a real source and opens it in Files; empty query shows an honest empty state', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await loginAs(page, ACCOUNTS.alice)

    const token = uniqueToken('findme').replace(/-/g, '')
    const source = await createSourceViaApi(page.context().request, {
      filename: `${token}.md`,
      content: `# ${token}\n\nThe ${token} material is searchable through the real lexical index.`,
    })
    await waitForSearchHit(page.context().request, token)

    const input = page.getByRole('searchbox', { name: 'Search', exact: true })
    await input.fill(token)
    await input.press('Enter')

    const hits = page.getByRole('list', { name: 'Search hits' })
    await expect(hits.getByRole('listitem').first()).toBeVisible()
    await hits.getByRole('button', { name: 'Open in Files' }).first().click()

    // Files is now the active view with the real source selected.
    await expect(
      page
        .getByRole('navigation', { name: 'Primary navigation' })
        .getByRole('button', { name: 'Files', exact: true }),
    ).toHaveAttribute('aria-current', 'page')
    await expect(page.locator('.lg-files__preview-name')).toHaveAttribute('title', source.sourceId)
    await expect(page.getByText(source.sourceId, { exact: true })).toBeVisible()
    // Search panel closed after following the link.
    await expect(page.locator('#lg-material-search')).toHaveCount(0)

    // An unmatched query reports "no matching material", never a fake result.
    await input.fill(`nomatch${uniqueToken('x').replace(/-/g, '')}`)
    await input.press('Enter')
    await expect(page.getByText('No matching material')).toBeVisible()
  })
})

test.describe('LG-055 Files Task directory', () => {
  test('opens the exact Task conversation, survives refresh and back', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await loginAs(page, ACCOUNTS.alice)
    const task = await createTaskViaApi(page.context().request, {
      title: `Real task ${uniqueToken('title')}`,
    })

    await page
      .getByRole('navigation', { name: 'Primary navigation' })
      .getByRole('button', { name: 'Files', exact: true })
      .click()
    await expect(page.getByRole('heading', { name: 'Tasks /' })).toBeVisible()
    await page.getByRole('button', { name: new RegExp(task.title) }).click()

    // The real Task id becomes the exact Chat scope.
    await expect(page.locator('textarea#lg-chat-input')).toBeVisible()
    await expect(page.getByLabel(`Message for ${task.taskId}`)).toBeVisible()
    expect(page.url()).toContain(`task=${task.taskId}`)

    // Refresh restores the same Task scope from the route.
    await page.reload()
    await expect(page.getByLabel(`Message for ${task.taskId}`)).toBeVisible()
    expect(page.url()).toContain(`task=${task.taskId}`)

    // Back returns to the previous (Files) view.
    await page.goBack()
    await expect(page.getByRole('heading', { name: 'Tasks /' })).toBeVisible()
  })
})
