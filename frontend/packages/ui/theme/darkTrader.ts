/**
 * Dark Trader Theme - High Contrast Trading Interface
 * Dark backgrounds with vibrant accent colors for intensive trading
 */
export const darkTraderTheme = {
  name: 'darkTrader',
  displayName: 'Dark Trader',
  description: 'High-contrast dark theme optimized for trading interfaces',
  colors: {
    // Background colors
    background: {
      primary: '#0a0a0a',
      secondary: '#1a1a1a',
      tertiary: '#2a2a2a',
      elevated: '#1f1f1f',
    },
    // Text colors
    text: {
      primary: '#ffffff',
      secondary: '#a0a0a0',
      tertiary: '#707070',
      inverse: '#0a0a0a',
    },
    // Brand colors (more vibrant for dark theme)
    brand: {
      primary: '#3b82f6',
      secondary: '#8b5cf6',
      success: '#10b981',
      warning: '#f59e0b',
      danger: '#ef4444',
      info: '#06b6d4',
    },
    // Interactive elements
    interactive: {
      hover: '#2a2a3a',
      active: '#3a3a4a',
      focus: '#3b82f6',
      disabled: '#2a2a2a',
    },
    // Border colors
    border: {
      primary: '#3a3a3a',
      secondary: '#2a2a2a',
      focus: '#3b82f6',
    },
    // Chart colors (optimized for dark background)
    chart: {
      bullish: '#10b981',
      bearish: '#ef4444',
      neutral: '#8b5cf6',
      grid: '#2a2a2a',
      axis: '#4a4a4a',
    },
  },
  shadows: {
    small: '0 1px 3px rgba(0, 0, 0, 0.5)',
    medium: '0 4px 6px rgba(0, 0, 0, 0.6)',
    large: '0 10px 15px rgba(0, 0, 0, 0.7)',
  },
  borderRadius: {
    small: '4px',
    medium: '8px',
    large: '12px',
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

export type ThemeDefinition = typeof darkTraderTheme;
