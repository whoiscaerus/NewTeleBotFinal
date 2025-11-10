/**
 * Theme system entry point
 * Export all available themes and theme utilities
 */
import { professionalTheme } from './professional';
import { darkTraderTheme } from './darkTrader';
import { goldMinimalTheme } from './goldMinimal';

export { professionalTheme, darkTraderTheme, goldMinimalTheme };
export type { ThemeDefinition } from './professional';

export type ThemeName = 'professional' | 'darkTrader' | 'goldMinimal';

export const themes = {
  professional: professionalTheme,
  darkTrader: darkTraderTheme,
  goldMinimal: goldMinimalTheme,
};

export function getTheme(name: ThemeName) {
  return themes[name];
}

export function getAvailableThemes(): ThemeName[] {
  return Object.keys(themes) as ThemeName[];
}
