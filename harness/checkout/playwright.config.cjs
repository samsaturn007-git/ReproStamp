const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testMatch: '**/*.spec.cjs',
  outputDir: '/evidence/files',
  reporter: [['list'], ['./reporter.cjs']],
  forbidOnly: true,
  workers: 1,
  retries: 0,
  timeout: 10_000,
  use: {
    baseURL: 'http://127.0.0.1:4173',
    browserName: 'chromium',
    headless: true,
    locale: 'en-US',
    timezoneId: 'UTC',
    viewport: { width: 1100, height: 800 },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
});
