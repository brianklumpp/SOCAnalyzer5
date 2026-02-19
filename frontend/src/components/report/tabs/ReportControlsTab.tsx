/**
 * ReportControlsTab Component
 * 
 * Displays high and low confidence controls with add button.
 */

import React, { useRef, useState, useMemo, useCallback } from 'react';
import { Box, Typography, Button, Collapse, Chip, Tooltip } from '@mui/material';
import { ExpandMore as ExpandMoreIcon, ExpandLess as ExpandLessIcon, Refresh as RefreshIcon, AccountTree as AccountTreeIcon } from '@mui/icons-material';
import { ControlsTable } from '../tables/ControlsTable';
import { CONFIDENCE_THRESHOLD_PERCENT } from '../../../config/report/constants';
import { SplitViewLayout } from '../SplitViewLayout';
import { ControlEditPanel } from '../ControlEditPanel';

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
  onMapAllFrameworks?: () => Promise<void>;
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
  onConvertToObjective?: (control: any) => void;
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
  onMapAllFrameworks,
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
  showToast,
  onConvertToObjective
}: ReportControlsTabProps) {
  const lowConfSectionRef = useRef<HTMLDivElement>(null);
  const [pdfNavigateHandler, setPdfNavigateHandler] = React.useState<((snippet: string | null, page?: number | null) => void) | null>(null);
  const [editPanelControl, setEditPanelControl] = useState<any>(null);

  // Combined controls list for edit panel navigation (high conf + low conf when visible)
  const allNavigableControls = useMemo(() => {
    const combined = [...filteredHighConfControls];
    if (showLowConfidence) {
      combined.push(...filteredLowConfControls);
    }
    return combined;
  }, [filteredHighConfControls, filteredLowConfControls, showLowConfidence]);

  const handleOpenEditPanel = useCallback((control: any) => {
    setEditPanelControl(control);
  }, []);

  const handleEditPanelNavigate = useCallback((control: any) => {
    setEditPanelControl(control);
  }, []);

  const handleEditPanelClose = useCallback(() => {
    setEditPanelControl(null);
  }, []);

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
      // control_page_refs already stores physical PDF page numbers (from === PAGE N === markers)
      const offset = tocPageOffset ?? 0;
      targetPage = pageRefs[0] + offset;
    } else if (row.control_page_ref) {
      // Fallback to singular control_page_ref if refs array doesn't exist
      const offset = tocPageOffset ?? 0;
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

      {/* Control Edit Panel (overlay) */}
      {editPanelControl && (
        <ControlEditPanel
          control={editPanelControl}
          controls={allNavigableControls}
          scanId={scanId ? parseInt(scanId) : 0}
          onClose={handleEditPanelClose}
          onSave={onEdit}
          onIgnore={onIgnore}
          onConfirm={onConfirm}
          onRecompute={onRecompute}
          onToggleDeviation={onToggleDeviation}
          onNavigate={handleEditPanelNavigate}
          onConvertToObjective={onConvertToObjective}
          pdfNavigateHandler={pdfNavigateHandler}
          tocPageOffset={tocPageOffset}
          frameworkCriteria={frameworkCriteria}
          onOpenMappingDetails={onOpenMappingDetails}
          onObjectivesRefresh={onObjectivesRefresh}
          onRefresh={onRefresh}
          showToast={showToast}
        />
      )}

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
          onOpenEditPanel={handleOpenEditPanel}
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
              {onMapAllFrameworks && (
                <Tooltip title="Map controls to all available frameworks (NIST, ISO 27001, etc.) — only TSC and COSO are mapped during scan">
                  <Button 
                    variant="outlined" 
                    size="small" 
                    onClick={onMapAllFrameworks}
                    startIcon={<AccountTreeIcon />}
                    sx={{ ml: 1 }}
                  >
                    Map All Frameworks
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
              onOpenEditPanel={handleOpenEditPanel}
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
