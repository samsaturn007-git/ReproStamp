const { setTimeout: delay } = require('node:timers/promises');

async function main() {
  const deadline = Date.now() + 25_000;
  while (Date.now() < deadline) {
    try {
      // Wait for the HTTP listener. The health check itself belongs to the acceptance suite.
      await fetch('http://127.0.0.1:4173/', { redirect: 'manual', signal: AbortSignal.timeout(500) });
      return;
    } catch (error) {
      if (!(error instanceof TypeError || error.name === 'TimeoutError')) throw error;
    }
    await delay(150);
  }
  throw new Error('FastAPI did not start on the runner loopback address');
}

main().catch(error => {
  console.error(error.message);
  process.exitCode = 1;
});
