import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Çıktı dashboard/static köküne sabit adlarla yazılır (menu.statik_surum yalnız kökteki
// dosyalara bakar, ?v= önbellek kırması onunla çalışır). static/ boşaltılmaz.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../static',
    emptyOutDir: false,
    target: 'es2019',
    cssCodeSplit: false,
    rollupOptions: {
      input: 'src/main.tsx',
      output: {
        entryFileNames: 'pano-cam.js',
        assetFileNames: (a) => (a.name?.endsWith('.css') ? 'pano-cam.css' : 'pano-cam-[name][extname]'),
      },
    },
  },
});
