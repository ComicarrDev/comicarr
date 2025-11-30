import { useState } from 'react';
import { Trash2, ToggleLeft, ToggleRight, Wifi } from 'lucide-react';
import { toast } from 'sonner';
import { apiPost, apiPut, ApiClientError } from '../api/client';
import { Indexer } from '../pages/IndexersPage';
import './Card.css';
import './IndexerCard.css';

interface IndexerCardProps {
  indexer: Indexer;
  onEdit: (indexer: Indexer) => void;
  onDelete: (id: string) => void;
  onToggleEnabled: () => void;
}

export default function IndexerCard({ indexer, onEdit, onDelete, onToggleEnabled }: IndexerCardProps) {
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<'success' | 'error' | null>(null);

  const handleTestConnection = async () => {
    setIsTesting(true);
    setTestResult(null);
    try {
      const response = await apiPost<{ success: boolean; message: string }>(`/indexers/${indexer.id}/test`, {});
      if (response.success) {
        setTestResult('success');
        toast.success(`Connection to ${indexer.name} successful!`);
      } else {
        setTestResult('error');
        toast.error(`Connection to ${indexer.name} failed: ${response.message}`);
      }
    } catch (err) {
      setTestResult('error');
      toast.error('Failed to test connection: ' + (err instanceof ApiClientError ? err.message : 'Unknown error'));
    } finally {
      setIsTesting(false);
    }
  };

  const handleToggle = async () => {
    try {
      await apiPut(`/indexers/${indexer.id}`, { enabled: !indexer.enabled });
      toast.success(`Indexer ${indexer.name} ${indexer.enabled ? 'disabled' : 'enabled'}.`);
      onToggleEnabled(); // Reload indexers list
    } catch (err) {
      toast.error('Failed to toggle indexer status: ' + (err instanceof ApiClientError ? err.message : 'Unknown error'));
    }
  };

  const handleCardClick = (e: React.MouseEvent) => {
    // Don't open edit modal if clicking on action buttons
    if ((e.target as HTMLElement).closest('.card-actions')) {
      return;
    }
    onEdit(indexer);
  };

  return (
    <div 
      className={`card indexer-card ${indexer.enabled ? 'card--enabled' : 'card--disabled'}`}
      onClick={handleCardClick}
    >
      <div className="card-header indexer-card-header">
        <h3>{indexer.name}</h3>
        <div className="card-actions indexer-card-actions" onClick={(e) => e.stopPropagation()}>
          <button
            className="button button--icon"
            onClick={handleToggle}
            title={indexer.enabled ? 'Disable Indexer' : 'Enable Indexer'}
          >
            {indexer.enabled ? <ToggleRight size={20} /> : <ToggleLeft size={20} />}
          </button>
          <button
            className="button button--icon"
            onClick={handleTestConnection}
            disabled={isTesting}
            title="Test Connection"
          >
            <Wifi 
              size={20}
              strokeWidth={2}
              color={
                isTesting 
                  ? undefined
                  : testResult === 'success' 
                    ? "rgb(34, 197, 94)" 
                    : testResult === 'error' 
                      ? "rgb(239, 68, 68)" 
                      : undefined
              }
              className={isTesting ? "icon-testing" : ""}
            />
          </button>
          {!indexer.is_builtin && (
            <button className="button button--icon button--danger" onClick={() => onDelete(indexer.id)} title="Delete Indexer">
              <Trash2 size={20} />
            </button>
          )}
        </div>
      </div>
      <div className="card-body indexer-card-body">
        <span className={`indexer-card-type indexer-card-type--${indexer.type}`}>{indexer.type.replace('_', ' ')}</span>
        <div className="indexer-card-capabilities">
          {indexer.enable_rss && <span className="indexer-card-capability">RSS</span>}
          {indexer.enable_automatic_search && <span className="indexer-card-capability">Automatic Search</span>}
          {indexer.enable_interactive_search && <span className="indexer-card-capability">Interactive Search</span>}
        </div>
        {indexer.tags.length > 0 && (
          <div className="indexer-card-tags">
            {indexer.tags.map((tag) => (
              <span key={tag} className="indexer-card-tag">{tag}</span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

