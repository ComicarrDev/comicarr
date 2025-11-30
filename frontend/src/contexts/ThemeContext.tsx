import { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { ThemeMode, ThemeName, ThemeConfig, getThemeConfig } from '../themes/theme';

const THEME_STORAGE_KEY = 'comicarr-theme';
const THEME_NAME_STORAGE_KEY = 'comicarr-theme-name';

interface ThemeContextType {
  themeName: ThemeName;
  themeMode: ThemeMode;
  themeConfig: ThemeConfig;
  toggleTheme: () => void;
  setThemeMode: (mode: ThemeMode) => void;
  setThemeName: (name: ThemeName) => void;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [themeName, setThemeNameState] = useState<ThemeName>(() => {
    const saved = localStorage.getItem(THEME_NAME_STORAGE_KEY) as ThemeName | null;
    if (saved && ['default', 'A', 'B', 'C', 'D'].includes(saved)) {
      return saved;
    }
    return 'default';
  });

  const [themeMode, setThemeModeState] = useState<ThemeMode>(() => {
    // Check localStorage for explicit theme preference first
    const saved = localStorage.getItem(THEME_STORAGE_KEY) as ThemeMode | null;
    if (saved && (saved === 'dark' || saved === 'light')) {
      return saved;
    }
    // Check UI settings for default theme preference
    try {
      const uiSettings = localStorage.getItem('comicarr-ui-settings');
      if (uiSettings) {
        const parsed = JSON.parse(uiSettings);
        if (parsed.defaultTheme === 'light' || parsed.defaultTheme === 'dark') {
          return parsed.defaultTheme;
        }
      }
    } catch (err) {
      // Ignore errors
    }
    // Fall back to system preference
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      return 'dark';
    }
    return 'dark'; // Default to dark
  });

  const themeConfig = getThemeConfig(themeName, themeMode);

  // Apply theme to CSS variables
  useEffect(() => {
    const root = document.documentElement;
    const config = themeConfig;
    
    // Set theme mode attribute for CSS selectors
    root.setAttribute('data-theme-mode', themeMode);

    // Brand colors
    root.style.setProperty('--color-primary', config.brand.primary);
    root.style.setProperty('--color-primary-hover', config.brand.primaryHover);
    root.style.setProperty('--color-primary-disabled', config.brand.primarySoft);
    root.style.setProperty('--color-secondary', config.brand.secondary);
    root.style.setProperty('--color-secondary-hover', config.brand.secondaryHover);
    root.style.setProperty('--glow-primary', config.brand.glowPrimary);
    root.style.setProperty('--glow-secondary', config.brand.glowSecondary);
    root.style.setProperty('--glow-info', config.brand.glowInfo);
    root.style.setProperty('--glow-primary-button', config.brand.glowPrimary);

    // Neutrals - Background
    root.style.setProperty('--color-bg-main', config.neutrals.background.main);
    root.style.setProperty('--color-bg-panel', config.neutrals.background.panel);
    root.style.setProperty('--color-bg-secondary', config.neutrals.background.panel);
    root.style.setProperty('--color-bg-card', config.neutrals.background.panel);
    root.style.setProperty('--color-bg-elevated', config.neutrals.background.elevated);
    root.style.setProperty('--color-bg-row-hover', config.neutrals.background.rowHover);
    root.style.setProperty('--color-bg-sidebar', config.neutrals.background.sidebar);

    // Neutrals - Borders
    root.style.setProperty('--color-border', config.neutrals.borders.main);
    root.style.setProperty('--color-border-divider', config.neutrals.borders.divider);
    root.style.setProperty('--color-border-active', config.neutrals.borders.active);

    // Neutrals - Text
    root.style.setProperty('--color-text', config.neutrals.text.primary);
    root.style.setProperty('--color-text-secondary', config.neutrals.text.secondary);
    root.style.setProperty('--color-text-muted', config.neutrals.text.muted);
    root.style.setProperty('--color-text-disabled', config.neutrals.text.disabled);

    // Semantic colors
    root.style.setProperty('--color-success', config.semantic.success.base);
    root.style.setProperty('--color-success-hover', config.semantic.success.hover);
    root.style.setProperty('--color-success-bg', config.semantic.success.softBg);
    root.style.setProperty('--color-warning', config.semantic.warning.base);
    root.style.setProperty('--color-warning-hover', config.semantic.warning.hover);
    root.style.setProperty('--color-warning-bg', config.semantic.warning.softBg);
    root.style.setProperty('--color-error', config.semantic.error.base);
    root.style.setProperty('--color-error-hover', config.semantic.error.hover);
    root.style.setProperty('--color-error-bg', config.semantic.error.softBg);
    root.style.setProperty('--color-info', config.semantic.info.base);
    root.style.setProperty('--color-info-hover', config.semantic.info.hover);
    root.style.setProperty('--color-info-bg', config.semantic.info.softBg);

    // Buttons
    root.style.setProperty('--button-primary-bg', config.buttons.primary.bg);
    root.style.setProperty('--button-primary-hover-bg', config.buttons.primary.hoverBg);
    root.style.setProperty('--button-primary-text', config.buttons.primary.text);
    root.style.setProperty('--button-primary-shadow', config.buttons.primary.shadow);
    root.style.setProperty('--button-secondary-bg', config.buttons.secondary.bg);
    root.style.setProperty('--button-secondary-hover-bg', config.buttons.secondary.hoverBg);
    root.style.setProperty('--button-secondary-text', config.buttons.secondary.text);
    root.style.setProperty('--button-secondary-border', config.buttons.secondary.border);
    root.style.setProperty('--button-tertiary-bg', config.buttons.tertiary.bg);
    root.style.setProperty('--button-tertiary-hover-bg', config.buttons.tertiary.hoverBg);
    root.style.setProperty('--button-tertiary-text', config.buttons.tertiary.text);

    // Cards
    root.style.setProperty('--card-bg', config.cards.standard.bg);
    root.style.setProperty('--card-border', config.cards.standard.border);
    root.style.setProperty('--card-shadow', config.cards.standard.shadow);
    root.style.setProperty('--card-hover-bg', config.cards.hoverable.hoverBg);
    root.style.setProperty('--card-highlight-border', config.cards.highlighted.border);
    root.style.setProperty('--card-highlight-glow', config.cards.highlighted.glow);

    // Inputs
    root.style.setProperty('--input-bg', config.inputs.default.bg);
    root.style.setProperty('--input-border', config.inputs.default.border);
    root.style.setProperty('--input-text', config.inputs.default.text);
    root.style.setProperty('--input-placeholder', config.inputs.default.placeholder);
    root.style.setProperty('--input-focus-border', config.inputs.focus.border);
    root.style.setProperty('--input-focus-shadow', config.inputs.focus.shadow);
    root.style.setProperty('--input-disabled-bg', config.inputs.disabled.bg);
    root.style.setProperty('--input-disabled-border', config.inputs.disabled.border);
    root.style.setProperty('--input-disabled-text', config.inputs.disabled.text);

    // Badges
    root.style.setProperty('--badge-default-bg', config.badges.default.bg);
    root.style.setProperty('--badge-default-text', config.badges.default.text);
    root.style.setProperty('--badge-primary-bg', config.badges.primary.bg);
    root.style.setProperty('--badge-primary-text', config.badges.primary.text);
    root.style.setProperty('--badge-secondary-bg', config.badges.secondary.bg);
    root.style.setProperty('--badge-secondary-text', config.badges.secondary.text);

    // Shadows
    root.style.setProperty('--shadow-soft', config.shadows.soft);
    root.style.setProperty('--shadow-medium', config.shadows.medium);
    root.style.setProperty('--shadow-dialog', config.shadows.dialog);

    // Button text colors (for compatibility)
    root.style.setProperty('--color-button-text-dark', config.buttons.primary.text);
    root.style.setProperty('--color-button-text-light', '#FFFFFF');
  }, [themeConfig]);

  const setThemeMode = (mode: ThemeMode) => {
    setThemeModeState(mode);
    localStorage.setItem(THEME_STORAGE_KEY, mode);
  };

  const setThemeName = (name: ThemeName) => {
    setThemeNameState(name);
    localStorage.setItem(THEME_NAME_STORAGE_KEY, name);
  };

  const toggleTheme = () => {
    const newMode = themeMode === 'dark' ? 'light' : 'dark';
    setThemeMode(newMode);
  };

  return (
    <ThemeContext.Provider value={{ themeName, themeMode, themeConfig, toggleTheme, setThemeMode, setThemeName }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (context === undefined) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
}

