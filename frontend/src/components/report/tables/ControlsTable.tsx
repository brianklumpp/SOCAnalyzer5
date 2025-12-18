/**
 * ControlsTable Component
 * 
 * Displays controls with edit, ignore, confirm, and recompute functionality.
 * Includes confidence tooltip/modal integration and duplicate detection.
 */

import React, { useState, useMemo } from 'react';
import { IconButton, Tooltip, CircularProgress, Box, Chip } from '@mui/material';
import { Refresh as RefreshIcon, Link as LinkIcon, Warning as WarningIcon, WarningAmber as WarningAmberIcon } from '@mui/icons-material';
import EditableTable from '../../EditableTable';
import { controlColumns, defaultVisibleControlColumns } from '../../../config/report/columnDefinitions';
import { MergeSuggestionsPanel } from './MergeSuggestionsPanel';

interface Control {
  id: number;
  control_id: string;
  control_status?: string;
  control_tsc_section?: string;
  control_seq?: number;
  is_duplicate_instance?: boolean;
  duplicate_group_id?: string;
  instance_differentiator?: {
    instance_number?: number;
    total_instances?: number;
    criteria_differ?: boolean;
    test_differ?: boolean;
    deviation_differ?: boolean;
  };
  [key: string]: any;
}

interface ControlsTableProps {
  controls: Control[];
  ignored: Set<number>;
  scanId: number;  // Add scanId for merge suggestions
  onEdit: (row: Control, idx: number) => void;
  onBatchEdit?: (changes: { [rowIdx: number]: any }, sectionRows: any[]) => void;
  onRecompute: (row: any) => Promise<void>;
  onIgnore?: (row: any) => void;
  onConfirm?: (row: any) => void;
  onRefresh?: () => void;  // Add refresh callback for merge complete
  onToggleDeviation?: (row: any, hasDeviation: boolean) => Promise<void>;
  additionalButtons?: React.ReactNode;
  onOpenConfidenceModal?: (control: any) => void;
  onOpenControlModal?: (control: any) => void;
  onRowClick?: (row: any) => void;
  frameworkCriteria?: any;
  onOpenMappingDetails?: (control: any, frameworkType: string) => void;
}

export const ControlsTable = React.memo(function ControlsTable({ 
  controls, 
  ignored, 
  scanId,
  onEdit, 
  onBatchEdit, 
  onRecompute, 
  onIgnore, 
  onConfirm, 
  onRefresh,
  onToggleDeviation,
  additionalButtons, 
  onOpenConfidenceModal,
  onOpenControlModal,
  onRowClick,
  frameworkCriteria,
  onOpenMappingDetails
}: ControlsTableProps) {
  const [recomputingIds, setRecomputingIds] = useState<Set<number>>(new Set());
  const [togglingDeviationIds, setTogglingDeviationIds] = useState<Set<number>>(new Set());
  
  // Detect duplicate control IDs
  const duplicateControlIds = useMemo(() => {
    const idCounts = new Map<string, number>();
    controls.forEach(ctrl => {
      const controlId = ctrl.control_id;
      if (controlId) {
        const idStr = String(controlId); // Convert to string to handle both string and number types
        idCounts.set(idStr, (idCounts.get(idStr) || 0) + 1);
      }
    });
    const duplicates = new Set<string>();
    idCounts.forEach((count, id) => {
      if (count > 1) {
        duplicates.add(id);
      }
    });
    return duplicates;
  }, [controls]);

  // Get columns with confidence modal handler
  const columns = useMemo(
    () => controlColumns(onOpenConfidenceModal, onOpenControlModal, frameworkCriteria, onOpenMappingDetails), 
    [onOpenConfidenceModal, onOpenControlModal, frameworkCriteria, onOpenMappingDetails]
  );

  // Preprocess rows to format similarity percentages and add instance info
  const processedControls = useMemo(() => {
    return controls.map(row => {
      const newRow = { ...row };
      // Format control_confidence as percentage for display
      if (typeof newRow.control_confidence === 'number') {
        newRow.control_confidence = `${Math.round(newRow.control_confidence * 100)}%`;
      }
      if (typeof newRow.control_tsc_similarity === 'number') {
        newRow.control_tsc_similarity = `${Math.round(newRow.control_tsc_similarity * 100)}%`;
      }
      if (typeof newRow.control_coso_similarity === 'number') {
        newRow.control_coso_similarity = `${Math.round(newRow.control_coso_similarity * 100)}%`;
      }
      
      // Add instance badge if this is a duplicate instance
      if (newRow.is_duplicate_instance && newRow.instance_differentiator) {
        const diff = newRow.instance_differentiator;
        const instanceNum = diff.instance_number || '?';
        const totalInstances = diff.total_instances || '?';
        
        newRow._instance_badge = (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <LinkIcon fontSize="small" sx={{ color: '#1976d2' }} />
            <Chip 
              size="small" 
              label={`Instance ${instanceNum} of ${totalInstances}`}
              color="info"
              sx={{ height: 20, fontSize: 10 }}
            />
          </Box>
        );
      }
      
      return newRow;
    });
  }, [controls]);

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

  // Local handleIgnore - call parent's onIgnore if provided
  const handleIgnore = (row: any, idx: number, type: string) => {
    if (onIgnore) {
      onIgnore(row);
    } else {
      // Fallback to old behavior if onIgnore not provided
      const newRow = { ...row, confidence: 0, cuec_confidence: 0, control_confidence: 0 };
      onEdit(newRow, idx);
    }
  };

  const handleToggleDeviation = async (row: any) => {
    if (!onToggleDeviation) return;
    
    try {
      setTogglingDeviationIds(prev => new Set([...Array.from(prev), row.id]));
      await onToggleDeviation(row, !row.has_deviation);
    } finally {
      setTogglingDeviationIds(prev => {
        const next = new Set(prev);
        next.delete(row.id);
        return next;
      });
    }
  };

  const actionsRenderer = (row: any) => (
    <Box sx={{ display: 'flex', gap: 0.5 }}>
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
      {onToggleDeviation && (
        <Tooltip title={row.has_deviation ? "Remove Deviation" : "Mark as Deviation"}>
          <span>
            <IconButton 
              size="small" 
              onClick={() => handleToggleDeviation(row)} 
              disabled={togglingDeviationIds.has(row.id)}
              color={row.has_deviation ? "warning" : "default"}
            >
              {togglingDeviationIds.has(row.id) ? (
                <CircularProgress size={14} />
              ) : row.has_deviation ? (
                <WarningIcon fontSize="small" />
              ) : (
                <WarningAmberIcon fontSize="small" />
              )}
            </IconButton>
          </span>
        </Tooltip>
      )}
    </Box>
  );

  return (
    <EditableTable
      rows={processedControls}
      columns={columns}
      ignored={ignored}
      recentlyChangedIds={new Set()}
      onIgnore={(rowOrIdx: number | any) => {
        const row = typeof rowOrIdx === 'number' ? processedControls[rowOrIdx] : rowOrIdx;
        if (row) handleIgnore(row, row.id || rowOrIdx, 'controls');
      }}
      onConfirm={onConfirm ? (row: any) => onConfirm(row) : undefined}
      onEdit={(rowIdxOrRow: any, newRow: any) => {
        // Get the original full row
        const originalRow = typeof rowIdxOrRow === 'number' ? processedControls[rowIdxOrRow] : processedControls.find((r: any) => r.id === newRow.id);
        // Merge changes with original row to preserve all fields
        const mergedRow = { ...originalRow, ...newRow };
        console.log('[ControlsTable] onEdit called:', {
          hasAnalystNotes: 'analyst_notes' in mergedRow,
          analystNotesValue: mergedRow.analyst_notes,
          allKeys: Object.keys(mergedRow)
        });
        const parentIdx = controls.findIndex((r: any) => r.id === mergedRow.id);
        onEdit(mergedRow, parentIdx >= 0 ? parentIdx : rowIdxOrRow);
      }}
      onBatchEdit={onBatchEdit ? (changes: any, displayRows: any[]) => {
        // Map sorted display indices back to parent array indices using row.id
        const mappedChanges: { [parentIdx: number]: any } = {};
        Object.keys(changes).forEach((sortedIdxStr) => {
          const sortedIdx = parseInt(sortedIdxStr, 10);
          const row = displayRows[sortedIdx];
          if (row) {
            const parentIdx = controls.findIndex((r: any) => r.id === row.id);
            if (parentIdx >= 0) {
              mappedChanges[parentIdx] = changes[sortedIdxStr];
            }
          }
        });
        onBatchEdit(mappedChanges, controls);
      } : undefined}
      duplicateIds={duplicateControlIds}
      tableSx={{ width: '100%' }}
      cellSx={{ 
        whiteSpace: 'pre-line', 
        overflow: 'visible', 
        textOverflow: 'clip', 
        wordBreak: 'break-word', 
        padding: '4px 6px', 
        fontSize: 12 
      }}
      defaultVisibleColumns={defaultVisibleControlColumns}
      storageKey="report_controls_all"
      additionalButtons={
        <Box sx={{ display: 'flex', alignItems: 'center' }}>
          {additionalButtons}
          <MergeSuggestionsPanel 
            scanId={scanId} 
            onMergeComplete={() => onRefresh?.()} 
          />
        </Box>
      }
      actionsRenderer={actionsRenderer}
      onRowClick={onRowClick}
    />
  );
});
