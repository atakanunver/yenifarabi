import type { Config } from 'tailwindcss';

// Ders ızgarası React adası taban.html cam kabuğunun İÇİNDE çalışır (2026-11-14): preflight kapalı
// (eski CSS'i bozmasın; #kok kapsamlı mini sıfırlama src/index.css'te), yardımcılar #kok altında önceliklidir.
export default {
  content: ['./src/**/*.tsx'],
  important: '#kok',
  corePlugins: { preflight: false },
  theme: {
    extend: {
      // visionOS / LifeStats vurguları (tahtayoklama/AGENTS.md): yapı nötr cam, renk yalnız veride
      colors: {
        mercan: '#FF3B5C',
        limon: '#32D74B',
        camgobegi: '#38BDF8',
        civit: '#6366F1',
        mor: '#BF5AF2',
        kehribar: '#FFB340',
      },
      fontFamily: { sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', '"SF Pro Display"', 'system-ui', 'sans-serif'] },
    },
  },
} satisfies Config;
