import './RadioGroup.css';

interface RadioOption {
  value: string;
  label: string;
  description?: string;
}

interface RadioGroupProps {
  name: string;
  value: string;
  options: RadioOption[];
  onChange: (value: string) => void;
  disabled?: boolean;
}

export default function RadioGroup({ name, value, options, onChange, disabled }: RadioGroupProps) {
  return (
    <div className="radio-group">
      {options.map((option) => (
        <label key={option.value} className="radio-group__option">
          <input
            type="radio"
            name={name}
            value={option.value}
            checked={value === option.value}
            onChange={(e) => onChange(e.target.value)}
            disabled={disabled}
            className="radio-group__input"
          />
          <span className="radio-group__indicator" />
          <div className="radio-group__content">
            <span className="radio-group__label">{option.label}</span>
            {option.description && (
              <span className="radio-group__description">{option.description}</span>
            )}
          </div>
        </label>
      ))}
    </div>
  );
}

