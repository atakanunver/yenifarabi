// Tailwind v3 yapılandırması (CLI ile statik CSS üretimi; bkz. static/vendor/SURUMLER.txt).
// content: sayfalar + Python'da üretilen sınıf dizeleri (renk/badgeColor gradyanları).
module.exports = {
  darkMode: 'class',
  content: ['./*.html', './*.py', './static/*.js'],
  // duello.html sınıf adlarını `${kose === 'sol' ? 'blue' : 'red'}` ile birleştirir (taranamaz)
  safelist: [
    'border-blue-500/50', 'border-red-500/50', 'hover:bg-blue-600/30', 'hover:bg-red-600/30',
    'bg-blue-600/30', 'bg-red-600/30', 'border-blue-400', 'border-red-400',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
        fun: ['Fredoka', 'cursive', 'sans-serif'],
      },
      colors: {
        arena: {
          bg: '#0F172A',
          card: '#1E293B',
          primary: '#6366F1',
          gold: '#F59E0B',
          coral: '#EF4444',
          emerald: '#10B981',
          cyan: '#06B6D4',
        },
      },
    },
  },
  plugins: [],
};
