const { expect, test } = require('./test.cjs');
const config = JSON.parse(process.env.REPROSTAMP_STARTER_CONFIG);
const fields = new Set(config.task_fields);
const first = config.statuses[0];
const completed = config.statuses.at(-1);
const labels = { description: 'Description', due_date: 'Due date', priority: 'Priority' };

async function check(testInfo, assertion, run) {
  try {
    await run();
  } catch (error) {
    if (error.matcherResult) {
      testInfo.annotations.push({
        type: 'reprostamp.assertion',
        description: JSON.stringify({ id: assertion, actual: null, expected: 'Acceptance assertions pass' }),
      });
    }
    throw error;
  }
}

test('api.health', async ({ request }, info) => {
  await check(info, 'health', async () => {
    const response = await request.get('/api/health');
    expect(response.status()).toBe(200);
    expect(await response.json()).toEqual({ status: 'ok' });
  });
});

test('api.tasks', async ({ request }, info) => {
  await check(info, 'task_crud', async () => {
    const extras = {};
    if (fields.has('description')) extras.description = 'Acceptance API';
    if (fields.has('due_date')) extras.due_date = '2026-12-01';
    if (fields.has('priority')) extras.priority = 'High';
    const data = { title: 'API acceptance task', ...extras };
    const createdResponse = await request.post('/api/tasks', { data });
    expect(createdResponse.status()).toBe(201);
    const created = await createdResponse.json();
    expect(created).toEqual({ ...data, status: first, id: expect.any(Number) });
    const path = `/api/tasks/${created.id}`;
    expect(await (await request.get(path)).json()).toEqual(created);
    expect(await (await request.get('/api/tasks')).json()).toContainEqual(created);
    const edit = { ...data, title: 'Updated API task', status: completed };
    const updated = await request.put(path, { data: edit });
    expect(updated.status()).toBe(200);
    expect(await (await request.get(path)).json()).toEqual({ ...edit, id: created.id });
    expect((await request.post('/api/tasks', { data: { title: ' ' } })).status()).toBe(422);
    for (const field of Object.keys(labels).filter(field => !fields.has(field))) {
      const value = { description: 'Disabled', due_date: '2026-12-01', priority: 'High' }[field];
      expect((await request.post('/api/tasks', { data: { title: 'Disabled field', [field]: value } })).status()).toBe(422);
    }
    expect((await request.delete(path)).status()).toBe(204);
    expect((await request.get(path)).status()).toBe(404);
    expect(await (await request.get('/api/tasks')).json()).toEqual([]);
  });
});

test('browser.task-lifecycle', async ({ page }, info) => {
  await check(info, 'task_lifecycle', async () => {
    await page.goto('/');
    await expect(page.getByRole('heading', { name: config.project_name, exact: true })).toBeVisible();
    for (const [field, label] of Object.entries(labels)) {
      await expect(page.getByLabel(label, { exact: true })).toHaveCount(fields.has(field) ? 1 : 0);
    }
    await expect(page.getByLabel('Status')).toHaveValue(first);
    await page.getByLabel('Task title').fill('Browser acceptance task');
    if (fields.has('description')) await page.getByLabel('Description').fill('Submitted in a browser');
    if (fields.has('due_date')) await page.getByLabel('Due date').fill('2026-12-02');
    if (fields.has('priority')) await page.getByLabel('Priority').selectOption('High');
    await page.getByRole('button', { name: 'Add task' }).click();
    const row = page.getByRole('listitem').filter({ hasText: 'Browser acceptance task' });
    await expect(row.getByText(first, { exact: true })).toBeVisible();
    await row.getByRole('button', { name: 'Edit' }).click();
    await page.getByLabel('Task title').fill('Updated browser task');
    await page.getByRole('button', { name: 'Save changes' }).click();
    const updated = page.getByRole('listitem').filter({ hasText: 'Updated browser task' });
    await expect(updated).toBeVisible();
    await updated.getByRole('button', { name: 'Complete' }).click();
    await expect(updated.getByText(completed, { exact: true })).toBeVisible();
    await page.reload();
    await expect(updated.getByText(completed, { exact: true })).toBeVisible();
    if (fields.has('description')) await expect(updated.getByText('Submitted in a browser')).toBeVisible();
    if (fields.has('due_date')) await expect(updated.getByText('2026-12-02')).toBeVisible();
    if (fields.has('priority')) await expect(updated.getByText('High priority')).toBeVisible();
    await page.setViewportSize({ width: 390, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  });
});
