import './Toggle.css';

interface ToggleProps {
  id: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  label?: string;
}

export default function Toggle({ id, checked, onChange, disabled, label }: ToggleProps) {
  return (
    <label htmlFor={id} className="toggle">
      <input
        id={id}
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        disabled={disabled}
      />
      <span className="toggle__slider" />
      {label && <span className="toggle__label">{label}</span>}
    </label>
  );
}

