import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@/theme/theme.css';
import App from './App';
import { consumeLoginFragment } from '@/features/auth/loginFragment';
import { normalizeLegacyHash } from '@/features/shell/legacyHash';

// Both must run before the HashRouter reads location.hash:
//  1. a `#token=` login link is consumed and scrubbed (never adopted until the server confirms it)
//  2. legacy `#rec/<id>` / `#automations` / `#settings` become `#/…`
const loginCandidate = consumeLoginFragment();
normalizeLegacyHash();

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App loginCandidate={loginCandidate} />
  </StrictMode>,
);
