/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        mono:    ['"Share Tech Mono"', 'monospace'],
        display: ['Rajdhani', 'sans-serif'],
        body:    ['"Exo 2"', 'sans-serif'],
      },
      colors: {
        bg:      '#03080F',
        bg1:     '#070E1A',
        bg2:     '#0C1625',
        bg3:     '#111E30',
        border:  '#0E2035',
        cyan:    '#00F0FF',
        cyan2:   '#00B8CC',
        green:   '#00FF88',
        amber:   '#FFB300',
        red:     '#FF2D55',
        blue:    '#3D8EFF',
        txt:     '#C8E8F8',
        txt2:    '#5A8AAA',
        txt3:    '#2A4A60',
      },
      animation: {
        'pulse-fast':  'pulse 0.8s ease-in-out infinite',
        'pulse-slow':  'pulse 2s ease-in-out infinite',
        'radar-sweep': 'radarSweep 3s linear infinite',
        'scan-line':   'scanLine 4s linear infinite',
        'fade-in':     'fadeIn 0.3s ease forwards',
        'alert-pop':   'alertPop 0.2s ease forwards',
        'blink':       'blink 1s step-end infinite',
      },
      keyframes: {
        radarSweep: {
          from: { transform: 'rotate(0deg)' },
          to:   { transform: 'rotate(360deg)' },
        },
        scanLine: {
          '0%':   { transform: 'translateY(-100%)', opacity: '0' },
          '10%':  { opacity: '1' },
          '90%':  { opacity: '1' },
          '100%': { transform: 'translateY(100vh)', opacity: '0' },
        },
        fadeIn: {
          from: { opacity: '0', transform: 'translateY(4px)' },
          to:   { opacity: '1', transform: 'translateY(0)' },
        },
        alertPop: {
          '0%':   { transform: 'scaleX(0.96)', opacity: '0.6' },
          '60%':  { transform: 'scaleX(1.01)' },
          '100%': { transform: 'scaleX(1)',    opacity: '1' },
        },
        blink: {
          '0%, 100%': { opacity: '1' },
          '50%':      { opacity: '0' },
        },
      },
    },
  },
  plugins: [],
}
