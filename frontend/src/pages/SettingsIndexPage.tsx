import { Link } from 'react-router-dom';
import { Settings, Search, Folder, Palette, Library, BookOpen, Sliders } from 'lucide-react';
import '../components/Card.css';
import './SettingsIndexPage.css';

interface SettingsCategory {
  id: string;
  title: string;
  description: string;
  to: string;
  icon: React.ComponentType<{ size?: number | string; className?: string }>;
}

export default function SettingsIndexPage() {
  const categories: SettingsCategory[] = [
    {
      id: 'media-management',
      title: 'Media Management',
      description: 'Configure root folders where Comicarr will organize your library.',
      to: '/settings/media-management',
      icon: Folder,
    },
    {
      id: 'libraries',
      title: 'Libraries',
      description: 'Manage your libraries and configure include paths for organizing volumes.',
      to: '/library',
      icon: Library,
    },
    {
      id: 'indexers',
      title: 'Indexers',
      description: 'Manage your content indexers for searching and downloading comics.',
      to: '/settings/indexers',
      icon: Search,
    },
    {
      id: 'general',
      title: 'General',
      description: 'Configure host settings, authentication, and external API integrations.',
      to: '/settings/general',
      icon: Settings,
    },
    {
      id: 'ui',
      title: 'UI',
      description: 'Configure user interface preferences, theme, and notification settings.',
      to: '/settings/ui',
      icon: Palette,
    },
    {
      id: 'reading',
      title: 'Reading',
      description: 'Configure reading functionality, display modes, and progress tracking.',
      to: '/settings/reading',
      icon: BookOpen,
    },
    {
      id: 'advanced',
      title: 'Advanced',
      description: 'Configure advanced matching parameters for ComicVine integration.',
      to: '/settings/advanced',
      icon: Sliders,
    },
  ];

  return (
    <div className="settings-index-page">
      <div className="settings-index-header">
        <p>Configure Comicarr application settings</p>
      </div>

      <div className="settings-index-grid">
        {categories.map((category) => {
          const IconComponent = category.icon;
          return (
            <Link
              key={category.id}
              to={category.to}
              className="card card--clickable settings-index-card"
            >
              <div className="card-icon settings-index-card-icon">
                <IconComponent size={24} />
              </div>
              <div className="card-content settings-index-card-content">
                <h2>{category.title}</h2>
                <p>{category.description}</p>
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}

