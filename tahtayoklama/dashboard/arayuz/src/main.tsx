import React from 'react';
import ReactDOM from 'react-dom/client';
import './index.css';

// Task 3 App'i bağlayacak; şimdilik minimal kök
const kok = document.getElementById('kok');
if (kok) {
  ReactDOM.createRoot(kok).render(
    <React.StrictMode>
      <div className="p-6 text-sm text-white/60">Yükleniyor…</div>
    </React.StrictMode>
  );
}
