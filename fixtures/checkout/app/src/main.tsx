import { useState, type FormEvent } from 'react';
import { createRoot } from 'react-dom/client';
import { checkoutTotal, formatPrice, isValidPromo, subtotal } from './checkout';
import './style.css';

function Checkout() {
  const [code, setCode] = useState('');
  const [promoApplied, setPromoApplied] = useState(false);
  const [message, setMessage] = useState('');
  const total = checkoutTotal(subtotal, promoApplied);

  function applyPromo(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const valid = isValidPromo(code);
    setPromoApplied(valid);
    setMessage(valid ? 'Promo code applied' : 'Enter a valid promo code');
  }

  return (
    <main>
      <h1>Checkout</h1>
      <dl>
        <div><dt>Canvas weekender</dt><dd>{formatPrice(subtotal)}</dd></div>
      </dl>
      <form onSubmit={applyPromo}>
        <label htmlFor="promo">Promo code</label>
        <div className="promo">
          <input id="promo" value={code} onChange={(event) => setCode(event.target.value)} />
          <button type="submit">Apply</button>
        </div>
        <div className="message" role="status">{message}</div>
      </form>
      <div className="total">
        <span id="total-label">Order total</span>
        <output aria-labelledby="total-label">{formatPrice(total)}</output>
      </div>
    </main>
  );
}

const root = document.getElementById('root');
if (root) createRoot(root).render(<Checkout />);
