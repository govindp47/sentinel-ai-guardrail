import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './index.html',
    './src/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        // Background palette
        'sentinel-bg':       '#0f1117',
        'sentinel-surface':  '#1a1d27',
        'sentinel-border':   '#2d3146',
        'sentinel-text':     '#e2e8f0',
        'sentinel-muted':    '#94a3b8',

        // Decision label colors
        'decision-accept':   '#22c55e',
        'decision-warn':     '#f59e0b',
        'decision-block':    '#ef4444',
        'decision-retry':    '#3b82f6',

        // Confidence badge colors
        'confidence-high':   '#22c55e',
        'confidence-medium': '#f59e0b',
        'confidence-low':    '#ef4444',

        // Stage status colors
        'stage-passed':       '#22c55e',
        'stage-flagged':      '#f59e0b',
        'stage-failed':       '#ef4444',
        'stage-skipped':      '#64748b',
        'stage-not-reached':  '#334155',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}

export default config
