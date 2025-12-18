/**
 * CuecsTable Component
 * 
 * Displays high and low confidence CUECs (Complementary User Entity Controls)
 * with edit, ignore, confirm, and recompute functionality.
 */

import React, { useState, useRef } from 'react';
import { Box, Button, Collapse, IconButton, Tooltip, CircularProgress, Chip } from '@mui/material';
import { ExpandLess as ExpandLessIcon, ExpandMore as ExpandMoreIcon, Refresh as RefreshIcon } from '@mui/icons-material';
import EditableTable from '../../EditableTable';
import { cuecColumns, defaultVisibleCuecColumns } from '../../../config/report/columnDefinitions';

interface CuecsTableProps {
  highConfCuecs: any[];
  lowConfCuecs: any[];
  ignored: Set<number>;
  recentlyChangedIds: Set<number>;
  showLowConfidence: boolean;
  onToggleLowConfidence: () => void;
  onIgnore: (row: any) => void;
  onConfirm: (row: any) => void;
  onEdit: (row: any, idx: number) => void;
  onBatchEdit: (changes: { [rowIdx: number]: any }, rows: any[]) => void;
  onRecompute: (row: any) => Promise<void>;
  additionalButtons?: React.ReactNode;
  onRowClick?: (row: any) => void;
  frameworkCriteria?: any;
  onOpenMappingDetails?: (control: any, frameworkType: string) => void;
}

export const CuecsTable = React.memo(function CuecsTable({
  highConfCuecs,
  lowConfCuecs,
  ignored,
  recentlyChangedIds,
  showLowConfidence,
  onToggleLowConfidence,
  onIgnore,
  onConfirm,
  onEdit,
  onBatchEdit,
  onRecompute,
  additionalButtons,
  onRowClick,
  frameworkCriteria,
  onOpenMappingDetails
}: CuecsTableProps) {
  const [recomputingIds, setRecomputingIds] = useState<Set<number>>(new Set());
  const lowConfSectionRef = useRef<HTMLDivElement>(null);

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

  // Preprocess rows to format confidence percentages
  const processedHighConfCuecs = highConfCuecs.map(row => {
    const newRow = { ...row };
    if (typeof newRow.cuec_confidence === 'number') {
      newRow.cuec_confidence = `${Math.round(newRow.cuec_confidence * 100)}%`;
    }
    return newRow;
  });

  const processedLowConfCuecs = lowConfCuecs.map(row => {
    const newRow = { ...row };
    if (typeof newRow.cuec_confidence === 'number') {
      newRow.cuec_confidence = `${Math.round(newRow.cuec_confidence * 100)}%`;
    }
    return newRow;
  });

  const handleRecompute = async (row: any) => {
    try {
      setRecomputingIds(prev => new Set([...Array.from(prev), row.id]));
      await onRecompute(row);
    } finally {
      setRecomputingIds(prev => {
        const next = new Set(prev);
        next.delete(row.id);
        return next;
      });
    }
  };

  const actionsRenderer = (row: any) => (
    <Tooltip title="Recompute Framework Mapping">
      <span>
        <IconButton 
          size="small" 
          onClick={() => handleRecompute(row)} 
          disabled={recomputingIds.has(row.id)}
        >
          {recomputingIds.has(row.id) ? (
            <CircularProgress size={14} />
          ) : (
            <RefreshIcon fontSize="small" />
          )}
        </IconButton>
      </span>
    </Tooltip>
  );

  return (
    <>
      {/* High Confidence CUECs */}
      <EditableTable
        columns={cuecColumns(frameworkCriteria, onOpenMappingDetails)}
        rows={processedHighConfCuecs}
        ignored={ignored}
        onIgnore={(rowOrIdx: any) => {
          const row = typeof rowOrIdx === 'number' ? processedHighConfCuecs[rowOrIdx] : rowOrIdx;
          const origRow = highConfCuecs.find(r => r.id === row.id) || row;
          onIgnore(origRow);
        }}
        onConfirm={(row) => onConfirm(row)}
        onEdit={(rowIdxOrRow: any, newRow: any) => {
          const originalRow = typeof rowIdxOrRow === 'number' ? processedHighConfCuecs[rowIdxOrRow] : processedHighConfCuecs.find((r: any) => r.id === newRow.id);
          const mergedRow = { ...originalRow, ...newRow };
          const origIdx = highConfCuecs.findIndex(r => r.id === mergedRow.id);
          onEdit(mergedRow, origIdx >= 0 ? origIdx : rowIdxOrRow);
        }}
        onBatchEdit={(changes) => onBatchEdit(changes, highConfCuecs)}
        recentlyChangedIds={recentlyChangedIds}
        cellSx={{ 
          whiteSpace: 'pre-line', 
          overflow: 'visible', 
          textOverflow: 'clip', 
          wordBreak: 'break-word', 
          padding: '4px 6px', 
          fontSize: 12 
        }}
        defaultVisibleColumns={defaultVisibleCuecColumns}
        storageKey="report_cuecs_high"
        additionalButtons={
          <>
            {additionalButtons}
            {lowConfCuecs.length > 0 && !showLowConfidence && (
              <Chip 
                label={`${lowConfCuecs.length} Low Confidence`}
                size="small"
                color="warning"
                variant="outlined"
                onClick={handleToggleLowConfidence}
                sx={{ ml: 1, cursor: 'pointer' }}
              />
            )}
          </>
        }
        actionsRenderer={actionsRenderer}
        onRowClick={onRowClick}
      />

      {/* Low Confidence CUECs (Collapsible) */}
      {lowConfCuecs.length > 0 && (
        <Box ref={lowConfSectionRef} sx={{ p: 1, ml: 3, scrollMarginTop: '20px' }}>
          <Button size="small" onClick={handleToggleLowConfidence}>
            {showLowConfidence ? <ExpandLessIcon /> : <ExpandMoreIcon />}
            {' '}
            Show Low Confidence ({lowConfCuecs.length})
          </Button>
          <Collapse in={showLowConfidence}>
            <EditableTable
              columns={cuecColumns(frameworkCriteria, onOpenMappingDetails)}
              rows={processedLowConfCuecs}
              ignored={ignored}
              onIgnore={(rowOrIdx: any) => {
                const row = typeof rowOrIdx === 'number' ? processedLowConfCuecs[rowOrIdx] : rowOrIdx;
                const origRow = lowConfCuecs.find(r => r.id === row.id) || row;
                onIgnore(origRow);
              }}
              onConfirm={(row) => onConfirm(row)}
              onEdit={(rowIdxOrRow: any, newRow: any) => {
                const originalRow = typeof rowIdxOrRow === 'number' ? processedLowConfCuecs[rowIdxOrRow] : processedLowConfCuecs.find((r: any) => r.id === newRow.id);
                const mergedRow = { ...originalRow, ...newRow };
                const origIdx = lowConfCuecs.findIndex(r => r.id === mergedRow.id);
                onEdit(mergedRow, origIdx >= 0 ? origIdx : rowIdxOrRow);
              }}
              onBatchEdit={(changes) => onBatchEdit(changes, lowConfCuecs)}
              recentlyChangedIds={recentlyChangedIds}
              cellSx={{ 
                whiteSpace: 'pre-line', 
                overflow: 'visible', 
                textOverflow: 'clip', 
                wordBreak: 'break-word', 
                padding: '4px 6px', 
                fontSize: 12 
              }}
              defaultVisibleColumns={defaultVisibleCuecColumns}
              storageKey="report_cuecs_low"
              actionsRenderer={actionsRenderer}
              onRowClick={onRowClick}
            />
          </Collapse>
        </Box>
      )}
    </>
  );
});
