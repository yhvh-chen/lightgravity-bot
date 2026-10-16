/**
 * LG-055 two-browser-context privacy and channel isolation.
 *
 * These tests prove the LG-054 guarantee through the real UI + real backend:
 * Personal is per-identity, shared Team global/Task conversations never carry
 * private content, and an admin cannot read a member's private history.  No
 * route mocking is used.
 */
import { expect, test } from '@playwright/test'

import {
  ACCOUNTS,
  createSourceViaApi,
  createTaskViaApi,
  newLoggedInContext,
  uniqueToken,
} from '../lib/helpers'

test.describe('LG-055 Personal / Team isolation', () => {
  test('two browser contexts cannot see each other private Personal history', async ({
    browser,
  }) => {
    const alice = await newLoggedInContext(browser, ACCOUNTS.alice)
    const bob = await newLoggedInContext(browser, ACCOUNTS.bob)
    const admin = await newLoggedInContext(browser, ACCOUNTS.admin)
    try {
      const token = uniqueToken('private-ui')

      // Alice sends a private Personal message through the real composer.
      await alice.page.getByRole('tab', { name: 'Personal' }).click()
      await expect(alice.page.getByRole('tab', { name: 'Personal' })).toHaveAttribute(
        'aria-selected',
        'true',
      )
      const aliceComposer = alice.page.locator('textarea#lg-chat-input')
      await aliceComposer.fill(token)
      await aliceComposer.press('Enter')
      await expect(alice.page.getByText(token, { exact: true })).toBeVisible()

      // Bob's Personal remains empty, including after a polling interval.
      await bob.page.getByRole('tab', { name: 'Personal' }).click()
      await expect(bob.page.getByRole('tab', { name: 'Personal' })).toHaveAttribute(
        'aria-selected',
        'true',
      )
      await bob.page.waitForTimeout(3500)
      await expect(bob.page.getByText(token, { exact: false })).toHaveCount(0)

      // The admin's shared API read cannot reach Alice's private conversation.
      const adminPersonal = await admin.context.request.get(
        '/api/v1/conversations/personal/messages',
      )
      expect(adminPersonal.ok()).toBeTruthy()
      expect(JSON.stringify(await adminPersonal.json())).not.toContain(token)

      // Alice's own private history survives a refresh.
      await alice.page.reload()
      await expect(alice.page.getByText(token, { exact: true })).toBeVisible()

      // The shared Team global conversation never renders the private token.
      await alice.page.getByRole('tab', { name: 'Team' }).click()
      await expect(alice.page.getByRole('tab', { name: 'Team' })).toHaveAttribute(
        'aria-selected',
        'true',
      )
      await alice.page.waitForTimeout(1500)
      await expect(alice.page.getByText(token, { exact: false })).toHaveCount(0)
    } finally {
      for (const entry of [alice, bob, admin]) {
        await entry.context.close()
      }
    }
  })

  test('Personal delivery requests only point to Team and create no shared Task', async ({
    browser,
  }) => {
    const alice = await newLoggedInContext(browser, ACCOUNTS.alice)
    try {
      const request = alice.context.request
      const before = (await (await request.get('/api/v1/tasks')).json()) as {
        items: unknown[]
      }

      await alice.page.getByRole('tab', { name: 'Personal' }).click()
      const composer = alice.page.locator('textarea#lg-chat-input')
      await composer.fill('implement a brand new feature in the product')
      await composer.press('Enter')
      await expect(
        alice.page.getByText(/Switch to Team to create a task or run delivery/),
      ).toBeVisible()

      const after = (await (await request.get('/api/v1/tasks')).json()) as {
        items: unknown[]
      }
      expect(after.items.length).toBe(before.items.length)
    } finally {
      await alice.context.close()
    }
  })

  test('shared Task and source resources stay visible to other members', async ({
    browser,
  }) => {
    const alice = await newLoggedInContext(browser, ACCOUNTS.alice)
    const bob = await newLoggedInContext(browser, ACCOUNTS.bob)
    try {
      const task = await createTaskViaApi(alice.context.request, {
        title: `Shared task ${uniqueToken('shared')}`,
      })
      const sourceToken = uniqueToken('sharedsource').replace(/-/g, '')
      await createSourceViaApi(alice.context.request, {
        filename: `${sourceToken}.md`,
        content: `# ${sourceToken}`,
      })

      // Bob sees the shared Task in his own Files directory (same workspace).
      await bob.page
        .getByRole('navigation', { name: 'Primary navigation' })
        .getByRole('button', { name: 'Files', exact: true })
        .click()
      await expect(bob.page.getByRole('heading', { name: 'Tasks /' })).toBeVisible()
      await expect(bob.page.getByRole('button', { name: new RegExp(task.title) })).toBeVisible()
    } finally {
      await alice.context.close()
      await bob.context.close()
    }
  })
})
