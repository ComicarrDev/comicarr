import { SquareCheck, Square, Replace } from 'lucide-react';
import './SelectionControls.css';

export interface SelectionControlsProps {
  selectedCount: number;
  totalCount: number;
  onSelectAll: () => void;
  onSelectNone: () => void;
  onInvertSelection: () => void;
  selectAllLabel?: string;
  selectNoneLabel?: string;
  invertLabel?: string;
  disabled?: boolean;
}

export function SelectionControls({
  selectedCount,
  totalCount,
  onSelectAll,
  onSelectNone,
  onInvertSelection,
  selectAllLabel = 'Select All',
  selectNoneLabel = 'Select None',
  invertLabel = 'Invert Selection',
  disabled = false,
}: SelectionControlsProps) {
  return (
    <div className="selection-controls">
      <button
        type="button"
        className="btn btn-secondary btn-small"
        onClick={onSelectAll}
        title={selectAllLabel}
        disabled={disabled}
      >
        <SquareCheck size={16} />
        {selectAllLabel}
      </button>
      <button
        type="button"
        className="btn btn-secondary btn-small"
        onClick={onSelectNone}
        title={selectNoneLabel}
        disabled={disabled}
      >
        <Square size={16} />
        {selectNoneLabel}
      </button>
      <button
        type="button"
        className="btn btn-secondary btn-small"
        onClick={onInvertSelection}
        title={invertLabel}
        disabled={disabled}
      >
        <Replace size={16} />
        {invertLabel}
      </button>
      {selectedCount > 0 && (
        <span className="selection-controls__count">
          {selectedCount} of {totalCount} selected
        </span>
      )}
    </div>
  );
}


