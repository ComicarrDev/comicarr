import React from 'react';
import { Pause, Play, RotateCcw } from 'lucide-react';
import './BulkActionsBar.css';

export interface BulkAction {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  variant?: 'primary' | 'secondary' | 'danger';
  icon?: React.ReactNode;
  title?: string;
}

export interface BulkActionsBarProps {
  selectedCount: number;
  progress?: { current: number; total: number; label: string; paused?: boolean } | null;
  actions: BulkAction[];
  children?: React.ReactNode; // For custom content like status dropdown
  onPause?: () => void;
  onResume?: () => void;
  onRestart?: () => void;
}

export function BulkActionsBar({ selectedCount, progress, actions, children, onPause, onResume, onRestart }: BulkActionsBarProps) {
  if (selectedCount === 0 && !progress) {
    return null;
  }

  return (
    <div className="bulk-actions-bar">
      {selectedCount > 0 && (
        <span className="bulk-selection-count">
          {selectedCount} {selectedCount === 1 ? 'item' : 'items'} selected
        </span>
      )}
      {progress && (
        <div className="bulk-progress-indicator">
          <span className="bulk-progress-text">
            {progress.paused ? "Paused: " : ""}{progress.label}: {progress.current}/{progress.total}
          </span>
          <div className="bulk-progress-bar">
            <div
              className="bulk-progress-fill"
              style={{ width: `${(progress.current / progress.total) * 100}%` }}
            />
          </div>
        </div>
      )}
      <div className="bulk-actions-right">
        {progress && onRestart && (
          <button
            type="button"
            className="btn btn-secondary btn-small"
            onClick={onRestart}
            title="Restart"
          >
            <RotateCcw size={14} style={{ marginRight: "0.25rem" }} />
            Restart
          </button>
        )}
        {progress && progress.paused && onResume && (
          <button
            type="button"
            className="btn btn-secondary btn-small"
            onClick={onResume}
            title="Resume"
          >
            <Play size={14} style={{ marginRight: "0.25rem" }} />
            Resume
          </button>
        )}
        {progress && !progress.paused && onPause && (
          <button
            type="button"
            className="btn btn-secondary btn-small"
            onClick={onPause}
            title="Pause"
          >
            <Pause size={14} style={{ marginRight: "0.25rem" }} />
            Pause
          </button>
        )}
        {actions.map((action, index) => (
          <button
            key={index}
            type="button"
            className={`btn btn-${action.variant || 'secondary'} btn-small`}
            onClick={action.onClick}
            disabled={action.disabled}
            title={action.title || action.label}
          >
            {action.icon && <span className="btn-icon">{action.icon}</span>}
            {action.label}
          </button>
        ))}
        {children}
      </div>
    </div>
  );
}


