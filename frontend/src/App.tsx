import { Routes, Route } from 'react-router-dom';
import { Toaster } from 'sonner';
import { AuthProvider } from './contexts/AuthContext';
import { ThemeProvider } from './contexts/ThemeContext';
import { ToastProvider, useToast } from './contexts/ToastContext';
import { RequireAuth } from './components/RequireAuth';
import Layout from './components/Layout';
import HomePage from './pages/HomePage';
import LoginPage from './pages/LoginPage';
import SetupPage from './pages/SetupPage';
import SettingsIndexPage from './pages/SettingsIndexPage';
import SettingsPage from './pages/SettingsPage';
import UISettingsPage from './pages/UISettingsPage';
import IndexersPage from './pages/IndexersPage';
import MediaManagementSettingsPage from './pages/MediaManagementSettingsPage';
import LibrariesPage from './pages/LibrariesPage';
import AddLibraryPage from './pages/AddLibraryPage';
import EditLibraryPage from './pages/EditLibraryPage';
import VolumesPage from './pages/VolumesPage';
import AddVolumePage from './pages/AddVolumePage';
import VolumeDetailsPage from './pages/VolumeDetailsPage';
import ImportPage from './pages/ImportPage';
import ReadingPage from './pages/ReadingPage';
import ReadingSettingsPage from './pages/ReadingSettingsPage';
import AdvancedSettingsPage from './pages/AdvancedSettingsPage';
import WeeklyReleasesPage from './pages/WeeklyReleasesPage';
import HistoryPage from './pages/HistoryPage';
import './App.css';

function AppContent() {
  const { enabled } = useToast();

  return (
    <>
      <Routes>
        {/* Public routes without layout */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/setup" element={<SetupPage />} />

        {/* Reading route - fullscreen, no layout */}
        <Route
          path="/reading/:issueId"
          element={
            <RequireAuth>
              <ReadingPage />
            </RequireAuth>
          }
        />

        {/* Protected routes with layout */}
        <Route
          element={
            <RequireAuth>
              <Layout />
            </RequireAuth>
          }
        >
          <Route path="/" element={<HomePage />} />
          <Route path="/library" element={<LibrariesPage />} />
          <Route path="/library/add" element={<AddLibraryPage />} />
          <Route path="/library/:libraryId" element={<EditLibraryPage />} />
          <Route path="/library/import" element={<ImportPage />} />
          <Route path="/volumes" element={<VolumesPage />} />
          <Route path="/volumes/add" element={<AddVolumePage />} />
          <Route path="/volumes/:volumeId" element={<VolumeDetailsPage />} />
          <Route path="/releases" element={<WeeklyReleasesPage />} />
          <Route path="/history" element={<HistoryPage />} />
          <Route path="/settings" element={<SettingsIndexPage />} />
          <Route path="/settings/general" element={<SettingsPage />} />
          <Route path="/settings/ui" element={<UISettingsPage />} />
          <Route path="/settings/indexers" element={<IndexersPage />} />
          <Route path="/settings/media-management" element={<MediaManagementSettingsPage />} />
          <Route path="/settings/reading" element={<ReadingSettingsPage />} />
          <Route path="/settings/advanced" element={<AdvancedSettingsPage />} />
        </Route>
      </Routes>
      {enabled && <Toaster position="bottom-right" richColors />}
    </>
  );
}

function App() {
  return (
    <ThemeProvider>
      <ToastProvider>
        <AuthProvider>
          <AppContent />
        </AuthProvider>
      </ToastProvider>
    </ThemeProvider>
  );
}

export default App;

