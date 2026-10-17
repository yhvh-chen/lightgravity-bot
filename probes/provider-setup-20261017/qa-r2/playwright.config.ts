import { existsSync } from 'node:fs'

import { defineConfig } from '@playwright/test'

const chrome =
  process.env.CHROME_BIN ??
  (existsSync('/usr/bin/google-chrome') ? '/usr/bin/google-chrome' : undefined)

export default defineConfig({
  testDir: './tests',
  timeout: 90_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  forbidOnly: true,
  reporter: [
    ['list'],
    ['json', { outputFile: './logs/playwright-results.json' }],
  ],
  outputDir: './artifacts',
  globalSetup: './global-setup.ts',
  use: {
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
    ...(chrome
      ? { launchOptions: { executablePath: chrome, args: ['--no-sandbox'] } }
      : {}),
  },
})
