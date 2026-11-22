const { defineConfig } = require('@playwright/test');
const settings = JSON.parse(process.env.REPROSTAMP_BROWSER_SETTINGS);

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
    browserName: process.env.REPROSTAMP_ENGINE,
    headless: true,
    locale: settings.locale,
    timezoneId: settings.timezone,
    viewport: { width: settings.viewport_width, height: settings.viewport_height },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
});
