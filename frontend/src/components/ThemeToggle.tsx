import { Moon, Sun } from 'lucide-react';
import { useTheme } from '../contexts/ThemeContext';
import './ThemeToggle.css';

export default function ThemeToggle() {
  const { themeMode, toggleTheme } = useTheme();

  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={toggleTheme}
      aria-label={`Switch to ${themeMode === 'dark' ? 'light' : 'dark'} mode`}
      title={`Switch to ${themeMode === 'dark' ? 'light' : 'dark'} mode`}
    >
      {themeMode === 'dark' ? (
        <Sun size={18} strokeWidth={2} />
      ) : (
        <Moon size={18} strokeWidth={2} />
      )}
    </button>
  );
}

