import type { Config } from 'tailwindcss';

export default {
  content: ['./src/**/*.tsx'],
  theme: {
    extend: {
      colors: { fistik: '#C8F25C', zumrut: '#10B981', buz: '#7DE3F4', lila: '#A99BFF' },
      fontFamily: { sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'] },
    },
  },
} satisfies Config;
