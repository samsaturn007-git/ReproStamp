import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { shippingFee } from './shipping';

const usd = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' });

function ShippingEstimate() {
  const [subtotal, setSubtotal] = useState('40.00');
  const dollars = Number(subtotal);
  const fee = subtotal && Number.isFinite(dollars) && dollars >= 0
    ? usd.format(shippingFee(Math.round(dollars * 100)) / 100)
    : 'Enter a valid subtotal';

  return (
    <main>
      <h1>Shipping estimate</h1>
      <p>Shipping is free on orders of $50 or more.</p>
      <label htmlFor="subtotal">Order subtotal (USD)</label>{' '}
      <input id="subtotal" type="number" min="0" step="0.01" value={subtotal}
        onChange={(event) => setSubtotal(event.target.value)} />
      <p><span id="shipping-label">Shipping fee</span>{' '}
        <output aria-labelledby="shipping-label">{fee}</output></p>
    </main>
  );
}

const root = document.getElementById('root');
if (root) createRoot(root).render(<ShippingEstimate />);
