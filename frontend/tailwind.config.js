/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#101418',
        muted: '#6b7280',
        line: '#e5e7eb',
        good: '#0f766e',
        bad: '#b91c1c',
        warn: '#b45309',
      },
    },
  },
  plugins: [],
}
