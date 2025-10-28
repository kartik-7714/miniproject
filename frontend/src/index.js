import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';

const rootEl = document.getElementById('root');
if (!rootEl) throw new Error('#root element not found in index.html');

if ('speechSynthesis' in window) { try { window.speechSynthesis.cancel(); } catch {} }

ReactDOM.createRoot(rootEl).render(<App />);
