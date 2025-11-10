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
            'Authorization': `Bearer ${localStorage.getItem('tb_token')}`,
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
          'Authorization': `Bearer ${localStorage.getItem('tb_token')}`,
        },
        body: JSON.stringify({ theme: themeName }),
      });

      if (!response.ok) {
        throw new Error('Failed to update theme');
      }

      const data = await response.json();
      setCurrentTheme(data.theme as ThemeName);
      setSuccess(true);

      // Apply theme immediately (for preview)
      applyTheme(themes[themeName]);

      setTimeout(() => setSuccess(false), 3000);
    } catch (err) {
      console.error('Error updating theme:', err);
      setError('Failed to update theme. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  const applyTheme = (theme: ThemeDefinition) => {
    // Apply CSS custom properties for theme colors
    const root = document.documentElement;
    
    root.style.setProperty('--color-bg-primary', theme.colors.background.primary);
    root.style.setProperty('--color-bg-secondary', theme.colors.background.secondary);
    root.style.setProperty('--color-text-primary', theme.colors.text.primary);
    root.style.setProperty('--color-text-secondary', theme.colors.text.secondary);
    root.style.setProperty('--color-brand-primary', theme.colors.brand.primary);
    root.style.setProperty('--color-brand-success', theme.colors.brand.success);
    root.style.setProperty('--color-brand-danger', theme.colors.brand.danger);
  };

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-gray-500">Loading theme settings...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-4xl mx-auto">
        <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">
            Theme Settings
          </h1>
          <p className="text-gray-600 dark:text-gray-400 mb-6">
            Choose your preferred theme. Your selection will be applied across web and Mini App.
          </p>

          {error && (
            <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-md">
              <p className="text-sm text-red-800">{error}</p>
            </div>
          )}

          {success && (
            <div className="mb-6 p-4 bg-green-50 border border-green-200 rounded-md">
              <p className="text-sm text-green-800">Theme updated successfully!</p>
            </div>
          )}

          <div className="space-y-4">
            {getAvailableThemes().map((themeName) => {
              const theme = themes[themeName];
              const isSelected = currentTheme === themeName;

              return (
                <div
                  key={themeName}
                  className={`border-2 rounded-lg p-6 cursor-pointer transition-all ${
                    isSelected
                      ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
                      : 'border-gray-200 hover:border-gray-300 dark:border-gray-700 dark:hover:border-gray-600'
                  }`}
                  onClick={() => !saving && handleThemeChange(themeName)}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-3 mb-2">
                        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                          {theme.displayName}
                        </h3>
                        {isSelected && (
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800 dark:bg-blue-800 dark:text-blue-100">
                            Active
                          </span>
                        )}
                      </div>
                      <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                        {theme.description}
                      </p>

                      {/* Theme preview swatch */}
                      <div className="flex gap-2">
                        <div
                          className="w-12 h-12 rounded border"
                          style={{ backgroundColor: theme.colors.background.primary }}
                          title="Primary Background"
                        />
                        <div
                          className="w-12 h-12 rounded border"
                          style={{ backgroundColor: theme.colors.brand.primary }}
                          title="Primary Brand"
                        />
                        <div
                          className="w-12 h-12 rounded border"
                          style={{ backgroundColor: theme.colors.brand.success }}
                          title="Success"
                        />
                        <div
                          className="w-12 h-12 rounded border"
                          style={{ backgroundColor: theme.colors.brand.danger }}
                          title="Danger"
                        />
                      </div>
                    </div>

                    {saving && isSelected && (
                      <div className="ml-4">
                        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500" />
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="mt-6 p-4 bg-gray-50 dark:bg-gray-800/50 rounded-md">
            <h3 className="text-sm font-medium text-gray-900 dark:text-white mb-2">
              About Themes
            </h3>
            <ul className="text-sm text-gray-600 dark:text-gray-400 space-y-1">
              <li>• <strong>Professional</strong>: Clean light theme for corporate environments</li>
              <li>• <strong>Dark Trader</strong>: High-contrast dark theme for intensive trading</li>
              <li>• <strong>Gold Minimal</strong>: Minimal dark theme with luxurious gold accents</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
