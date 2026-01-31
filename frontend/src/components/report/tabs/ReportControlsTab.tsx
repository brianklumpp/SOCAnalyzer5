/**
 * ReportControlsTab Component
 * 
 * Displays high and low confidence controls with add button.
 */

import React, { useRef } from 'react';
import { Box, Typography, Button, Collapse, Chip, Tooltip } from '@mui/material';
import { ExpandMore as ExpandMoreIcon, ExpandLess as ExpandLessIcon, Refresh as RefreshIcon } from '@mui/icons-material';
import { ControlsTable } from '../tables/ControlsTable';
import { CONFIDENCE_THRESHOLD_PERCENT } from '../../../config/report/constants';
import { SplitViewLayout } from '../SplitViewLayout';

interface ReportControlsTabProps {
  scanId: string | undefined;
  filteredHighConfControls: any[];
  filteredLowConfControls: any[];
  ignored: { controls: Set<number>; cuecs: Set<number>; suborgs: Set<number> };
  showLowConfidence: boolean;
  onToggleLowConfidence: () => void;
  onEdit: (row: any, idx: number) => void;
  onBatchEdit: (changes: { [rowIdx: number]: any }, sectionRows: any[]) => void;
  onRecompute: (row: any) => Promise<void>;
  onRecomputeAllHighConfidence?: () => Promise<void>;
  onToggleDeviation?: (row: any, hasDeviation: boolean) => Promise<void>;
  onIgnore: (row: any) => void;
  onConfirm: (row: any) => void;
  onRefresh?: () => void;
  onOpenConfidenceModal: (control: any) => void;
  onOpenControlModal?: (control: any) => void;
  onAddControl: () => void;
  darkMode: boolean;
  tocPageOffset?: number;
  frameworkCriteria?: any;
  onOpenMappingDetails?: (control: any, frameworkType: string) => void;
  objectives?: any[];
  objectivesLoading?: boolean;
  objectiveMappings?: Map<string | number, any>;
  onOpenObjectivesModal?: () => void;
  isAdmin?: boolean;
  onObjectivesRefresh?: () => void;
  showToast?: (message: string, severity?: 'success' | 'error' | 'info' | 'warning') => void;
}

export const ReportControlsTab = React.memo(function ReportControlsTab({
  scanId,
  filteredHighConfControls,
  filteredLowConfControls,
  ignored,
  showLowConfidence,
  onToggleLowConfidence,
  onEdit,
  onBatchEdit,
  onRecompute,
  onRecomputeAllHighConfidence,
  onToggleDeviation,
  onIgnore,
  onConfirm,
  onRefresh,
  onOpenConfidenceModal,
  onOpenControlModal,
  onAddControl,
  darkMode,
  tocPageOffset,
  frameworkCriteria,
  onOpenMappingDetails,
  objectives,
  objectivesLoading,
  objectiveMappings,
  onOpenObjectivesModal,
  isAdmin,
  onObjectivesRefresh,
  showToast
}: ReportControlsTabProps) {
  const lowConfSectionRef = useRef<HTMLDivElement>(null);
  const [pdfNavigateHandler, setPdfNavigateHandler] = React.useState<((snippet: string | null, page?: number | null) => void) | null>(null);

  const handleRowClick = React.useCallback((row: any) => {
    if (!pdfNavigateHandler) return;
    
    // Check if page refs exist - if not, skip navigation to avoid expensive search
    const pageRefs = row.control_page_refs;
    const hasPageRef = (Array.isArray(pageRefs) && pageRefs.length > 0) || row.control_page_ref;
    
    if (!hasPageRef) {
      console.log('[Controls Tab] Row clicked but no page refs available, skipping navigation');
      return;
    }
    
    // Try to get snippet from pdf_snippet field first, then fallback to control text
    const snippet = row.pdf_snippet || row.control_desc || row.control_text || null;
    let targetPage: number | null = null;
    
    if (Array.isArray(pageRefs) && pageRefs.length > 0) {
      // control_page_refs contains document page numbers (from === PAGE X === markers)
      // Add TOC offset to convert document page to PDF page
      // Default to 2 for existing scans that don't have toc_page_offset stored
      const offset = tocPageOffset ?? 2;
      targetPage = pageRefs[0] + offset;
    } else if (row.control_page_ref) {
      // Fallback to singular control_page_ref if refs array doesn't exist
      const offset = tocPageOffset ?? 2;
      targetPage = row.control_page_ref + offset;
    }
    
    console.log('[Controls Tab] Row clicked, navigating to:', { 
      snippet: snippet?.substring(0, 50), 
      hasPdfSnippet: !!row.pdf_snippet,
      documentPage: pageRefs?.[0] || row.control_page_ref,
      pdfPage: targetPage 
    });
    
    // Navigate with snippet and page number
    pdfNavigateHandler(snippet, targetPage);
  }, [pdfNavigateHandler, tocPageOffset]);

  const handleToggleLowConfidence = () => {
    onToggleLowConfidence();
    if (!showLowConfidence && lowConfSectionRef.current) {
      setTimeout(() => {
        lowConfSectionRef.current?.scrollIntoView({ 
          behavior: 'smooth', 
          block: 'start' 
        });
      }, 100);
    }
  };

  const content = (
    <>
      <Typography variant="h5" gutterBottom sx={{ fontSize: 18, mb: 2 }}>
        Controls
      </Typography>

      {/* High Confidence Controls */}
      <Box className={`sticky-table-container ${darkMode ? 'dark-mode' : 'light-mode'}`}>
        <ControlsTable
          scanId={scanId ? parseInt(scanId) : 0}
          controls={filteredHighConfControls}
          ignored={ignored.controls}
          onEdit={onEdit}
          onBatchEdit={onBatchEdit}
          onRecompute={onRecompute}
          onToggleDeviation={onToggleDeviation}
          onIgnore={onIgnore}
          onConfirm={onConfirm}
          onRowClick={handleRowClick}
          onRefresh={onRefresh}
          onOpenConfidenceModal={onOpenConfidenceModal}
          onOpenControlModal={onOpenControlModal}
          frameworkCriteria={frameworkCriteria}
          onOpenMappingDetails={onOpenMappingDetails}
          objectives={objectives}
          objectivesLoading={objectivesLoading}
          objectiveMappings={objectiveMappings}
          onObjectivesRefresh={onObjectivesRefresh}
          showToast={showToast}
          additionalButtons={
            <>
              <Button variant="outlined" size="small" onClick={onAddControl}>
                Add Control
              </Button>
              {onRecomputeAllHighConfidence && (
                <Tooltip title="Recompute framework mappings for all high confidence controls">
                  <Button 
                    variant="outlined" 
                    size="small" 
                    onClick={onRecomputeAllHighConfidence}
                    startIcon={<RefreshIcon />}
                    sx={{ ml: 1 }}
                  >
                    Recompute All
                  </Button>
                </Tooltip>
              )}
              {isAdmin && onOpenObjectivesModal && (
                <Button
                  type="button"
                  variant="outlined"
                  size="small"
                  onClick={onOpenObjectivesModal}
                  sx={{ ml: 1 }}
                >
                  Manage Objectives
                </Button>
              )}
              {filteredLowConfControls.length > 0 && !showLowConfidence && (
                <Chip 
                  label={`${filteredLowConfControls.length} Low Confidence`}
                  size="small"
                  color="warning"
                  variant="outlined"
                  onClick={handleToggleLowConfidence}
                  sx={{ ml: 1, cursor: 'pointer' }}
                />
              )}
            </>
          }
        />
      </Box>

      {/* Low Confidence Section (Collapsible) */}
      {filteredLowConfControls.length > 0 && (
        <Box ref={lowConfSectionRef} sx={{ p: 1, ml: 3, scrollMarginTop: '20px' }}>
          <Button size="small" onClick={handleToggleLowConfidence}>
            {showLowConfidence ? <ExpandLessIcon /> : <ExpandMoreIcon />}
            {' '}
            Show Low Confidence ({filteredLowConfControls.length})
          </Button>
        </Box>
      )}
      
      {showLowConfidence && filteredLowConfControls.length > 0 && (
        <Collapse in={showLowConfidence}>
          <Box className={`sticky-table-container low-confidence-section ${darkMode ? 'dark-mode' : 'light-mode'}`}>
            <ControlsTable
              scanId={scanId ? parseInt(scanId) : 0}
              controls={filteredLowConfControls}
              ignored={ignored.controls}
              onEdit={onEdit}
              onBatchEdit={onBatchEdit}
              onRecompute={onRecompute}
              onToggleDeviation={onToggleDeviation}
              onIgnore={onIgnore}
              onConfirm={onConfirm}
              onRefresh={onRefresh}
              onOpenConfidenceModal={onOpenConfidenceModal}
              onOpenControlModal={onOpenControlModal}
              onRowClick={handleRowClick}
              objectives={objectives}
              objectivesLoading={objectivesLoading}
              objectiveMappings={objectiveMappings}
              showToast={showToast}
            />
          </Box>
        </Collapse>
      )}

      <Typography sx={{ fontStyle: "italic", fontSize: 11 }}>
        Controls are grouped by status and TSC section. High confidence (≥ {CONFIDENCE_THRESHOLD_PERCENT}%) shown by default.
        Low confidence items (including ignored items with 0% confidence) available in "Show Low Confidence" section.
      </Typography>
    </>
  );
  
  return (
    <SplitViewLayout
      scanId={scanId ? parseInt(scanId) : 0}
      tabName="controls"
      onPdfNavigate={(handler) => setPdfNavigateHandler(() => handler)}
    >
      {content}
    </SplitViewLayout>
  );
});
