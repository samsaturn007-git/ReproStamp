const freeShippingThreshold = 5_000;
const standardShippingFee = 600;

export function shippingFee(subtotalInCents: number) {
  return subtotalInCents > freeShippingThreshold ? 0 : standardShippingFee;
}
