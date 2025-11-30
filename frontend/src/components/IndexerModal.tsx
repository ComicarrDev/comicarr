import { useState, useEffect } from 'react';
import { X, Check, Wifi } from 'lucide-react';
import { toast } from 'sonner';
import { apiPost, apiPut, ApiClientError } from '../api/client';
import Toggle from './Toggle';
import { Indexer, IndexerType } from '../pages/IndexersPage';
import './IndexerModal.css';

interface IndexerModalProps {
  indexer: Indexer | null; // Null for add, object for edit
  indexerTypes: IndexerType[];
  onClose: () => void;
  onSave: () => void;
}

export default function IndexerModal({ indexer, indexerTypes, onClose, onSave }: IndexerModalProps) {
  const [step, setStep] = useState<'select' | 'configure'>(indexer ? 'configure' : 'select');
  const [selectedType, setSelectedType] = useState<string>(indexer?.type || '');
  const [name, setName] = useState(indexer?.name || '');
  const [enabled, setEnabled] = useState(indexer?.enabled ?? true);
  const [priority, setPriority] = useState(String(indexer?.priority ?? 0));
  const [config, setConfig] = useState<{ [key: string]: any }>(indexer?.config || {});
  const [enableRss, setEnableRss] = useState(indexer?.enable_rss ?? true);
  const [enableAutomaticSearch, setEnableAutomaticSearch] = useState(indexer?.enable_automatic_search ?? true);
  const [enableInteractiveSearch, setEnableInteractiveSearch] = useState(indexer?.enable_interactive_search ?? true);
  const [tags, setTags] = useState(indexer?.tags.join(', ') || '');
  const [isSaving, setIsSaving] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<'success' | 'error' | null>(null);

  useEffect(() => {
    if (indexer) {
      setSelectedType(indexer.type);
      setName(indexer.name);
      setEnabled(indexer.enabled);
      setPriority(String(indexer.priority));
      setConfig(indexer.config);
      setEnableRss(indexer.enable_rss);
      setEnableAutomaticSearch(indexer.enable_automatic_search);
      setEnableInteractiveSearch(indexer.enable_interactive_search);
      setTags(indexer.tags.join(', '));
      setStep('configure');
    }
  }, [indexer]);

  const handleTypeSelect = (typeId: string) => {
    setSelectedType(typeId);
    const typeDef = indexerTypes.find((t) => t.id === typeId);
    if (typeDef) {
      // Initialize config with default values from type definition
      const initialConfig: { [key: string]: any } = {};
      typeDef.fields.forEach(field => {
        if (field.default !== undefined) {
          initialConfig[field.id] = field.default;
        } else if (field.type === 'number') {
          initialConfig[field.id] = 0;
        } else if (field.type === 'boolean') {
          initialConfig[field.id] = false;
        } else if (field.type === 'multiselect') {
          initialConfig[field.id] = [];
        } else {
          initialConfig[field.id] = '';
        }
      });
      setConfig(initialConfig);
      setName(typeDef.name); // Pre-fill name with type name
    }
    setStep('configure');
  };

  const handleConfigChange = (fieldId: string, value: any) => {
    setConfig((prevConfig) => ({ ...prevConfig, [fieldId]: value }));
    setTestResult(null); // Clear test result on config change
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      const payload = {
        name,
        type: selectedType,
        enabled,
        priority: Number(priority),
        config,
        enable_rss: enableRss,
        enable_automatic_search: enableAutomaticSearch,
        enable_interactive_search: enableInteractiveSearch,
        tags: tags.split(',').map((tag) => tag.trim()).filter(Boolean),
      };

      if (indexer) {
        // Update existing indexer
        await apiPut(`/indexers/${indexer.id}`, payload);
        toast.success('Indexer updated successfully.');
      } else {
        // Create new indexer
        await apiPost('/indexers', payload);
        toast.success('Indexer added successfully.');
      }
      onSave();
    } catch (err) {
      toast.error('Failed to save indexer: ' + (err instanceof ApiClientError ? err.message : 'Unknown error'));
    } finally {
      setIsSaving(false);
    }
  };

  const handleTestConnection = async () => {
    if (!indexer) {
      toast.error('Cannot test connection for unsaved indexer.');
      return;
    }
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

  const currentType = indexerTypes.find((t) => t.id === selectedType);

  return (
    <div className="indexer-modal-overlay" onClick={onClose}>
      <div className="indexer-modal" onClick={(e) => e.stopPropagation()}>
        <div className="indexer-modal-header">
          <h2>
            {indexer ? `Edit Indexer - ${indexer.name}` : step === 'select' ? 'Add Indexer' : `Add Indexer - ${currentType?.name || ''}`}
          </h2>
          <button
            type="button"
            className="indexer-modal-close"
            onClick={onClose}
            aria-label="Close"
          >
            <X size={20} />
          </button>
        </div>

        <div className="indexer-modal-body">
          {step === 'select' ? (
            <div className="indexer-modal-types">
              <div className="indexer-modal-types-intro">
                <p>
                  Comicarr supports indexers that use the Newznab standard, as well as torrent indexers.
                  For more information on the individual indexers, click on the more info buttons.
                </p>
              </div>

              <div className="indexer-modal-types-section">
                <h3>Usenet</h3>
                <div className="indexer-modal-types-grid">
                  {indexerTypes
                    .filter((t) => t.category === 'Usenet')
                    .map((type) => (
                      <button
                        key={type.id}
                        type="button"
                        className="indexer-modal-type-card"
                        onClick={() => handleTypeSelect(type.id)}
                      >
                        <div className="indexer-modal-type-card-name">{type.name}</div>
                        <button
                          type="button"
                          className="indexer-modal-type-card-info"
                          onClick={(e) => {
                            e.stopPropagation();
                            // TODO: Show more info
                            toast.info(`More info for ${type.name}`);
                          }}
                        >
                          More Info
                        </button>
                      </button>
                    ))}
                </div>
              </div>

              <div className="indexer-modal-types-section">
                <h3>Torrents</h3>
                <div className="indexer-modal-types-grid">
                  {indexerTypes
                    .filter((t) => t.category === 'Torrents')
                    .map((type) => (
                      <button
                        key={type.id}
                        type="button"
                        className="indexer-modal-type-card"
                        onClick={() => handleTypeSelect(type.id)}
                      >
                        <div className="indexer-modal-type-card-name">{type.name}</div>
                        <button
                          type="button"
                          className="indexer-modal-type-card-info"
                          onClick={(e) => {
                            e.stopPropagation();
                            // TODO: Show more info
                            toast.info(`More info for ${type.name}`);
                          }}
                        >
                          More Info
                        </button>
                      </button>
                    ))}
                </div>
              </div>
            </div>
          ) : (
            <div className="indexer-modal-form">
              <div className="form-field">
                <label htmlFor="name">Name</label>
                <input
                  id="name"
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  disabled={isSaving || indexer?.is_builtin}
                />
              </div>

              <div className="form-field">
                <Toggle
                  id="enabled"
                  checked={enabled}
                  onChange={setEnabled}
                  disabled={isSaving || indexer?.is_builtin}
                  label={enabled ? 'Enabled' : 'Disabled'}
                />
              </div>

              <div className="form-field">
                <label htmlFor="priority">Priority</label>
                <input
                  id="priority"
                  type="number"
                  value={priority}
                  onChange={(e) => setPriority(e.target.value)}
                  disabled={isSaving}
                />
                <p className="help-text">Lower numbers have higher priority.</p>
              </div>

              <div className="form-field">
                <Toggle
                  id="enable-rss"
                  checked={enableRss}
                  onChange={setEnableRss}
                  disabled={isSaving}
                  label="Enable RSS"
                />
                <p className="help-text">Will be used when Comicarr periodically looks for releases via RSS Sync.</p>
              </div>

              <div className="form-field">
                <Toggle
                  id="enable-automatic-search"
                  checked={enableAutomaticSearch}
                  onChange={setEnableAutomaticSearch}
                  disabled={isSaving}
                  label="Enable Automatic Search"
                />
                <p className="help-text">Will be used when automatic searches are performed via the UI or by Comicarr.</p>
              </div>

              <div className="form-field">
                <Toggle
                  id="enable-interactive-search"
                  checked={enableInteractiveSearch}
                  onChange={setEnableInteractiveSearch}
                  disabled={isSaving}
                  label="Enable Interactive Search"
                />
                <p className="help-text">Will be used when interactive search is used.</p>
              </div>

              {currentType?.fields.map((fieldDef) => (
                <div className="form-field" key={fieldDef.id}>
                  <label htmlFor={fieldDef.id}>{fieldDef.name}</label>
                  {fieldDef.type === 'text' && (
                    <input
                      id={fieldDef.id}
                      type="text"
                      value={config[fieldDef.id] || ''}
                      onChange={(e) => handleConfigChange(fieldDef.id, e.target.value)}
                      disabled={isSaving || fieldDef.disabled}
                      placeholder={fieldDef.placeholder}
                    />
                  )}
                  {fieldDef.type === 'password' && (
                    <input
                      id={fieldDef.id}
                      type="password"
                      value={config[fieldDef.id] || ''}
                      onChange={(e) => handleConfigChange(fieldDef.id, e.target.value)}
                      disabled={isSaving || fieldDef.disabled}
                      placeholder={fieldDef.placeholder}
                    />
                  )}
                  {fieldDef.type === 'number' && (
                    <input
                      id={fieldDef.id}
                      type="number"
                      value={config[fieldDef.id] || ''}
                      onChange={(e) => handleConfigChange(fieldDef.id, Number(e.target.value))}
                      disabled={isSaving || fieldDef.disabled}
                      placeholder={fieldDef.placeholder}
                    />
                  )}
                  {fieldDef.type === 'multiselect' && (
                    <div className="multiselect-container">
                      {fieldDef.options && fieldDef.options.length > 0 ? (
                        <div className="multiselect-checkboxes">
                          {fieldDef.options.map((option: { id: string; name: string }) => {
                            const categoryId = option.id;
                            const categoryName = option.name;
                            const isChecked = Array.isArray(config[fieldDef.id])
                              ? config[fieldDef.id].includes(categoryId) || config[fieldDef.id].includes(String(categoryId))
                              : false;
                            
                            return (
                              <label key={categoryId} className="multiselect-checkbox-label">
                                <input
                                  type="checkbox"
                                  checked={isChecked}
                                  onChange={(e) => {
                                    const currentValues = Array.isArray(config[fieldDef.id]) 
                                      ? config[fieldDef.id].map((v: unknown) => String(v))
                                      : [];
                                    const categoryIdStr = String(categoryId);
                                    
                                    let newValues: string[];
                                    if (e.target.checked) {
                                      // Add category ID if not already present
                                      if (!currentValues.includes(categoryIdStr)) {
                                        newValues = [...currentValues, categoryIdStr];
                                      } else {
                                        newValues = currentValues;
                                      }
                                    } else {
                                      // Remove category ID
                                      newValues = currentValues.filter((v: string) => v !== categoryIdStr);
                                    }
                                    handleConfigChange(fieldDef.id, newValues);
                                  }}
                                  disabled={isSaving || fieldDef.disabled}
                                />
                                <span>{categoryName}</span>
                              </label>
                            );
                          })}
                        </div>
                      ) : (
                        <input
                          id={fieldDef.id}
                          type="text"
                          value={
                            Array.isArray(config[fieldDef.id])
                              ? config[fieldDef.id].join(', ')
                              : typeof config[fieldDef.id] === 'string'
                              ? config[fieldDef.id]
                              : ''
                          }
                          onChange={(e) => {
                            // Parse comma-separated values into array, filtering out empty strings
                            const values = e.target.value.split(',').map(v => v.trim()).filter(v => v.length > 0);
                            handleConfigChange(fieldDef.id, values);
                          }}
                          disabled={isSaving || fieldDef.disabled}
                          placeholder={fieldDef.placeholder || "Comma-separated values (e.g., 7000, 7010)"}
                        />
                      )}
                    </div>
                  )}
                  {fieldDef.help && <p className="help-text">{fieldDef.help}</p>}
                </div>
              ))}

              <div className="form-field">
                <label htmlFor="tags">Tags</label>
                <input
                  id="tags"
                  type="text"
                  value={tags}
                  onChange={(e) => setTags(e.target.value)}
                  disabled={isSaving}
                  placeholder="comma, separated, tags"
                />
                <p className="help-text">Only use this indexer for series with at least one matching tag. Leave blank to use with all series.</p>
              </div>
            </div>
          )}
        </div>

        <div className="indexer-modal-footer">
          {step === 'configure' && (
            <button
              type="button"
              className="button button--icon"
              onClick={handleTestConnection}
              disabled={isTesting || !indexer}
              title="Test Connection"
            >
              <Wifi 
                size={20}
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
          )}
          <button 
            type="button" 
            className="button button--icon" 
            onClick={onClose} 
            disabled={isSaving}
            title="Cancel"
          >
            <X size={20} />
          </button>
          {step === 'configure' && (
            <button 
              type="button" 
              className="button button--icon" 
              onClick={handleSave} 
              disabled={isSaving}
              title={isSaving ? 'Saving...' : 'Save'}
            >
              <Check size={20} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

