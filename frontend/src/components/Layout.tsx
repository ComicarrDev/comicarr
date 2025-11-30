import { useState, useEffect } from 'react';
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import {
  Home,
  Library,
  Inbox,
  History,
  Settings,
  ChevronDown,
  ChevronRight,
  ChevronLeft,
  LogOut,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { getBaseUrl } from '../api/client';
import ThemeToggle from './ThemeToggle';
import './Layout.css';

interface NavItem {
  id: string;
  label: string;
  to: string;
  icon: React.ComponentType<{ size?: number | string; className?: string }>;
  children?: Array<{ id: string; label: string; to: string }>;
}

export default function Layout() {
  const { authenticated, authMethod, logout, username } = useAuth();
  const location = useLocation();
  const baseUrl = getBaseUrl();
  const logoPath = `${baseUrl}/comicarr_logo.png`;

  // Sidebar collapse state (persisted to localStorage)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    const saved = localStorage.getItem('sidebarCollapsed');
    return saved ? JSON.parse(saved) : false;
  });

  // Save collapse state to localStorage
  useEffect(() => {
    localStorage.setItem('sidebarCollapsed', JSON.stringify(sidebarCollapsed));
  }, [sidebarCollapsed]);

  // Determine which section should be expanded based on current route
  const getActiveSection = (pathname: string) => {
    // Check specific routes first (more specific before general)
    if (pathname.startsWith('/volumes') || pathname.startsWith('/library/import') || pathname.startsWith('/releases')) {
      return 'library';
    }
    if (pathname.startsWith('/settings') || (pathname.startsWith('/library') && !pathname.startsWith('/library/import'))) {
      return 'settings';
    }
    return null;
  };

  const [expandedSection, setExpandedSection] = useState<string | null>(() =>
    getActiveSection(location.pathname)
  );

  // Update expanded section when route changes
  useEffect(() => {
    const activeSection = getActiveSection(location.pathname);
    if (activeSection) {
      setExpandedSection(activeSection);
    }
  }, [location.pathname]);

  // Breadcrumb component
  function Breadcrumb() {
    const pathname = location.pathname;

    const pathLabels: Record<string, string> = {
      library: 'Libraries',
      libraries: 'Libraries',
      volumes: 'Library',
      'add': 'Add',
      import: 'Import',
      releases: 'Weekly Releases',
      queue: 'Queue',
      history: 'History',
      settings: 'Settings',
      'media-management': 'Media Management',
      indexers: 'Indexers',
      general: 'General',
      ui: 'UI',
      reading: 'Reading',
      advanced: 'Advanced',
    };

    const buildBreadcrumb = () => {
      const segments = pathname.split('/').filter(Boolean);

      if (segments.length === 0) {
        return ['Home'];
      }

      const breadcrumbs: Array<string> = [];

      if (segments[0] === 'library') {
        breadcrumbs.push('Library');
        if (segments[1] === 'add') {
          breadcrumbs.push('Add Library');
        } else if (segments[1] === 'import') {
          breadcrumbs.push('Import');
        } else if (segments[1] && segments[1] !== 'add' && segments[1] !== 'import') {
          breadcrumbs.push('Edit Library');
        } else {
          breadcrumbs.push('Libraries');
        }
      } else if (segments[0] === 'volumes') {
        breadcrumbs.push('Library');
        if (segments[1] === 'add') {
          breadcrumbs.push('Add Volume');
        } else if (segments[1] && segments[1] !== 'add') {
          breadcrumbs.push('Volume Details');
        }
      } else if (segments[0] === 'queue') {
        breadcrumbs.push('Queue');
      } else if (segments[0] === 'history') {
        breadcrumbs.push('History');
      } else if (segments[0] === 'settings') {
        breadcrumbs.push('Settings');
        if (segments[1]) {
          const label = pathLabels[segments[1]] || segments[1].charAt(0).toUpperCase() + segments[1].slice(1);
          breadcrumbs.push(label);
        }
      } else {
        segments.forEach((seg) => {
          breadcrumbs.push(pathLabels[seg] || seg);
        });
      }

      return breadcrumbs;
    };

    const breadcrumbs = buildBreadcrumb();

    return (
      <nav className="layout__breadcrumb" aria-label="Breadcrumb">
        {breadcrumbs.map((crumb, index) => (
          <span key={index}>
            {index > 0 && <span className="layout__breadcrumb-separator"> / </span>}
            <span>{crumb}</span>
          </span>
        ))}
      </nav>
    );
  }

  const navItems: NavItem[] = [
    {
      id: 'home',
      label: 'Home',
      to: '/',
      icon: Home,
    },
    {
      id: 'library',
      label: 'Library',
      to: '/volumes',
      icon: Library,
      children: [
        { id: 'library-import', label: 'Import', to: '/library/import' },
        { id: 'library-releases', label: 'Weekly Releases', to: '/releases' },
      ],
    },
    {
      id: 'queue',
      label: 'Queue',
      to: '/queue',
      icon: Inbox,
    },
    {
      id: 'history',
      label: 'History',
      to: '/history',
      icon: History,
    },
    {
      id: 'settings',
      label: 'Settings',
      to: '/settings',
      icon: Settings,
      children: [
        { id: 'settings-media-management', label: 'Media Management', to: '/settings/media-management' },
        { id: 'settings-libraries', label: 'Libraries', to: '/library' },
        { id: 'settings-indexers', label: 'Indexers', to: '/settings/indexers' },
        { id: 'settings-general', label: 'General', to: '/settings/general' },
        { id: 'settings-ui', label: 'UI', to: '/settings/ui' },
        { id: 'settings-reading', label: 'Reading', to: '/settings/reading' },
        { id: 'settings-advanced', label: 'Advanced', to: '/settings/advanced' },
      ],
    },
  ];

  const handleToggle = (id: string) => {
    setExpandedSection((current) => (current === id ? null : id));
  };

  // Only show auth controls when authentication is enabled (forms) and user is authenticated
  const showAuthControls = authMethod !== 'none' && authMethod === 'forms' && authenticated;

  return (
    <div className={`layout ${sidebarCollapsed ? 'layout--sidebar-collapsed' : ''}`}>
      <aside className="layout__sidebar">
        {/* Notch on the right side to toggle collapse/expand */}
        <button
          type="button"
          className="layout__sidebar-notch"
          onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
          aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {sidebarCollapsed ? (
            <ChevronRight size={18} className="layout__sidebar-notch-icon" />
          ) : (
            <ChevronLeft size={18} className="layout__sidebar-notch-icon" />
          )}
        </button>

        <header className="layout__sidebar-header">
          {!sidebarCollapsed ? (
            <Link to="/" className="layout__sidebar-brand">
              <img
                src={logoPath}
                alt="Comicarr"
                className="layout__sidebar-logo"
              />
              <span className="layout__sidebar-brand-text">Comicarr</span>
            </Link>
          ) : (
            <div className="layout__sidebar-brand-collapsed">
              <Link to="/" className="layout__sidebar-brand-link">
                <img
                  src={logoPath}
                  alt="Comicarr"
                  className="layout__sidebar-logo-collapsed"
                />
              </Link>
            </div>
          )}
        </header>
        <nav className="layout__sidebar-nav">
          {navItems.map((item) => {
            const Icon = item.icon;
            return item.children ? (
              <div key={item.id} className="layout__sidebar-group">
                <NavLink
                  to={item.to}
                  className={({ isActive }) =>
                    `layout__sidebar-toggle-item ${expandedSection === item.id || isActive ? 'active' : ''
                    }`
                  }
                  onClick={() => {
                    // Navigate and expand/collapse on click
                    handleToggle(item.id);
                  }}
                  title={sidebarCollapsed ? item.label : undefined}
                >
                  <Icon size={20} className="layout__sidebar-icon" />
                  {!sidebarCollapsed && <span>{item.label}</span>}
                  {!sidebarCollapsed && (
                    <span className="layout__sidebar-caret">
                      {expandedSection === item.id ? (
                        <ChevronDown size={16} />
                      ) : (
                        <ChevronRight size={16} />
                      )}
                    </span>
                  )}
                </NavLink>
                {!sidebarCollapsed && (
                  <div
                    className={`layout__sidebar-subnav ${expandedSection === item.id ? 'expanded' : ''
                      }`}
                  >
                    {item.children.map((child) => (
                      <NavLink
                        key={child.id}
                        to={child.to}
                        className={({ isActive }) =>
                          `layout__sidebar-nav-link layout__sidebar-nav-link--child${isActive ? ' active' : ''
                          }`
                        }
                      >
                        {child.label}
                      </NavLink>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <NavLink
                key={item.id}
                to={item.to}
                end={item.to === '/'}
                className={({ isActive }) =>
                  `layout__sidebar-nav-link${isActive ? ' active' : ''}`
                }
                title={sidebarCollapsed ? item.label : undefined}
                onClick={() => setExpandedSection(null)}
              >
                <Icon size={20} className="layout__sidebar-icon" />
                {!sidebarCollapsed && <span>{item.label}</span>}
              </NavLink>
            );
          })}
        </nav>
      </aside>
      <div className="layout__content">
        <header className="layout__header">
          <div className="layout__header-left">
            <Breadcrumb />
          </div>
          <div className="layout__header-right">
            <div className="layout__header-actions">
              <ThemeToggle />
              {showAuthControls && (
                <>
                  <span className="layout__header-user">
                    Signed in as {username || 'User'}
                  </span>
                  <button
                    type="button"
                    className="layout__header-button secondary"
                    onClick={() => logout()}
                    title="Log out"
                    aria-label="Log out"
                  >
                    <LogOut size={20} />
                  </button>
                </>
              )}
            </div>
          </div>
        </header>
        <main className="layout__main">
          <Outlet />
        </main>
      </div>
    </div>
  );
}