import { useRef, useState, useCallback } from 'react';

interface UseSettingsChangeDetectionOptions<T> {
    initialValues: T;
    loadFunction: () => Promise<T>;
    onLoadSuccess?: (data: T) => void;
    onLoadError?: (error: Error) => void;
    compareFunction?: (current: T, initial: T) => boolean;
}

/**
 * Custom hook for detecting changes in settings forms.
 * 
 * @template T - The type of the settings object
 * @param options - Configuration options
 * @returns Object with values, setters, loading/saving states, and change detection
 */
export function useSettingsChangeDetection<T extends Record<string, any>>(
    options: UseSettingsChangeDetectionOptions<T>
) {
    const { initialValues, loadFunction, onLoadSuccess, onLoadError, compareFunction } = options;

    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [values, setValues] = useState<T>(initialValues);
    const initialRef = useRef<T | null>(null);

    // Default comparison function
    const defaultCompare = useCallback((current: T, initial: T): boolean => {
        return Object.keys(current).some(key => {
            const currentVal = current[key];
            const initialVal = initial[key];

            // Handle strings with trimming
            if (typeof currentVal === 'string' && typeof initialVal === 'string') {
                return currentVal.trim() !== initialVal.trim();
            }

            // Handle numbers - special case for empty strings that should be treated as numbers
            if (typeof initialVal === 'number') {
                const currentNum = typeof currentVal === 'string' && currentVal.trim() !== ''
                    ? Number(currentVal)
                    : currentVal;
                return currentNum !== initialVal;
            }

            // Default comparison
            return currentVal !== initialVal;
        });
    }, []);

    const hasChanges = initialRef.current && compareFunction
        ? compareFunction(values, initialRef.current)
        : initialRef.current
            ? defaultCompare(values, initialRef.current)
            : false;

    const load = useCallback(async () => {
        try {
            setLoading(true);
            const data = await loadFunction();
            setValues(data);
            initialRef.current = { ...data };
            onLoadSuccess?.(data);
        } catch (err) {
            const error = err instanceof Error ? err : new Error('Failed to load');
            onLoadError?.(error);
            // Don't set ref on error - we can't know the actual state
            // This ensures buttons stay disabled until we successfully load data
        } finally {
            setLoading(false);
        }
    }, [loadFunction, onLoadSuccess, onLoadError]);

    const updateValue = useCallback(<K extends keyof T>(key: K, value: T[K]) => {
        setValues(prev => ({ ...prev, [key]: value }));
    }, []);

    const updateValues = useCallback((updates: Partial<T>) => {
        setValues(prev => ({ ...prev, ...updates }));
    }, []);

    const resetToInitial = useCallback(() => {
        if (initialRef.current) {
            setValues({ ...initialRef.current });
        }
    }, []);

    const markAsSaved = useCallback((savedValues?: T) => {
        const valuesToSave = savedValues || values;
        initialRef.current = { ...valuesToSave };
        setValues(valuesToSave);
    }, [values]);

    return {
        values,
        setValues,
        updateValue,
        updateValues,
        loading,
        saving,
        setSaving,
        hasChanges,
        initialRef,
        load,
        resetToInitial,
        markAsSaved,
    };
}

