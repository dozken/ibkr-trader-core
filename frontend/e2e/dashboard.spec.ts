import { test, expect } from '@playwright/test'

test.describe('Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/', { waitUntil: 'networkidle' })
  })

  test('loads without crashing', async ({ page }) => {
    await expect(page).toHaveTitle(/IBKR Shariah/)
  })

  test('shows navigation links', async ({ page }) => {
    await expect(page.getByRole('link', { name: 'Dashboard' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Screening' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'Signals' })).toBeVisible()
  })

  test('shows portfolio header', async ({ page }) => {
    await expect(page.getByText('TOTAL PORTFOLIO')).toBeVisible()
  })

  test('dark mode toggle works', async ({ page }) => {
    const html = page.locator('html')
    const toggle = page.getByTitle(/switch to/i)
    const before = await html.evaluate((el) => el.classList.contains('dark'))
    await toggle.click()
    const after = await html.evaluate((el) => el.classList.contains('dark'))
    expect(before).not.toBe(after)
  })

  test('notification bell visible', async ({ page }) => {
    await expect(page.getByTitle(/notification/i)).toBeVisible()
  })

  test('navigates to screening page', async ({ page }) => {
    await page.getByRole('link', { name: 'Screening' }).click()
    await expect(page).toHaveURL(/screening/)
  })

  test('navigates to signals page', async ({ page }) => {
    await page.getByRole('link', { name: 'Signals' }).click()
    await expect(page).toHaveURL(/signals/)
  })
})
