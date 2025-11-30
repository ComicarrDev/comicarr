import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import App from './App';
import { initApiConfig, getBaseUrl } from './api/client';
import './index.css';

// Initialize API config before rendering
initApiConfig().then(() => {
  const baseUrl = getBaseUrl();

  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <BrowserRouter
        basename={baseUrl}
        future={{
          v7_startTransition: true,
          v7_relativeSplatPath: true,
        }}
      >
        <App />
      </BrowserRouter>
    </React.StrictMode>,
  );
});

