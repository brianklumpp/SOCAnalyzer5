/**
 * ReportSuborgsTab Component
 * 
 * Displays high and low confidence subservice organizations with duplicate warning.
 */

import React, { useRef } from 'react';
import { Box, Typography, Button, Collapse, Chip, Tooltip } from '@mui/material';
import { Warning as WarningIcon, ExpandMore as ExpandMoreIcon, ExpandLess as ExpandLessIcon, PlaylistAdd as ExtractIcon } from '@mui/icons-material';
import { SuborgsTable } from '../tables/SuborgsTable';
import { CONFIDENCE_THRESHOLD_PERCENT } from '../../../config/report/constants';
import { SplitViewLayout } from '../SplitViewLayout';
import { ManualExtractionDialog } from '../ManualExtractionDialog';

interface ReportSuborgsTabProps {
  scanId: string | undefined;
  filteredHighConfSubOrgs: any[];
  filteredLowConfSubOrgs: any[];
  ignored: { controls: Set<number>; cuecs: Set<number>; suborgs: Set<number> };
  recentlyChangedIds: Set<number>;
  hasAnyDuplicateSoNames: boolean;
  showLowConfidence: boolean;
  onToggleLowConfidence: () => void;
  onEdit: (row: any, idx: number) => void;
  onBatchEdit: (changes: { [rowIdx: number]: any }, rows: any[]) => void;
  onIgnore: (row: any) => void;
  onConfirm: (row: any) => void;
  onAddSuborg: () => void;
  darkMode: boolean;
  theme: any;
  tocPageOffset?: number;
  refreshReport?: () => Promise<void>;
}

export const ReportSuborgsTab = React.memo(function ReportSuborgsTab({
  scanId,
  filteredHighConfSubOrgs,
  filteredLowConfSubOrgs,
  ignored,
  recentlyChangedIds,
  hasAnyDuplicateSoNames,
  showLowConfidence,
  onToggleLowConfidence,
  onEdit,
  onBatchEdit,
  onIgnore,
  onConfirm,
  onAddSuborg,
  darkMode,
  theme,
  tocPageOffset,
  refreshReport
}: ReportSuborgsTabProps) {
  const lowConfSectionRef = useRef<HTMLDivElement>(null);
  const [pdfNavigateHandler, setPdfNavigateHandler] = React.useState<((snippet: string | null, page?: number | null) => void) | null>(null);
  const [manualExtractOpen, setManualExtractOpen] = React.useState(false);

  const handleRowClick = React.useCallback((row: any) => {
    if (!pdfNavigateHandler) return;
    
    // Try to get snippet from pdf_snippet field first, then fallback to description/name
    const snippet = row.pdf_snippet || row.third_party_description || row.name || null;
    const pageRef = row.third_party_page_ref;
    let targetPage: number | null = null;
    
    if (pageRef) {
      // third_party_page_ref is a single page number
      const offset = tocPageOffset ?? 2;
      targetPage = pageRef + offset;
    }
    
    console.log('[Suborgs Tab] Row clicked, navigating to:', { 
      snippet: snippet?.substring(0, 50),
      hasPdfSnippet: !!row.pdf_snippet,
      documentPage: pageRef,
      pdfPage: targetPage 
    });
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
        Subservice Organizations
      </Typography>

      {/* Duplicate Names Warning */}
      {hasAnyDuplicateSoNames && (
        <Box sx={{ 
          mb: 1, 
          p: 1, 
          backgroundColor: theme.palette.mode === 'dark' ? '#665500' : '#fff3cd', 
          border: '1px solid #ffc107', 
          borderRadius: 1 
        }}>
          <Typography sx={{ 
            fontSize: 12, 
            color: theme.palette.mode === 'dark' ? '#ffeb3b' : '#856404', 
            display: 'flex', 
            alignItems: 'center' 
          }}>
            <WarningIcon sx={{ fontSize: 16, mr: 0.5 }} />
            Duplicate subservice organization names exist in this scan. Duplicates are allowed. 
            Edits target rows by ID, so duplicate names are safe. If helpful, add a qualifier 
            (e.g., region or environment) to disambiguate.
          </Typography>
        </Box>
      )}

      {/* High Confidence Suborgs */}
      <Box className={`sticky-table-container ${darkMode ? 'dark-mode' : 'light-mode'}`}>
        <SuborgsTable
          subOrgs={filteredHighConfSubOrgs}
          ignored={ignored.suborgs}
          recentlyChangedIds={recentlyChangedIds}
          onEdit={onEdit}
          onBatchEdit={onBatchEdit}
          onIgnore={onIgnore}
          onConfirm={onConfirm}
          onRowClick={handleRowClick}
          additionalButtons={
            <>
              <Button variant="outlined" size="small" onClick={onAddSuborg}>
                Add Subservice Org
              </Button>
              <Tooltip title="Extract Subservice Organizations from specific PDF pages">
                <Button 
                  variant="outlined" 
                  size="small" 
                  onClick={() => setManualExtractOpen(true)}
                  startIcon={<ExtractIcon />}
                  sx={{ ml: 1 }}
                >
                  Manual Extract
                </Button>
              </Tooltip>
              {filteredLowConfSubOrgs.length > 0 && !showLowConfidence && (
                <Chip 
                  label={`${filteredLowConfSubOrgs.length} Low Confidence`}
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
      {filteredLowConfSubOrgs.length > 0 && (
        <Box ref={lowConfSectionRef} sx={{ p: 1, ml: 3, scrollMarginTop: '20px' }}>
          <Button size="small" onClick={handleToggleLowConfidence}>
            {showLowConfidence ? <ExpandLessIcon /> : <ExpandMoreIcon />}
            {' '}
            Show Low Confidence ({filteredLowConfSubOrgs.length})
          </Button>
        </Box>
      )}

      {showLowConfidence && filteredLowConfSubOrgs.length > 0 && (
        <Collapse in={showLowConfidence}>
          <Box className={`sticky-table-container ${darkMode ? 'dark-mode' : 'light-mode'}`}>
            <SuborgsTable
              subOrgs={filteredLowConfSubOrgs}
              ignored={ignored.suborgs}
              recentlyChangedIds={recentlyChangedIds}
              onEdit={onEdit}
              onBatchEdit={onBatchEdit}
              onIgnore={onIgnore}
              onConfirm={onConfirm}
              onRowClick={handleRowClick}
            />
          </Box>
        </Collapse>
      )}

      <Typography sx={{ mt: 1, fontStyle: "italic", fontSize: 11 }}>
        Confidence: High confidence (≥ {CONFIDENCE_THRESHOLD_PERCENT}%) shown by default. 
        Low confidence items (including ignored items with 0% confidence) available in "Show Low Confidence" section.
      </Typography>
    </>
  );
  
  return (
    <>
      <SplitViewLayout
        scanId={scanId ? parseInt(scanId) : 0}
        tabName="subservice_orgs"
        onPdfNavigate={(handler) => setPdfNavigateHandler(() => handler)}
      >
        {content}
      </SplitViewLayout>
      
      <ManualExtractionDialog
        open={manualExtractOpen}
        onClose={() => setManualExtractOpen(false)}
        scanId={scanId ? parseInt(scanId) : 0}
        entityType="subservice_org"
        onSuccess={async () => {
          if (refreshReport) {
            await refreshReport();
          }
        }}
      />
    </>
  );
});
