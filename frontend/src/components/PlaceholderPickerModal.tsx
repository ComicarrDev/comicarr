import { useState, useEffect } from 'react';
import { X } from 'lucide-react';
import './PlaceholderPickerModal.css';

interface Placeholder {
  token: string;
  description: string;
  example?: string;
}

interface PlaceholderPickerModalProps {
  isOpen: boolean;
  initialValue: string;
  onClose: () => void;
  onApply: (value: string) => void;
  title: string;
}

const PLACEHOLDERS: Placeholder[] = [
  { token: '{Series Title}', description: 'Original series/volume title from Comicvine', example: "The Series Title's!" },
  { token: '{Clean Series Title}', description: 'Series title normalized for sorting', example: "Amazing Spider-Man, The" },
  { token: '{Volume}', description: 'Volume number padded using Volume padding', example: '001' },
  { token: '{Issue}', description: 'Issue number padded using Issue padding', example: '001' },
  { token: '{Year}', description: 'Series year (volume year if present, otherwise the issue year)', example: '2010' },
  { token: '{Issue Title}', description: 'Issue title', example: 'The Amazing Issue' },
  { token: '{Publisher}', description: 'Publisher name', example: 'Marvel Comics' },
  { token: '{Release Date}', description: 'Full release date string', example: '2010-01-15' },
  { token: '{Release Date:%Y}', description: 'Year from release date (strftime format)', example: '2010' },
  { token: '{Release Date:%Y-%m-%d}', description: 'Full date formatted (strftime format)', example: '2010-01-15' },
  { token: '{Release Date:%B %Y}', description: 'Month name and year (strftime format)', example: 'January 2010' },
  { token: '{Comicvine Id}', description: 'Comicvine ID for the volume', example: '4050-91273' },
  { token: '{Issue Comicvine Id}', description: 'Comicvine ID for the issue', example: '4000-1143254' },
  { token: '{Special}', description: 'Special version label (if enabled)', example: 'Variant' },
];

export default function PlaceholderPickerModal({
  isOpen,
  initialValue,
  onClose,
  onApply,
  title,
}: PlaceholderPickerModalProps) {
  const [template, setTemplate] = useState(initialValue);

  useEffect(() => {
    if (isOpen) {
      setTemplate(initialValue);
    }
  }, [isOpen, initialValue]);

  const handlePlaceholderClick = (token: string) => {
    setTemplate((prev) => prev + token);
  };

  const handleApply = () => {
    onApply(template);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="placeholder-picker-overlay" onClick={onClose}>
      <div className="placeholder-picker-modal" onClick={(e) => e.stopPropagation()}>
        <div className="placeholder-picker-header">
          <h2>{title}</h2>
          <button className="placeholder-picker-close" onClick={onClose} type="button">
            <X size={20} />
          </button>
        </div>
        
        <div className="placeholder-picker-body">
          <div className="placeholder-picker-tokens">
            {PLACEHOLDERS.map((placeholder) => (
              <div
                key={placeholder.token}
                className="placeholder-token-item"
                onClick={() => handlePlaceholderClick(placeholder.token)}
              >
                <code className="placeholder-token">{placeholder.token}</code>
                <span className="placeholder-description">{placeholder.description}</span>
                {placeholder.example && (
                  <span className="placeholder-example">{placeholder.example}</span>
                )}
              </div>
            ))}
          </div>
        </div>

        <div className="placeholder-picker-footer">
          <input
            type="text"
            className="placeholder-picker-input"
            value={template}
            onChange={(e) => setTemplate(e.target.value)}
            placeholder="Template will appear here..."
          />
          <div className="placeholder-picker-actions">
            <button className="secondary" onClick={onClose} type="button">
              Close
            </button>
            <button className="primary" onClick={handleApply} type="button">
              OK
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}



