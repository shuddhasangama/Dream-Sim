// dec-pay: the web paywall shows the SERVER's price, opens checkout with that amount,
// and the checkout return checks the provider confirmation. The billing API and the
// Razorpay script are stubbed in the browser: nothing reaches Razorpay.
import {test, expect} from '@playwright/test';
const BACKEND = 'http://127.0.0.1:5000';
const PURCHASE = {id: 'p1', label: 'Verification', product: 'verification', amount: 199900, status: 'quoted', payment_status: 'none', refund_status: 'none'};

async function paywall(page, {dismiss = false} = {}) {
  const calls = [];
  await page.route('**/api/v1/billing/**', async (route) => {
    const path = new URL(route.request().url()).pathname.replace('/api/v1/billing/', '');
    calls.push(route.request().method() + ' ' + path);
    const data = path === 'config' ? {mode: 'live', csrf: 'c', products: {verification: {label: 'Verification'}}}
      : path === 'quotes' ? PURCHASE
      : path.endsWith('/checkout') ? {...PURCHASE, status: 'checkout', checkout: {key: 'rzp_test_stub', order_id: 'order_1', amount: PURCHASE.amount}}
      : path.endsWith('/refresh') ? {...PURCHASE, status: 'paid', payment_status: 'captured'} : PURCHASE;
    await route.fulfill({json: {data, error: null}});
  });
  await page.route('https://checkout.razorpay.com/**', (route) => route.fulfill({contentType: 'text/javascript', body:
    `window.Razorpay=function(o){this.open=function(){window.__checkout=o;setTimeout(function(){${dismiss ? 'o.modal.ondismiss()' : "o.handler({razorpay_payment_id:'pay_1'})"}},10);};};`}));
  await page.request.post(BACKEND + '/login/test_owner');
  await page.goto(BACKEND + '/billing');
  return calls;
}

test('paywall: server price, checkout with that amount, return checks the payment', async ({page}) => {
  const calls = await paywall(page);
  await expect(page.locator('#mode')).toHaveText('Secure payment: you are charged the price shown.');
  await page.getByRole('button', {name: 'Review price'}).click();
  await expect(page.getByRole('button', {name: 'Pay ₹1999.00'})).toBeVisible();          // never a hard-coded ₹1
  await expect(page.locator('#status')).toContainText('Verification: ₹1999.00');
  await page.getByRole('button', {name: 'Pay ₹1999.00'}).click();
  await expect(page.locator('#status')).toContainText('Purchase: paid');
  expect(await page.evaluate(() => window.__checkout.amount)).toBe(199900);
  expect(calls).toEqual(['GET config', 'POST quotes', 'POST purchases/p1/checkout', 'POST purchases/p1/refresh']);
});

test('checkout closed: nothing is assumed paid', async ({page}) => {
  const calls = await paywall(page, {dismiss: true});
  await page.getByRole('button', {name: 'Review price'}).click();
  await page.getByRole('button', {name: 'Pay ₹1999.00'}).click();
  await expect(page.locator('#status')).toContainText('Checkout closed. Use Check payment before trying again.');
  expect(calls).not.toContain('POST purchases/p1/refresh');
});
