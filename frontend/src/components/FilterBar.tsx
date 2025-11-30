import { MultiSelectFilter, MultiSelectFilterOption } from './MultiSelectFilter';
import Toggle from './Toggle';
import './FilterBar.css';

export interface FilterBarFilter {
  id: string;
  label: string;
  type: 'multi-select' | 'toggle' | 'search';
  options?: MultiSelectFilterOption[];
  value: any;
  onChange: (value: any) => void;
  placeholder?: string;
  searchPlaceholder?: string;
}

export interface FilterBarProps {
  filters: FilterBarFilter[];
  onReset: () => void;
  resetLabel?: string;
  layout?: 'horizontal' | 'vertical' | 'grid';
}

export function FilterBar({
  filters,
  onReset,
  resetLabel = 'Reset Filters',
  layout = 'horizontal',
}: FilterBarProps) {
  const layoutClass = `filter-bar--${layout}`;

  return (
    <div className={`filter-bar ${layoutClass}`}>
      {filters.map((filter) => {
        if (filter.type === 'multi-select') {
          return (
            <MultiSelectFilter
              key={filter.id}
              label={filter.label}
              options={filter.options || []}
              selected={filter.value}
              onChange={filter.onChange}
              placeholder={filter.placeholder}
            />
          );
        } else if (filter.type === 'toggle') {
          return (
            <div key={filter.id} className="filter-bar__toggle">
              <Toggle
                id={filter.id}
                label={filter.label}
                checked={filter.value}
                onChange={filter.onChange}
              />
            </div>
          );
        } else if (filter.type === 'search') {
          return (
            <div key={filter.id} className="filter-bar__search">
              <label htmlFor={filter.id}>{filter.label}</label>
              <input
                id={filter.id}
                type="text"
                value={filter.value || ''}
                onChange={(e) => filter.onChange(e.target.value)}
                placeholder={filter.searchPlaceholder || 'Search...'}
                className="filter-bar__search-input"
              />
            </div>
          );
        }
        return null;
      })}
      <button
        type="button"
        className="btn btn-secondary btn-small filter-bar__reset"
        onClick={onReset}
      >
        {resetLabel}
      </button>
    </div>
  );
}



