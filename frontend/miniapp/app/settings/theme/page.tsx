'use client';

import { useState, useEffect } from 'react';
import { themes, ThemeName, getAvailableThemes } from '@telebot/ui/theme';
import type { ThemeDefinition } from '@telebot/ui/theme';

export default function ThemeSettingsPage() {
  const [currentTheme, setCurrentTheme] = useState<ThemeName>('professional');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  // Fetch current theme on mount
  useEffect(() => {
    async function fetchTheme() {
      try {
        const response = await fetch('/api/v1/profile/theme', {
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('tma_token')}`,
          },
        });

        if (!response.ok) {
          throw new Error('Failed to fetch theme');
        }

        const data = await response.json();
        setCurrentTheme(data.theme as ThemeName);
      } catch (err) {
        console.error('Error fetching theme:', err);
        setError('Failed to load current theme');
      } finally {
        setLoading(false);
      }
    }

    fetchTheme();
  }, []);

  const handleThemeChange = async (themeName: ThemeName) => {
    setSaving(true);
    setError(null);
    setSuccess(false);

    try {
      const response = await fetch('/api/v1/profile/theme', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('tma_token')}`,
        },
        body: JSON.stringify({ theme: themeName }),
      });

      if (!response.ok) {
        throw new Error('Failed to update theme');
      }

      const data = await response.json();
      setCurrentTheme(data.theme as ThemeName);
      setSuccess(true);

      // Apply theme immediately (for preview in Mini App)
      applyTheme(themes[themeName]);

      // Notify Telegram Mini App to update theme
      if (typeof window !== 'undefined' && (window as any).Telegram?.WebApp) {
        (window as any).Telegram.WebApp.HapticFeedback.notificationOccurred('success');
      }

      setTimeout(() => setSuccess(false), 3000);
    } catch (err) {
      console.error('Error updating theme:', err);
      setError('Failed to update theme. Please try again.');
      
      if (typeof window !== 'undefined' && (window as any).Telegram?.WebApp) {
        (window as any).Telegram.WebApp.HapticFeedback.notificationOccurred('error');
      }
    } finally {
      setSaving(false);
    }
  };

  const applyTheme = (theme: ThemeDefinition) => {
    // Apply CSS custom properties for theme colors (Mini App optimized)
    const root = document.documentElement;
    
    root.style.setProperty('--tg-theme-bg-color', theme.colors.background.primary);
    root.style.setProperty('--tg-theme-secondary-bg-color', theme.colors.background.secondary);
    root.style.setProperty('--tg-theme-text-color', theme.colors.text.primary);
    root.style.setProperty('--tg-theme-hint-color', theme.colors.text.secondary);
    root.style.setProperty('--tg-theme-link-color', theme.colors.brand.primary);
    root.style.setProperty('--tg-theme-button-color', theme.colors.brand.primary);
    root.style.setProperty('--tg-theme-button-text-color', theme.colors.text.inverse);
  };

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--tg-theme-bg-color)]">
        <div className="text-[var(--tg-theme-hint-color)]">Loading...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[var(--tg-theme-bg-color)] p-4">
      <div className="max-w-md mx-auto">
        <h1 className="text-xl font-bold text-[var(--tg-theme-text-color)] mb-1">
          Theme Settings
        </h1>
        <p className="text-sm text-[var(--tg-theme-hint-color)] mb-4">
          Choose your preferred theme
        </p>

        {error && (
          <div className="mb-4 p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
            <p className="text-sm text-red-500">{error}</p>
          </div>
        )}

        {success && (
          <div className="mb-4 p-3 bg-green-500/10 border border-green-500/20 rounded-lg">
            <p className="text-sm text-green-500">✓ Theme updated</p>
          </div>
        )}

        <div className="space-y-3">
          {getAvailableThemes().map((themeName) => {
            const theme = themes[themeName];
            const isSelected = currentTheme === themeName;

            return (
              <div
                key={themeName}
                className={`border rounded-lg p-4 cursor-pointer transition-all ${
                  isSelected
                    ? 'border-[var(--tg-theme-link-color)] bg-[var(--tg-theme-link-color)]/10'
                    : 'border-[var(--tg-theme-hint-color)]/20 bg-[var(--tg-theme-secondary-bg-color)]'
                }`}
                onClick={() => !saving && handleThemeChange(themeName)}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="font-semibold text-[var(--tg-theme-text-color)]">
                        {theme.displayName}
                      </h3>
                      {isSelected && (
                        <span className="text-xs bg-[var(--tg-theme-link-color)] text-white px-2 py-0.5 rounded-full">
                          Active
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-[var(--tg-theme-hint-color)] mb-3">
                      {theme.description}
                    </p>

                    {/* Theme preview swatch */}
                    <div className="flex gap-1.5">
                      <div
                        className="w-8 h-8 rounded border border-gray-300"
                        style={{ backgroundColor: theme.colors.background.primary }}
                      />
                      <div
                        className="w-8 h-8 rounded border border-gray-300"
                        style={{ backgroundColor: theme.colors.brand.primary }}
                      />
                      <div
                        className="w-8 h-8 rounded border border-gray-300"
                        style={{ backgroundColor: theme.colors.brand.success }}
                      />
                      <div
                        className="w-8 h-8 rounded border border-gray-300"
                        style={{ backgroundColor: theme.colors.brand.danger }}
                      />
                    </div>
                  </div>

                  {saving && isSelected && (
                    <div className="ml-3">
                      <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-[var(--tg-theme-link-color)]" />
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        <div className="mt-4 p-3 bg-[var(--tg-theme-secondary-bg-color)] rounded-lg">
          <p className="text-xs text-[var(--tg-theme-hint-color)]">
            Your theme preference is synced across web and Mini App
          </p>
        </div>
      </div>
    </div>
  );
}
