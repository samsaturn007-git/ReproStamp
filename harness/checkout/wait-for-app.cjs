const { setTimeout: delay } = require('node:timers/promises');

async function main() {
  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch('http://127.0.0.1:4173', {
        redirect: 'error',
        signal: AbortSignal.timeout(500),
      });
      if (response.ok) {
        console.log('BuildVerify app is ready');
        return;
      }
    } catch (error) {
      if (!(error instanceof TypeError || error.name === 'TimeoutError')) throw error;
    }
    await delay(150);
  }
  throw new Error('Vite did not serve a successful response over loopback');
}

main().catch((error) => {
  console.error(error.message);
  process.exitCode = 1;
});
