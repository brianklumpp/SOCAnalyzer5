import React, { useState } from 'react';
import { Box, IconButton, Tooltip, Fab, useMediaQuery, useTheme } from '@mui/material';
import { PictureInPictureAlt, Close, SwapHoriz, SwapVert } from '@mui/icons-material';
import { Panel, PanelGroup, PanelResizeHandle } from 'react-resizable-panels';
import { PdfViewerPanel } from './PdfViewerPanel';
import { APP_CONFIG } from '../../config';
import { useSplitView } from '../../contexts/SplitViewContext';

interface SplitViewLayoutProps {
  scanId: number;
  tabName: 'controls' | 'cuecs' | 'subservice_orgs' | 'objectives';
  children: React.ReactNode;
  onPdfNavigate?: (handler: (snippet: string | null, page?: number | null) => void) => void;
}

export const SplitViewLayout: React.FC<SplitViewLayoutProps> = ({
  scanId,
  tabName,
  children,
  onPdfNavigate
}) => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
  const { getSplitViewState, toggleSplitView, toggleOrientation } = useSplitView();
  
  // Get state from context
  const { enabled: splitViewEnabled, orientation } = getSplitViewState(scanId, tabName);
  
  const [currentSnippet, setCurrentSnippet] = useState<string | null>(null);
  const [targetPage, setTargetPage] = useState<number | null>(null);
  const [navigationKey, setNavigationKey] = useState<number>(0);

  const handleToggleSplitView = () => {
    toggleSplitView(scanId, tabName);
    if (!splitViewEnabled) {
      setCurrentSnippet(null); // Reset snippet when enabling
      setTargetPage(null);
    }
  };

  // Provide navigation function to parent
  const handlePdfNavigate = React.useCallback((snippet: string | null, page?: number | null) => {
    console.log('[SplitViewLayout] handlePdfNavigate called:', { 
      splitViewEnabled, 
      snippet: snippet?.substring(0, 50), 
      page 
    });
    if (splitViewEnabled) {
      setCurrentSnippet(snippet);
      setTargetPage(page ?? null);
      setNavigationKey(prev => prev + 1); // Increment key to force navigation
    }
  }, [splitViewEnabled]);

  // Expose navigation handler to parent via prop
  React.useEffect(() => {
    if (onPdfNavigate) {
      onPdfNavigate(handlePdfNavigate);
    }
  }, [onPdfNavigate, handlePdfNavigate]);

  const handleToggleOrientation = () => {
    toggleOrientation(scanId, tabName);
  };

  // Note: Row click handling for PDF navigation will be added when table components
  // are enhanced to pass pdf_snippet data on row click events

  // Mobile FAB fallback
  if (isMobile) {
    return (
      <Box sx={{ position: 'relative', height: '100%' }}>
        {children}
        <Fab
          color="primary"
          size="small"
          sx={{ position: 'fixed', bottom: 16, right: 16, zIndex: 1000 }}
          onClick={() => window.open(APP_CONFIG.apiUrl(`/pdf/${scanId}`), '_blank')}
        >
          <PictureInPictureAlt />
        </Fab>
      </Box>
    );
  }

  // Desktop split view
  if (!splitViewEnabled) {
    return (
      <Box sx={{ 
        position: 'relative', 
        height: '100%', 
        width: '100%', 
        overflow: 'auto' 
      }}>
        {children}
        
        <Tooltip title="Enable Split View PDF Viewer">
          <IconButton
            color="primary"
            sx={{
              position: 'absolute',
              top: 8,
              right: 8,
              bgcolor: 'background.paper',
              boxShadow: 3,
              zIndex: 1000,
              '&:hover': { bgcolor: 'primary.light', color: 'white' }
            }}
            onClick={handleToggleSplitView}
          >
            <PictureInPictureAlt />
          </IconButton>
        </Tooltip>
      </Box>
    );
  }

  return (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden', position: 'relative' }}>
      {/* Split View Panels */}
      <Box sx={{ height: '100%', overflow: 'hidden', position: 'relative' }}>
        <PanelGroup direction={orientation === 'horizontal' ? 'horizontal' : 'vertical'}>
          {/* Table Panel */}
          <Panel defaultSize={50} minSize={30} maxSize={80} style={{ overflow: 'hidden', position: 'relative', minWidth: 0 }}>
            <Box 
              sx={{ 
                height: '100%', 
                width: '100%',
                minWidth: 0,
                overflow: 'auto', 
                bgcolor: 'background.default', 
                p: 2,
                position: 'relative',
                zIndex: 1,
                pointerEvents: 'auto'
              }}
            >
              {children}
            </Box>
          </Panel>

          {/* Resize Handle */}
          <PanelResizeHandle>
            <Box
              sx={{
                width: orientation === 'horizontal' ? '4px' : '100%',
                height: orientation === 'horizontal' ? '100%' : '4px',
                bgcolor: 'divider',
                cursor: orientation === 'horizontal' ? 'col-resize' : 'row-resize',
                '&:hover': { bgcolor: 'primary.main' },
                transition: 'background-color 0.2s',
                zIndex: 2
              }}
            />
          </PanelResizeHandle>

          {/* PDF Panel */}
          <Panel defaultSize={50} minSize={20} maxSize={70} style={{ overflow: 'hidden', position: 'relative' }}>
            <Box sx={{ height: '100%', width: '100%', overflow: 'hidden', display: 'flex', flexDirection: 'column', position: 'relative', zIndex: 0 }}>
              <PdfViewerPanel
                scanId={scanId}
                pdfSnippet={currentSnippet}
                initialPage={targetPage}
                navigationKey={navigationKey}
                onClose={handleToggleSplitView}
                orientation={orientation}
                onToggleOrientation={handleToggleOrientation}
              />
            </Box>
          </Panel>
        </PanelGroup>
      </Box>
    </Box>
  );
};
