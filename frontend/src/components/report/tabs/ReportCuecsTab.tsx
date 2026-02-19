/**
 * ReportCuecsTab Component
 * 
 * Displays high and low confidence CUECs with add button.
 */

import React from 'react';
import { Box, Typography, Button, Tooltip } from '@mui/material';
import { Refresh as RefreshIcon, PlaylistAdd as ExtractIcon, AccountTree as AccountTreeIcon } from '@mui/icons-material';
import { CuecsTable } from '../tables/CuecsTable';
import { CONFIDENCE_THRESHOLD_PERCENT } from '../../../config/report/constants';
import { SplitViewLayout } from '../SplitViewLayout';
import { ManualExtractionDialog } from '../ManualExtractionDialog';

interface ReportCuecsTabProps {
  scanId: string | undefined;
  filteredHighConfCuecs: any[];
  filteredLowConfCuecs: any[];
  ignored: { controls: Set<number>; cuecs: Set<number>; suborgs: Set<number> };
  recentlyChangedIds: Set<number>;
  showLowConfidence: boolean;
  onToggleLowConfidence: () => void;
  onEdit: (row: any, idx: number) => void;
  onBatchEdit: (changes: { [rowIdx: number]: any }, rows: any[]) => void;
  onRecompute: (row: any) => Promise<void>;
  onRecomputeAllHighConfidence?: () => Promise<void>;
  onMapAllFrameworks?: () => Promise<void>;
  onIgnore: (row: any) => void;
  onConfirm: (row: any) => void;
  onAddCuec: () => void;
  darkMode: boolean;
  tocPageOffset?: number;
  frameworkCriteria?: any;
  onOpenMappingDetails?: (control: any, frameworkType: string) => void;
  refreshReport?: () => Promise<void>;
}

export const ReportCuecsTab = React.memo(function ReportCuecsTab({
  scanId,
  filteredHighConfCuecs,
  filteredLowConfCuecs,
  ignored,
  recentlyChangedIds,
  showLowConfidence,
  onToggleLowConfidence,
  onEdit,
  onBatchEdit,
  onRecompute,
  onRecomputeAllHighConfidence,
  onMapAllFrameworks,
  onIgnore,
  onConfirm,
  onAddCuec,
  darkMode,
  tocPageOffset,
  frameworkCriteria,
  onOpenMappingDetails,
  refreshReport
}: ReportCuecsTabProps) {
  const [pdfNavigateHandler, setPdfNavigateHandler] = React.useState<((snippet: string | null, page?: number | null) => void) | null>(null);
  const [manualExtractOpen, setManualExtractOpen] = React.useState(false);

  const handleRowClick = React.useCallback((row: any) => {
    if (!pdfNavigateHandler) return;
    
    // Check if page refs exist - if not, skip navigation to avoid expensive search
    const pageRefs = row.cuec_page_refs;
    const hasPageRef = Array.isArray(pageRefs) && pageRefs.length > 0;
    
    if (!hasPageRef) {
      console.log('[CUECs Tab] Row clicked but no page refs available, skipping navigation');
      return;
    }
    
    // Extract page number from cuec_page_refs array and apply offset
    let targetPage: number | null = null;
    if (row.cuec_page_refs && Array.isArray(row.cuec_page_refs) && row.cuec_page_refs.length > 0) {
      const pageNum = row.cuec_page_refs[0];
      if (typeof pageNum === 'number') {
        targetPage = pageNum + (tocPageOffset ?? 0);
      }
    }
    
    // Try to get snippet from pdf_snippet field first, then fallback to cuec text
    const snippet = row.pdf_snippet || row.cuec_description || null;
    
    console.log('[CUECs Tab] Row clicked, navigating to:', { 
      snippet: snippet?.substring(0, 50),
      hasPdfSnippet: !!row.pdf_snippet,
      documentPage: row.cuec_page_refs?.[0],
      pdfPage: targetPage
    });
    pdfNavigateHandler(snippet, targetPage);
  }, [pdfNavigateHandler, tocPageOffset]);
  const content = (
    <>
      <Typography variant="h5" gutterBottom sx={{ fontSize: 18, mb: 2 }}>
        Complementary User Entity Controls
      </Typography>

      <Box className={`sticky-table-container ${darkMode ? 'dark-mode' : 'light-mode'}`}>
        <CuecsTable
          highConfCuecs={filteredHighConfCuecs}
          lowConfCuecs={filteredLowConfCuecs}
          ignored={ignored.cuecs}
          recentlyChangedIds={recentlyChangedIds}
          showLowConfidence={showLowConfidence}
          onToggleLowConfidence={onToggleLowConfidence}
          onEdit={onEdit}
          onBatchEdit={onBatchEdit}
          onIgnore={onIgnore}
          onConfirm={onConfirm}
          onRecompute={onRecompute}
          onRowClick={handleRowClick}
          frameworkCriteria={frameworkCriteria}
          onOpenMappingDetails={onOpenMappingDetails}
          additionalButtons={
            <>
              <Button variant="outlined" size="small" onClick={onAddCuec}>
                Add CUEC
              </Button>
              <Tooltip title="Extract CUECs from specific PDF pages">
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
              {onRecomputeAllHighConfidence && (
                <Tooltip title="Recompute framework mappings for all high confidence CUECs">
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
                <Tooltip title="Map CUECs to all available frameworks (NIST, ISO 27001, etc.) — only TSC and COSO are mapped during scan">
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
            </>
          }
        />
      </Box>

      <Typography sx={{ fontStyle: "italic", fontSize: 11, mt: 1 }}>
        Confidence: High confidence (≥ {CONFIDENCE_THRESHOLD_PERCENT}%) shown by default. 
        Low confidence items (including ignored items with 0% confidence) available in "Show Low Confidence" section.
      </Typography>
    </>
  );
  
  return (
    <>
      <SplitViewLayout
        scanId={scanId ? parseInt(scanId) : 0}
        tabName="cuecs"
        onPdfNavigate={(handler) => setPdfNavigateHandler(() => handler)}
      >
        {content}
      </SplitViewLayout>
      
      <ManualExtractionDialog
        open={manualExtractOpen}
        onClose={() => setManualExtractOpen(false)}
        scanId={scanId ? parseInt(scanId) : 0}
        entityType="cuec"
        onSuccess={async () => {
          if (refreshReport) {
            await refreshReport();
          }
        }}
      />
    </>
  );
});
