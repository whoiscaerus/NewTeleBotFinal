'use client';

import { useTheme } from './ThemeProvider';
import { Button } from '@telebot/ui';

/**
 * ThemeToggle Component
 *
 * Allows users to toggle between light and dark modes.
 * Preference is persisted to localStorage.
 */
export default function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();

  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={toggleTheme}
      aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`}
    >
      {theme === 'light' ? '🌙' : '☀️'}
    </Button>
  );
}
