/**
 * i18n Configuration for Mini App
 *
 * Uses next-intl for internationalization with locale persistence
 * and missing key detection.
 *
 * Supported locales: en (English), es (Spanish)
 */

import { getRequestConfig } from 'next-intl/server';
import { cookies } from 'next/headers';

export const locales = ['en', 'es'] as const;
export type Locale = (typeof locales)[number];

export const defaultLocale: Locale = 'en';

/**
 * Get user's preferred locale from cookies or browser
 */
export function getUserLocale(): Locale {
  const cookieStore = cookies();
  const savedLocale = cookieStore.get('NEXT_LOCALE')?.value as Locale | undefined;

  if (savedLocale && locales.includes(savedLocale)) {
    return savedLocale;
  }

  return defaultLocale;
}

/**
 * next-intl configuration
 * Loads messages from locale JSON files
 */
export default getRequestConfig(async () => {
  const locale = getUserLocale();

  return {
    locale,
    messages: (await import(`./messages/${locale}.json`)).default,
    // Enable strict mode to catch missing keys in development
    onError: (error) => {
      if (process.env.NODE_ENV === 'development') {
        console.error('i18n error:', error);
      }
    },
    getMessageFallback: ({ namespace, key, error }) => {
      const path = [namespace, key].filter((part) => part != null).join('.');

      if (process.env.NODE_ENV === 'development') {
        return `🚨 Missing: ${path}`;
      }

      return path;
    }
  };
});

/**
 * Locale display names
 */
export const localeNames: Record<Locale, string> = {
  en: 'English',
  es: 'Español'
};

/**
 * Locale emoji flags for UI
 */
export const localeFlags: Record<Locale, string> = {
  en: '🇬🇧',
  es: '🇪🇸'
};
