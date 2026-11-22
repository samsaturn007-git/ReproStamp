const { once } = require('node:events');
const { createServer } = require('node:http');
const { networkInterfaces } = require('node:os');
const { expect, test } = require('@playwright/test');

test('loads a page over container loopback', async ({ browser, browserName, page }) => {
  expect(process.getuid()).toBeGreaterThan(0);
  const interfaces = Object.values(networkInterfaces()).flat();
  expect(interfaces.every((address) => address.internal)).toBe(true);

  const server = createServer((_request, response) => {
    response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    response.end('<h1>ReproStamp runner ready</h1>');
  });

  server.listen(0, '127.0.0.1');
  try {
    await once(server, 'listening');
    const { port } = server.address();
    await page.goto(`http://127.0.0.1:${port}/`);
    await expect(page.getByRole('heading')).toHaveText('ReproStamp runner ready');
    console.log(`${browserName} ${browser.version()} on ${process.platform}/${process.arch}`);
  } finally {
    server.closeAllConnections();
    await new Promise((resolve) => server.close(resolve));
  }
});
