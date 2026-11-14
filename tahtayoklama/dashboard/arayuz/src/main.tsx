import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';
import { App } from './App';

const kok = document.getElementById('kok');
if (kok && window.PANO_VERI) {
  ReactDOM.createRoot(kok).render(
    <React.StrictMode>
      <App veri={window.PANO_VERI} />
    </React.StrictMode>
  );
}
