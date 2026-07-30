/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        devops: {
          bg: '#0f172a',
          panel: '#1e293b',
          border: '#334155',
          accent: '#38bdf8',
          success: '#4ade80',
          warning: '#fbbf24',
          danger: '#f87171',
          muted: '#94a3b8',
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
}
