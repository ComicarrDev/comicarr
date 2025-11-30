import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ChevronLeft, ChevronRight, X } from 'lucide-react';
import { buildApiUrl } from '../api/client';
import './ReadingPage.css';

type ReadingMode = 'single' | 'double';

export default function ReadingPage() {
  const { issueId } = useParams<{ issueId: string }>();
  const navigate = useNavigate();
  const [pages, setPages] = useState<string[]>([]);
  const [currentPage, setCurrentPage] = useState(0);
  const [readingMode, setReadingMode] = useState<ReadingMode>('single');
  const [doublePageGap, setDoublePageGap] = useState<number>(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [imageLoading, setImageLoading] = useState(true);
  const [imageError, setImageError] = useState<string | null>(null);
  // Track which pages are landscape (width > height) - should be shown alone
  const [doublePages, setDoublePages] = useState<Set<number>>(new Set());

  // Fetch reading settings
  useEffect(() => {
    const fetchReadingSettings = async () => {
      try {
        const response = await fetch(buildApiUrl('/api/settings/reading'), {
          credentials: 'include',
        });
        if (response.ok) {
          const data = await response.json() as { settings: { reading_mode?: ReadingMode; double_page_gap?: number } };
          setReadingMode(data.settings.reading_mode || 'single');
          setDoublePageGap(data.settings.double_page_gap ?? 0);
        }
      } catch (err) {
        console.warn('Failed to fetch reading settings:', err);
      }
    };

    fetchReadingSettings();
  }, []);

  useEffect(() => {
    if (!issueId) {
      setError('Issue ID is required');
      setLoading(false);
      return;
    }

    const fetchPages = async () => {
      try {
        setLoading(true);
        setError(null);
        const response = await fetch(buildApiUrl(`/api/reading/${issueId}/pages`), {
          credentials: 'include',
        });

        if (!response.ok) {
          let errorMessage = 'Issue or file not found';
          try {
            const errorData = await response.json();
            if (errorData.detail) {
              errorMessage = typeof errorData.detail === 'string' 
                ? errorData.detail 
                : 'Issue or file not found';
            }
          } catch {
            // If response is not JSON, use status text
            errorMessage = response.status === 404 
              ? 'Issue or file not found' 
              : `Failed to load pages: ${response.statusText}`;
          }
          setError(errorMessage);
          setLoading(false);
          return;
        }

        const data = await response.json() as { pages: string[] };
        setPages(data.pages || []);
        setCurrentPage(0);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load pages');
      } finally {
        setLoading(false);
      }
    };

    fetchPages();
  }, [issueId]);

  // Check if a page is landscape (width > height) - should be shown alone
  const isLandscapePage = (pageIndex: number): boolean => {
    return doublePages.has(pageIndex);
  };

  // Convert navigation position to actual page indices in double mode
  const getPageIndicesFromPosition = (position: number): { left: number | null; right: number | null } => {
    if (position === 0) {
      // Cover is always alone
      return { left: 0, right: null };
    }

    // Walk through pages after cover to find which pages correspond to this position
    let pageIndex = 1; // Start after cover
    let currentPosition = 1;

    while (pageIndex < pages.length) {
      if (currentPosition === position) {
        // Found the position we're looking for
        // Check if this page is landscape (width > height) - show alone
        if (isLandscapePage(pageIndex)) {
          return { left: pageIndex, right: null };
        }

        // Portrait page - check if we can pair with next page
        if (pageIndex + 1 < pages.length && !isLandscapePage(pageIndex + 1)) {
          // Next page is also portrait, can pair them
          return { left: pageIndex, right: pageIndex + 1 };
        } else {
          // Last page or next is landscape, show current alone
          return { left: pageIndex, right: null };
        }
      }

      // Move to next position
      currentPosition++;
      
      // Move to next page(s)
      if (isLandscapePage(pageIndex)) {
        // Landscape page takes one position alone
        pageIndex++;
      } else {
        // Portrait page - check if we can pair it
        if (pageIndex + 1 < pages.length && !isLandscapePage(pageIndex + 1)) {
          // Paired with next portrait page
          pageIndex += 2;
        } else {
          // Alone (last page or next is landscape)
          pageIndex++;
        }
      }
    }

    // Should not reach here, but return last page if we do
    return { left: pages.length - 1, right: null };
  };

  // Calculate which pages to show based on reading mode
  const getPagesToShow = (): { left: number | null; right: number | null } => {
    if (readingMode === 'single') {
      return { left: currentPage, right: null };
    }

    // Double mode - use position to page index mapping
    return getPageIndicesFromPosition(currentPage);
  };

  // Calculate the maximum page index we can navigate to
  const getMaxPageIndex = (): number => {
    if (readingMode === 'single') {
      return pages.length - 1;
    }

    // In double mode:
    // - Cover (page 0) is alone at position 0
    // - After that, we navigate by spreads (pairs)
    // - Double-page spreads are shown alone and take up one navigation position
    // - If odd number of pages after cover, last page is alone on left
    if (pages.length <= 1) {
      return 0; // Only cover
    }

    // Count navigation positions needed
    // Start with cover (position 0)
    let position = 0;
    let pageIndex = 1; // Start after cover

    while (pageIndex < pages.length) {
      position++;
      
      // If current page is landscape (width > height), it takes one position alone
      if (isLandscapePage(pageIndex)) {
        pageIndex++;
      } else {
        // Portrait page - check if we can pair it with next page
        if (pageIndex + 1 < pages.length && !isLandscapePage(pageIndex + 1)) {
          // Can pair with next portrait page
          pageIndex += 2;
        } else {
          // Last page or next is landscape, show current alone
          pageIndex++;
        }
      }
    }

    return position;
  };

  // Keyboard navigation
  useEffect(() => {
    const handleKeyPress = (event: KeyboardEvent) => {
      if (loading || pages.length === 0) return;

      switch (event.key) {
        case 'ArrowLeft':
          event.preventDefault();
          handlePrevious();
          break;
        case 'ArrowRight':
          event.preventDefault();
          handleNext();
          break;
        case 'Escape':
          event.preventDefault();
          handleClose();
          break;
      }
    };

    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  }, [loading, pages.length, currentPage, readingMode]);

  const handlePrevious = () => {
    if (currentPage > 0) {
      if (readingMode === 'single') {
        setCurrentPage(currentPage - 1);
      } else {
        // Double mode navigation - just decrement position
        setCurrentPage(currentPage - 1);
      }
      setImageLoading(true);
      setImageError(null);
    }
  };

  const handleNext = () => {
    const maxPage = getMaxPageIndex();
    if (currentPage < maxPage) {
      if (readingMode === 'single') {
        setCurrentPage(currentPage + 1);
      } else {
        // Double mode navigation - just increment position
        setCurrentPage(currentPage + 1);
      }
      setImageLoading(true);
      setImageError(null);
    }
  };

  const handleClose = () => {
    navigate(-1); // Go back to previous page
  };

  const getImageUrl = (pageIndex: number) => {
    if (!issueId) return '';
    return buildApiUrl(`/api/reading/${issueId}/page/${pageIndex}`);
  };

  const pagesToShow = getPagesToShow();
  const maxPage = getMaxPageIndex();

  if (loading) {
    return (
      <div className="reading-page">
        <div className="reading-loading">
          <p>Loading comic book…</p>
        </div>
      </div>
    );
  }

  if (error || pages.length === 0) {
    return (
      <div className="reading-page">
        <div className="reading-error">
          <p>{error || 'No pages found'}</p>
          <button onClick={handleClose} className="button primary">
            Close
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="reading-page">
      <div className="reading-controls">
        <button
          onClick={handleClose}
          className="reading-control-button reading-control-close"
          title="Close (Esc)"
        >
          <X size={20} />
        </button>
        <div className="reading-controls-center">
          <button
            onClick={handlePrevious}
            disabled={currentPage === 0}
            className="reading-control-button"
            title="Previous (←)"
          >
            <ChevronLeft size={24} />
          </button>
          <span className="reading-page-info">
            {currentPage + 1} / {maxPage + 1}
          </span>
          <button
            onClick={handleNext}
            disabled={currentPage >= maxPage}
            className="reading-control-button"
            title="Next (→)"
          >
            <ChevronRight size={24} />
          </button>
        </div>
      </div>

      <div className={`reading-content ${readingMode === 'double' ? 'reading-content--double' : ''}`}>
        {imageLoading && (
          <div className="reading-image-loading">
            <p>Loading page…</p>
          </div>
        )}
        {imageError && (
          <div className="reading-image-error">
            <p>{imageError}</p>
          </div>
        )}
        
        {readingMode === 'single' ? (
          <img
            key={pagesToShow.left}
            src={getImageUrl(pagesToShow.left!)}
            alt={`Page ${pagesToShow.left! + 1}`}
            className={`reading-image ${imageLoading ? 'hidden' : ''}`}
            onLoad={(e) => {
              // Check if image is landscape (width > height) - should be shown alone
              const img = e.currentTarget;
              if (pagesToShow.left !== null) {
                if (img.naturalWidth > img.naturalHeight) {
                  // Landscape orientation - mark as double-page (shown alone)
                  setDoublePages(prev => new Set(prev).add(pagesToShow.left!));
                }
              }
              setImageLoading(false);
            }}
            onError={() => {
              setImageLoading(false);
              setImageError('Failed to load image');
            }}
          />
        ) : (
          <div 
            className={`reading-pages-container ${pagesToShow.right === null ? 'reading-pages-container--single' : ''}`}
            style={pagesToShow.right !== null ? { gap: `${doublePageGap}px` } : {}}
          >
            {pagesToShow.left !== null && (
              <div className="reading-page-left">
                <img
                  key={`left-${pagesToShow.left}`}
                  src={getImageUrl(pagesToShow.left)}
                  alt={`Page ${pagesToShow.left + 1}`}
                  className={`reading-image ${imageLoading ? 'hidden' : ''}`}
                  onLoad={(e) => {
                    // Check if image is landscape (width > height) - should be shown alone
                    const img = e.currentTarget;
                    if (img.naturalWidth > img.naturalHeight) {
                      // Landscape orientation - mark as double-page (shown alone)
                      setDoublePages(prev => new Set(prev).add(pagesToShow.left!));
                    }
                    // Only set loading to false when both images are loaded (or if right is null)
                    if (pagesToShow.right === null) {
                      setImageLoading(false);
                    }
                  }}
                  onError={() => {
                    setImageLoading(false);
                    setImageError('Failed to load image');
                  }}
                />
              </div>
            )}
            {pagesToShow.right !== null && (
              <div className="reading-page-right">
                <img
                  key={`right-${pagesToShow.right}`}
                  src={getImageUrl(pagesToShow.right)}
                  alt={`Page ${pagesToShow.right + 1}`}
                  className={`reading-image ${imageLoading ? 'hidden' : ''}`}
                  onLoad={(e) => {
                    // Check if image is landscape (width > height) - should be shown alone
                    const img = e.currentTarget;
                    if (img.naturalWidth > img.naturalHeight) {
                      // Landscape orientation - mark as double-page (shown alone)
                      setDoublePages(prev => new Set(prev).add(pagesToShow.right!));
                    }
                    setImageLoading(false);
                  }}
                  onError={() => {
                    setImageLoading(false);
                    setImageError('Failed to load image');
                  }}
                />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
