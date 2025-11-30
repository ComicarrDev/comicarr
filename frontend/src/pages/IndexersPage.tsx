import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Plus } from 'lucide-react';
import { apiGet, apiDelete, ApiClientError } from '../api/client';
import IndexerCard from '../components/IndexerCard';
import IndexerModal from '../components/IndexerModal';
import './IndexersPage.css';

export interface Indexer {
  id: string;
  name: string;
  type: string;
  is_builtin: boolean;
  enabled: boolean;
  priority: number;
  config: { [key: string]: any };
  enable_rss: boolean;
  enable_automatic_search: boolean;
  enable_interactive_search: boolean;
  tags: string[];
  created_at: number;
  updated_at: number;
}

export interface IndexerType {
  id: string;
  name: string;
  category: 'Usenet' | 'Torrents' | 'Built-in';
  description: string;
  fields: { id: string; name: string; type: string; required?: boolean; default?: any; placeholder?: string; help?: string; disabled?: boolean; options?: { id: string; name: string }[] }[];
}

export default function IndexersPage() {
  const [indexers, setIndexers] = useState<Indexer[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingIndexer, setEditingIndexer] = useState<Indexer | null>(null);
  const [indexerTypes, setIndexerTypes] = useState<IndexerType[]>([]);

  useEffect(() => {
    loadIndexers();
    loadIndexerTypes();
  }, []);

  async function loadIndexers() {
    try {
      setLoading(true);
      setError(null);
      const data = await apiGet<Indexer[]>('/indexers');
      setIndexers(data);
    } catch (err) {
      if (err instanceof ApiClientError) {
        setError(err.message);
      } else {
        setError('An unknown error occurred.');
      }
      toast.error('Failed to load indexers: ' + (err instanceof ApiClientError ? err.message : 'Unknown error'));
    } finally {
      setLoading(false);
    }
  }

  async function loadIndexerTypes() {
    try {
      const data = await apiGet<IndexerType[]>('/indexers/types');
      setIndexerTypes(data);
    } catch (err) {
      toast.error('Failed to load indexer types: ' + (err instanceof ApiClientError ? err.message : 'Unknown error'));
    }
  }

  async function handleDeleteIndexer(id: string) {
    if (!window.confirm('Are you sure you want to delete this indexer?')) {
      return;
    }
    try {
      await apiDelete(`/indexers/${id}`);
      toast.success('Indexer deleted successfully.');
      loadIndexers();
    } catch (err) {
      toast.error('Failed to delete indexer: ' + (err instanceof ApiClientError ? err.message : 'Unknown error'));
    }
  }

  const handleOpenAddModal = () => {
    setEditingIndexer(null);
    setIsModalOpen(true);
  };

  const handleOpenEditModal = (indexer: Indexer) => {
    setEditingIndexer(indexer);
    setIsModalOpen(true);
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
    setEditingIndexer(null);
  };

  const handleIndexerSaved = () => {
    loadIndexers();
    handleCloseModal();
  };

  if (loading) {
    return (
      <div className="indexers-page">
        <p>Loading indexers...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="indexers-page">
        <p className="error-message">{error}</p>
        <button onClick={loadIndexers} className="button button--primary">
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="indexers-page">
      <div className="settings-header">
        <p>
          Manage your content indexers for searching and downloading comics.
        </p>
      </div>
      <button className="indexer-add-button" onClick={handleOpenAddModal}>
        <Plus size={20} />
        <span>Add Indexer</span>
      </button>

      <div className="indexers-grid">
        {indexers.map((indexer) => (
          <IndexerCard
            key={indexer.id}
            indexer={indexer}
            onEdit={handleOpenEditModal}
            onDelete={handleDeleteIndexer}
            onToggleEnabled={loadIndexers} // Reload after toggle
          />
        ))}
      </div>

      {isModalOpen && (
        <IndexerModal
          indexer={editingIndexer}
          indexerTypes={indexerTypes}
          onClose={handleCloseModal}
          onSave={handleIndexerSaved}
        />
      )}
    </div>
  );
}
