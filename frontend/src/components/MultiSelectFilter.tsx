import { useState, useRef, useEffect } from 'react';
import './MultiSelectFilter.css';

export interface MultiSelectFilterOption {
  value: string;
  label: string;
}

export interface MultiSelectFilterProps {
  label: string;
  options: MultiSelectFilterOption[];
  selected: Set<string>;
  onChange: (selected: Set<string>) => void;
  placeholder?: string;
}

export function MultiSelectFilter({
  label,
  options,
  selected,
  onChange,
  placeholder = 'All',
}: MultiSelectFilterProps) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleToggle = (value: string) => {
    const newSelected = new Set(selected);
    if (newSelected.has(value)) {
      newSelected.delete(value);
    } else {
      newSelected.add(value);
    }
    onChange(newSelected);
  };

  const displayText = selected.size === 0
    ? placeholder
    : selected.size === 1
    ? `${selected.size} selected`
    : `${selected.size} selected`;

  return (
    <div className="chip-select-container" ref={containerRef}>
      {label && <label className="chip-select-label">{label}</label>}
      <div className="chip-select-wrapper">
        <div
          className="chip-select-field"
          onClick={() => setIsOpen(!isOpen)}
        >
          <span className="chip-select-placeholder">{displayText}</span>
          <span className="chip-select-arrow">▼</span>
        </div>
        {isOpen && (
          <div className="chip-select-dropdown">
            {options.map((option) => (
              <div
                key={option.value}
                className={`chip-select-option ${selected.has(option.value) ? 'selected' : ''}`}
                onClick={() => handleToggle(option.value)}
              >
                <input
                  type="checkbox"
                  checked={selected.has(option.value)}
                  onChange={() => {}}
                  readOnly
                />
                <span>{option.label}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

