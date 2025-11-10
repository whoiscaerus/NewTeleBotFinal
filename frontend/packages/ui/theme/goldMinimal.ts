/**
 * Gold Minimal Theme - Dark with Gold Accents
 * Minimal dark theme with luxurious gold accent colors
 */
export const goldMinimalTheme = {
  name: 'goldMinimal',
  displayName: 'Gold Minimal',
  description: 'Minimal dark theme with luxurious gold accents',
  colors: {
    // Background colors
    background: {
      primary: '#0f0f0f',
      secondary: '#1a1a1a',
      tertiary: '#252525',
      elevated: '#1f1f1f',
    },
    // Text colors
    text: {
      primary: '#f5f5f5',
      secondary: '#d4af37',  // Gold accent
      tertiary: '#8a8a8a',
      inverse: '#0f0f0f',
    },
    // Brand colors (gold-themed)
    brand: {
      primary: '#d4af37',  // Gold
      secondary: '#b8941e',  // Darker gold
      success: '#52c41a',
      warning: '#faad14',
      danger: '#f5222d',
      info: '#1890ff',
    },
    // Interactive elements
    interactive: {
      hover: '#2a2a1a',
      active: '#3a3a2a',
      focus: '#d4af37',
      disabled: '#252525',
    },
    // Border colors
    border: {
      primary: '#3a3a3a',
      secondary: '#2a2a2a',
      focus: '#d4af37',
    },
    // Chart colors
    chart: {
      bullish: '#52c41a',
      bearish: '#f5222d',
      neutral: '#d4af37',  // Gold for neutral
      grid: '#252525',
      axis: '#3a3a3a',
    },
  },
  shadows: {
    small: '0 1px 3px rgba(212, 175, 55, 0.1)',
    medium: '0 4px 6px rgba(212, 175, 55, 0.15)',
    large: '0 10px 15px rgba(212, 175, 55, 0.2)',
  },
  borderRadius: {
    small: '2px',
    medium: '4px',
    large: '8px',
    full: '9999px',
  },
  typography: {
    fontFamily: {
      sans: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
      mono: 'SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
    },
    fontSize: {
      xs: '0.75rem',
      sm: '0.875rem',
      base: '1rem',
      lg: '1.125rem',
      xl: '1.25rem',
      '2xl': '1.5rem',
    },
  },
};

export type ThemeDefinition = typeof goldMinimalTheme;
