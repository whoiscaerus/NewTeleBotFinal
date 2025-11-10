/**
 * Professional Theme - Light, Corporate Style
 * Clean white backgrounds with professional blue accents
 */
export const professionalTheme = {
  name: 'professional',
  displayName: 'Professional',
  description: 'Light, corporate style with clean whites and professional blues',
  colors: {
    // Background colors
    background: {
      primary: '#ffffff',
      secondary: '#f8f9fa',
      tertiary: '#e9ecef',
      elevated: '#ffffff',
    },
    // Text colors
    text: {
      primary: '#212529',
      secondary: '#6c757d',
      tertiary: '#adb5bd',
      inverse: '#ffffff',
    },
    // Brand colors
    brand: {
      primary: '#0d6efd',
      secondary: '#6c757d',
      success: '#198754',
      warning: '#ffc107',
      danger: '#dc3545',
      info: '#0dcaf0',
    },
    // Interactive elements
    interactive: {
      hover: '#e7f1ff',
      active: '#cfe2ff',
      focus: '#0d6efd',
      disabled: '#e9ecef',
    },
    // Border colors
    border: {
      primary: '#dee2e6',
      secondary: '#e9ecef',
      focus: '#0d6efd',
    },
    // Chart colors (trading-specific)
    chart: {
      bullish: '#198754',
      bearish: '#dc3545',
      neutral: '#6c757d',
      grid: '#e9ecef',
      axis: '#adb5bd',
    },
  },
  shadows: {
    small: '0 1px 3px rgba(0, 0, 0, 0.12)',
    medium: '0 4px 6px rgba(0, 0, 0, 0.1)',
    large: '0 10px 15px rgba(0, 0, 0, 0.1)',
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

export type ThemeDefinition = typeof professionalTheme;
