import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';
import {
  Box,
  CircularProgress,
  IconButton,
  TextField,
  Typography,
  Snackbar,
  Alert,
  Stack,
  Tooltip,
  LinearProgress,
  Button
} from '@mui/material';
import {
  ZoomIn,
  ZoomOut,
  ZoomOutMap,
  Search as SearchIcon,
  NavigateBefore,
  NavigateNext,
  Close,
  SwapHoriz,
  SwapVert
} from '@mui/icons-material';
import { APP_CONFIG } from '../../config';
import { api } from '../../api/client';

// Configure PDF.js worker
pdfjs.GlobalWorkerOptions.workerSrc = `https://cdn.jsdelivr.net/npm/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

// Fuzzy matching using Levenshtein distance
function levenshteinDistance(a: string, b: string): number {
  const matrix: number[][] = [];
  for (let i = 0; i <= b.length; i++) {
    matrix[i] = [i];
  }
  for (let j = 0; j <= a.length; j++) {
    matrix[0][j] = j;
  }
  for (let i = 1; i <= b.length; i++) {
    for (let j = 1; j <= a.length; j++) {
      if (b.charAt(i - 1) === a.charAt(j - 1)) {
        matrix[i][j] = matrix[i - 1][j - 1];
      } else {
        matrix[i][j] = Math.min(
          matrix[i - 1][j - 1] + 1,
          matrix[i][j - 1] + 1,
          matrix[i - 1][j] + 1
        );
      }
    }
  }
  return matrix[b.length][a.length];
}

function fuzzyMatch(snippet: string, text: string): number {
  const snippetClean = snippet.toLowerCase().trim();
  const textClean = text.toLowerCase();
  
  // Try exact match first
  if (textClean.includes(snippetClean)) {
    return 100;
  }
  
  // Sliding window fuzzy match
  const snippetLen = snippetClean.length;
  let bestSimilarity = 0;
  
  for (let i = 0; i <= textClean.length - snippetLen; i++) {
    const window = textClean.substring(i, i + snippetLen);
    const distance = levenshteinDistance(snippetClean, window);
    const similarity = 100 * (1 - distance / snippetLen);
    if (similarity > bestSimilarity) {
      bestSimilarity = similarity;
    }
  }
  
  return bestSimilarity;
}

interface PdfViewerPanelProps {
  scanId: number;
  pdfSnippet?: string | null;
  initialPage?: number | null;
  navigationKey?: number; // Changes when navigation is requested to force re-navigation
  onClose?: () => void;
  orientation?: 'horizontal' | 'vertical'; // Split view orientation
  onToggleOrientation?: () => void; // Toggle split orientation
}

export const PdfViewerPanel: React.FC<PdfViewerPanelProps> = ({
  scanId,
  pdfSnippet,
  initialPage,
  navigationKey,
  onClose,
  orientation,
  onToggleOrientation
}) => {
  const [numPages, setNumPages] = useState<number>(0);
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [scale, setScale] = useState<number>(1.0);
  const [searchText, setSearchText] = useState<string>('');
  const [pdfUrl, setPdfUrl] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(true);
  const [loadingProgress, setLoadingProgress] = useState<number>(0);
  const [loadingStage, setLoadingStage] = useState<string>('Initializing...');
  const [error, setError] = useState<string>('');
  const [snackbarOpen, setSnackbarOpen] = useState<boolean>(false);
  const [snackbarMessage, setSnackbarMessage] = useState<string>('');
  const [highlightedPage, setHighlightedPage] = useState<number | null>(null);
  const [searchMatches, setSearchMatches] = useState<Array<{ page: number; similarity: number }>>([]); 
  const [currentMatchIndex, setCurrentMatchIndex] = useState<number>(0);
  const [jumpToPageInput, setJumpToPageInput] = useState<string>('');
  const containerRef = useRef<HTMLDivElement>(null);
  const pageRefs = useRef<Map<number, HTMLDivElement>>(new Map());
  const collapseTimerRef = useRef<NodeJS.Timeout | null>(null);

  // Initialize PDF URL - fetch with auth token and create blob URL
  useEffect(() => {
    const fetchPdf = async () => {
      try {
        setLoadingStage('Fetching PDF...');
        setLoadingProgress(10);
        
        // Use authenticated API client to fetch PDF
        const response = await api.get(`/pdf/${scanId}`, {
          responseType: 'blob'
        });
        
        // Create blob URL for pdf.js
        const blob = new Blob([response.data], { type: 'application/pdf' });
        const blobUrl = URL.createObjectURL(blob);
        
        console.log('[PDF Viewer] PDF fetched, created blob URL:', blobUrl);
        setPdfUrl(blobUrl);
        setLoadingProgress(30);
      } catch (err: any) {
        console.error('[PDF Viewer] Failed to fetch PDF:', err);
        setError(`Failed to load PDF: ${err.response?.data?.detail || err.message || 'Unknown error'}`);
        setLoading(false);
      }
    };
    
    fetchPdf();
    
    // Cleanup blob URL on unmount
    return () => {
      if (pdfUrl && pdfUrl.startsWith('blob:')) {
        URL.revokeObjectURL(pdfUrl);
      }
    };
  }, [scanId]);

  // Handle initialPage navigation - navigationKey forces re-navigation to same page
  useEffect(() => {
    if (initialPage && initialPage > 0 && initialPage <= numPages && !loading) {
      console.log('[PDF Viewer] Navigating to page:', initialPage, 'key:', navigationKey);
      setCurrentPage(initialPage);
      setTimeout(() => {
        const pageRef = pageRefs.current.get(initialPage);
        if (pageRef && containerRef.current) {
          const container = containerRef.current;
          const pageTop = pageRef.offsetTop;
          console.log('[PDF Viewer] Scrolling to offsetTop:', pageTop);
          container.scrollTo({ top: pageTop - 10, behavior: 'smooth' });
        }
      }, 100);
    }
  }, [initialPage, navigationKey, numPages, loading]);

  // Memoize file and options to prevent unnecessary reloads
  const pdfFile = useMemo(() => {
    return pdfUrl ? { url: pdfUrl } : null;
  }, [pdfUrl]);

  const pdfOptions = useMemo(() => {
    return {
      // Use jsdelivr CDN for reliable CORS-enabled access to cmaps and fonts
      cMapUrl: `https://cdn.jsdelivr.net/npm/pdfjs-dist@${pdfjs.version}/cmaps/`,
      cMapPacked: true,
      standardFontDataUrl: `https://cdn.jsdelivr.net/npm/pdfjs-dist@${pdfjs.version}/standard_fonts/`,
    };
  }, []);

  const onDocumentLoadSuccess = ({ numPages: pages }: { numPages: number }) => {
    console.log('[PDF Viewer] Document loaded successfully, pages:', pages);
    setNumPages(pages);
    setLoadingStage(`Rendering ${pages} pages...`);
    setLoadingProgress(90);
    
    // Small delay to show final progress, then complete
    setTimeout(() => {
      setLoadingProgress(100);
      setLoading(false);
      
      // Auto-jump to snippet location ONLY if no page number provided (avoid expensive text search)
      if (pdfSnippet && !initialPage) {
        setTimeout(() => jumpToLocation(pdfSnippet), 500);
      }
    }, 100);
  };

  const onDocumentLoadError = (err: Error) => {
    console.error('[PDF Viewer] Load error:', err);
    setError(`Failed to load PDF: ${err.message || 'Unknown error'}`);
    setLoading(false);
  };

  const onDocumentLoadProgress = ({ loaded, total }: { loaded: number; total: number }) => {
    console.log('[PDF Viewer] Load progress:', loaded, '/', total);
    if (total > 0) {
      const progress = Math.min(Math.round((loaded / total) * 70) + 10, 80);
      setLoadingProgress(progress);
      setLoadingStage(`Loading PDF... ${Math.round((loaded / total) * 100)}%`);
    }
  };

  const jumpToLocation = useCallback(async (snippet: string) => {
    if (!snippet || numPages === 0) return;

    try {
      // Adaptive threshold based on snippet length
      const snippetLen = snippet.length;
      const threshold = snippetLen < 50 ? 90 : snippetLen < 150 ? 85 : 80;

      const matches: Array<{ page: number; similarity: number }> = [];

      // Search through all pages to find ALL matches
      for (let pageNum = 1; pageNum <= numPages; pageNum++) {
        const pageRef = pageRefs.current.get(pageNum);
        if (!pageRef) continue;

        const textLayer = pageRef.querySelector('.react-pdf__Page__textContent');
        if (!textLayer) continue;

        const pageText = textLayer.textContent || '';
        const similarity = fuzzyMatch(snippet, pageText);

        if (similarity >= threshold) {
          matches.push({ page: pageNum, similarity });
        }
      }

      if (matches.length > 0) {
        // Sort by similarity (best match first)
        matches.sort((a, b) => b.similarity - a.similarity);
        setSearchMatches(matches);
        setCurrentMatchIndex(0);
        
        const firstMatch = matches[0];
        setCurrentPage(firstMatch.page);
        setHighlightedPage(firstMatch.page);
        
        // Scroll to page
        setTimeout(() => {
          const pageElement = pageRefs.current.get(firstMatch.page);
          if (pageElement && containerRef.current) {
            const container = containerRef.current;
            const pageTop = pageElement.offsetTop;
            container.scrollTo({ top: pageTop - 10, behavior: 'smooth' });
          }
        }, 100);

        const matchMsg = matches.length === 1 
          ? `Found on page ${firstMatch.page} (${firstMatch.similarity.toFixed(0)}% match)`
          : `Found ${matches.length} matches - showing best match on page ${firstMatch.page} (${firstMatch.similarity.toFixed(0)}%)`;
        setSnackbarMessage(matchMsg);
        setSnackbarOpen(true);

        // Clear any previous auto-collapse timer
        if (collapseTimerRef.current) {
          clearTimeout(collapseTimerRef.current);
        }
        // Keep highlight visible (no auto-remove)
      } else {
        setSearchMatches([]);
        setSnackbarMessage(`No match found (threshold: ${threshold}%)`);
        setSnackbarOpen(true);
      }
    } catch (err) {
      console.error('Error jumping to location:', err);
      setSnackbarMessage('Error searching PDF');
      setSnackbarOpen(true);
    }
  }, [numPages]);

  // Handle snippet-based search when page is not available
  useEffect(() => {
    if (pdfSnippet && !initialPage && !loading && numPages > 0) {
      console.log('[PDF Viewer] Searching for snippet:', pdfSnippet.substring(0, 50));
      setTimeout(() => jumpToLocation(pdfSnippet), 500);
    }
  }, [pdfSnippet, initialPage, loading, numPages, jumpToLocation]);

  const handleZoomIn = useCallback(() => {
    console.log('[PDF Viewer] Zoom In clicked, current scale:', scale);
    setScale((prev) => {
      const newScale = Math.min(prev + 0.2, 3.0);
      console.log('[PDF Viewer] New scale:', newScale);
      return newScale;
    });
  }, [scale]);

  const handleZoomOut = useCallback(() => {
    console.log('[PDF Viewer] Zoom Out clicked, current scale:', scale);
    setScale((prev) => {
      const newScale = Math.max(prev - 0.2, 0.5);
      console.log('[PDF Viewer] New scale:', newScale);
      return newScale;
    });
  }, [scale]);

  const handleZoomFit = useCallback(() => {
    console.log('[PDF Viewer] Fit Width clicked, setting scale to 1.0');
    setScale(1.0);
  }, []);

  const handleSearch = useCallback(() => {
    console.log('[PDF Viewer] Search clicked, searchText:', searchText);
    if (searchText.trim()) {
      jumpToLocation(searchText.trim());
    }
  }, [searchText, jumpToLocation]);

  const handlePreviousMatch = useCallback(() => {
    if (searchMatches.length === 0) return;
    const newIndex = currentMatchIndex > 0 ? currentMatchIndex - 1 : searchMatches.length - 1;
    setCurrentMatchIndex(newIndex);
    const match = searchMatches[newIndex];
    setCurrentPage(match.page);
    setHighlightedPage(match.page);
    
    setTimeout(() => {
      const pageElement = pageRefs.current.get(match.page);
      if (pageElement && containerRef.current) {
        const container = containerRef.current;
        const pageTop = pageElement.offsetTop;
        container.scrollTo({ top: pageTop - 10, behavior: 'smooth' });
      }
    }, 50);
    
    setSnackbarMessage(`Match ${newIndex + 1} of ${searchMatches.length} (page ${match.page}, ${match.similarity.toFixed(0)}% match)`);
    setSnackbarOpen(true);
  }, [searchMatches, currentMatchIndex]);

  const handleNextMatch = useCallback(() => {
    if (searchMatches.length === 0) return;
    const newIndex = currentMatchIndex < searchMatches.length - 1 ? currentMatchIndex + 1 : 0;
    setCurrentMatchIndex(newIndex);
    const match = searchMatches[newIndex];
    setCurrentPage(match.page);
    setHighlightedPage(match.page);
    
    setTimeout(() => {
      const pageElement = pageRefs.current.get(match.page);
      if (pageElement && containerRef.current) {
        const container = containerRef.current;
        const pageTop = pageElement.offsetTop;
        container.scrollTo({ top: pageTop - 10, behavior: 'smooth' });
      }
    }, 50);
    
    setSnackbarMessage(`Match ${newIndex + 1} of ${searchMatches.length} (page ${match.page}, ${match.similarity.toFixed(0)}% match)`);
    setSnackbarOpen(true);
  }, [searchMatches, currentMatchIndex]);

  const handlePreviousPage = useCallback(() => {
    console.log('[PDF Viewer] Previous Page clicked, current page:', currentPage);
    if (currentPage > 1) {
      const targetPage = currentPage - 1;
      console.log('[PDF Viewer] Navigating to page:', targetPage);
      setCurrentPage(targetPage);
      setTimeout(() => {
        const pageElement = pageRefs.current.get(targetPage);
        if (pageElement && containerRef.current) {
          const container = containerRef.current;
          const pageTop = pageElement.offsetTop;
          console.log('[PDF Viewer] Scrolling to offsetTop:', pageTop);
          container.scrollTo({ top: pageTop - 10, behavior: 'smooth' });
        } else {
          console.log('[PDF Viewer] Could not find page element or container');
        }
      }, 50);
    }
  }, [currentPage]);

  const handleNextPage = useCallback(() => {
    console.log('[PDF Viewer] Next Page clicked, current page:', currentPage, 'numPages:', numPages);
    if (currentPage < numPages) {
      const targetPage = currentPage + 1;
      console.log('[PDF Viewer] Navigating to page:', targetPage);
      setCurrentPage(targetPage);
      setTimeout(() => {
        const pageElement = pageRefs.current.get(targetPage);
        if (pageElement && containerRef.current) {
          const container = containerRef.current;
          const pageTop = pageElement.offsetTop;
          console.log('[PDF Viewer] Scrolling to offsetTop:', pageTop);
          container.scrollTo({ top: pageTop - 10, behavior: 'smooth' });
        } else {
          console.log('[PDF Viewer] Could not find page element or container');
        }
      }, 50);
    }
  }, [currentPage, numPages]);

  const handleJumpToPage = useCallback(() => {
    const pageNum = parseInt(jumpToPageInput, 10);
    if (isNaN(pageNum) || pageNum < 1 || pageNum > numPages) {
      setSnackbarMessage(`Please enter a valid page number (1-${numPages})`);
      setSnackbarOpen(true);
      return;
    }
    
    console.log('[PDF Viewer] Jumping to page:', pageNum);
    setCurrentPage(pageNum);
    setJumpToPageInput('');
    
    setTimeout(() => {
      const pageElement = pageRefs.current.get(pageNum);
      if (pageElement && containerRef.current) {
        const container = containerRef.current;
        const pageTop = pageElement.offsetTop;
        console.log('[PDF Viewer] Scrolling to offsetTop:', pageTop);
        container.scrollTo({ top: pageTop - 10, behavior: 'smooth' });
      }
    }, 50);
  }, [jumpToPageInput, numPages]);

  // Track scroll position to update current page
  useEffect(() => {
    const container = containerRef.current;
    if (!container || numPages === 0) return;

    const handleScroll = () => {
      // Find the page that's most visible in the viewport
      const containerRect = container.getBoundingClientRect();
      const containerCenter = containerRect.top + containerRect.height / 2;

      let closestPage = 1;
      let closestDistance = Infinity;

      pageRefs.current.forEach((pageElement, pageNumber) => {
        const pageRect = pageElement.getBoundingClientRect();
        const pageCenter = pageRect.top + pageRect.height / 2;
        const distance = Math.abs(pageCenter - containerCenter);

        if (distance < closestDistance) {
          closestDistance = distance;
          closestPage = pageNumber;
        }
      });

      setCurrentPage(closestPage);
    };

    container.addEventListener('scroll', handleScroll, { passive: true });
    return () => {
      container.removeEventListener('scroll', handleScroll);
    };
  }, [numPages]);

  // Cleanup timer on unmount
  useEffect(() => {
    return () => {
      if (collapseTimerRef.current) {
        clearTimeout(collapseTimerRef.current);
      }
    };
  }, []);

  // Determine windowed rendering - only for very large documents
  const shouldUseWindowedRendering = numPages >= 200;
  const visiblePageRange = shouldUseWindowedRendering
    ? [Math.max(1, currentPage - 5), Math.min(numPages, currentPage + 5)]
    : [1, numPages];

  // Debug logging
  console.log('[PDF Viewer] Render state:', { loading, numPages, currentPage, scale });

  return (
    <Box
      sx={{
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        bgcolor: 'grey.100',
        overflow: 'hidden'
      }}
    >
      {/* Toolbar */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 1,
          p: 1,
          bgcolor: 'background.paper',
          borderBottom: '1px solid',
          borderColor: 'divider',
          flexShrink: 0,
          zIndex: 10,
          position: 'relative',
          pointerEvents: 'auto'
        }}
      >
        <Stack direction="row" spacing={0.5}>
          <Tooltip title="Zoom Out">
            <span>
              <IconButton size="small" onClick={handleZoomOut} disabled={scale <= 0.5}>
                <ZoomOut />
              </IconButton>
            </span>
          </Tooltip>
          <Tooltip title="Fit Width">
            <IconButton size="small" onClick={handleZoomFit}>
              <ZoomOutMap />
            </IconButton>
          </Tooltip>
          <Tooltip title="Zoom In">
            <span>
              <IconButton size="small" onClick={handleZoomIn} disabled={scale >= 3.0}>
                <ZoomIn />
              </IconButton>
            </span>
          </Tooltip>
        </Stack>

        <Typography variant="body2" sx={{ mx: 1 }}>
          {scale.toFixed(1)}x
        </Typography>

        <Stack direction="row" spacing={0.5} alignItems="center">
          <Tooltip title="Previous Page">
            <span>
              <IconButton size="small" onClick={handlePreviousPage} disabled={currentPage <= 1}>
                <NavigateBefore />
              </IconButton>
            </span>
          </Tooltip>
          <Typography variant="body2" sx={{ mx: 1 }}>
            Page {currentPage} / {numPages}
          </Typography>
          <Tooltip title="Next Page">
            <span>
              <IconButton size="small" onClick={handleNextPage} disabled={currentPage >= numPages}>
                <NavigateNext />
              </IconButton>
            </span>
          </Tooltip>
          <Tooltip title="Jump to page">
            <TextField
              size="small"
              placeholder="Go to..."
              value={jumpToPageInput}
              onChange={(e) => setJumpToPageInput(e.target.value)}
              onKeyPress={(e) => e.key === 'Enter' && handleJumpToPage()}
              sx={{ 
                width: 70,
                ml: 1,
                '& input': { 
                  textAlign: 'center',
                  fontSize: '0.875rem'
                }
              }}
            />
          </Tooltip>
        </Stack>

        <TextField
          size="small"
          placeholder="Search in PDF..."
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
          sx={{ flex: 1, maxWidth: 300, ml: 'auto' }}
          InputProps={{
            endAdornment: (
              <IconButton size="small" onClick={handleSearch}>
                <SearchIcon />
              </IconButton>
            )
          }}
        />

        {/* Search Match Navigation - only show when there are multiple matches */}
        {searchMatches.length > 1 && (
          <Stack direction="row" spacing={0.5} sx={{ ml: 1 }}>
            <Tooltip title="Previous Match">
              <IconButton size="small" onClick={handlePreviousMatch}>
                <NavigateBefore />
              </IconButton>
            </Tooltip>
            <Typography variant="body2" sx={{ mx: 0.5, alignSelf: 'center', fontSize: '0.75rem' }}>
              {currentMatchIndex + 1}/{searchMatches.length}
            </Typography>
            <Tooltip title="Next Match">
              <IconButton size="small" onClick={handleNextMatch}>
                <NavigateNext />
              </IconButton>
            </Tooltip>
          </Stack>
        )}

        {/* Split View Controls */}
        {onToggleOrientation && (
          <Tooltip title={orientation === 'horizontal' ? 'Switch to Vertical Split' : 'Switch to Horizontal Split'}>
            <IconButton size="small" onClick={onToggleOrientation} sx={{ ml: 1 }}>
              {orientation === 'horizontal' ? <SwapVert /> : <SwapHoriz />}
            </IconButton>
          </Tooltip>
        )}
        
        {onClose && (
          <Tooltip title="Close Split View">
            <IconButton size="small" onClick={onClose} color="error">
              <Close />
            </IconButton>
          </Tooltip>
        )}
      </Box>

      {/* PDF Viewer */}
      <Box
        ref={containerRef}
        sx={{
          flex: 1,
          overflow: 'auto',
          py: 2,
          px: 0,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'flex-start',
          gap: 2,
          width: '100%'
        }}
      >
        {error && (
          <Alert 
            severity="error"
            sx={{ m: 2, maxWidth: 600 }}
            action={
              <Button 
                color="inherit" 
                size="small"
                onClick={() => window.open(`/api/pdf/${scanId}`, '_blank')}
              >
                Download PDF
              </Button>
            }
          >
            {error}
          </Alert>
        )}

        {!error && pdfFile && (
          <>
            {loading && (
              <Box 
                sx={{ 
                  display: 'flex', 
                  flexDirection: 'column',
                  justifyContent: 'center', 
                  alignItems: 'center', 
                  minHeight: '400px',
                  gap: 2,
                  minWidth: 300,
                  p: 4
                }}
              >
                <CircularProgress size={60} />
                <Typography variant="body1" color="text.secondary">
                  {loadingStage}
                </Typography>
                <Box sx={{ width: '100%', maxWidth: 400 }}>
                  <LinearProgress 
                    variant="determinate" 
                    value={loadingProgress} 
                    sx={{ height: 8, borderRadius: 4 }}
                  />
                  <Typography 
                    variant="caption" 
                    color="text.secondary" 
                    sx={{ display: 'block', textAlign: 'center', mt: 1 }}
                  >
                    {loadingProgress}%
                  </Typography>
                </Box>
              </Box>
            )}
            
            <Document
              file={pdfFile}
              onLoadSuccess={onDocumentLoadSuccess}
              onLoadError={(error) => {
                console.error('[PDF Viewer] PDF load error:', error);
                setError(`Failed to load PDF: ${error.message || 'Unknown error'}. You can download the PDF using the button below.`);
                setLoading(false);
              }}
              onLoadProgress={onDocumentLoadProgress}
              options={pdfOptions}
            >
              {!loading && numPages > 0 && Array.from({ length: numPages }, (_, i) => i + 1)
                .filter((pageNum) => pageNum >= visiblePageRange[0] && pageNum <= visiblePageRange[1])
                .map((pageNum) => (
                  <Box
                    key={`page-${pageNum}-${scale}`}
                    ref={(el) => {
                      if (el) pageRefs.current.set(pageNum, el as HTMLDivElement);
                    }}
                    sx={{
                      mb: 2,
                      boxShadow: highlightedPage === pageNum ? '0 0 0 3px #ffd54f' : 2,
                      bgcolor: 'white',
                      transition: 'box-shadow 0.3s ease'
                    }}
                  >
                    <Page
                      key={`page-render-${pageNum}-${scale}`}
                      pageNumber={pageNum}
                      scale={scale}
                      renderTextLayer={true}
                      renderAnnotationLayer={true}
                    />
                    <Typography
                      variant="caption"
                      sx={{
                        display: 'block',
                        textAlign: 'center',
                        mt: 0.5,
                        color: 'text.secondary'
                      }}
                    >
                      Page {pageNum}
                    </Typography>
                  </Box>
                ))}
            </Document>
          </>
        )}
      </Box>

      {/* Snackbar for search feedback */}
      <Snackbar
        open={snackbarOpen}
        autoHideDuration={3000}
        onClose={() => setSnackbarOpen(false)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert onClose={() => setSnackbarOpen(false)} severity="info" sx={{ width: '100%' }}>
          {snackbarMessage}
        </Alert>
      </Snackbar>
    </Box>
  );
};
