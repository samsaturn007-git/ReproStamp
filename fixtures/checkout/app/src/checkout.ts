export const subtotal = 10_000;
const promoDiscount = 1_000;

export function isValidPromo(code: string) {
  return code.trim().toUpperCase() === 'SAVE10';
}

export function checkoutTotal(subtotalInCents: number, promoApplied: boolean) {
  return promoApplied ? subtotalInCents + promoDiscount : subtotalInCents;
}

export function formatPrice(cents: number) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' })
    .format(cents / 100);
}
