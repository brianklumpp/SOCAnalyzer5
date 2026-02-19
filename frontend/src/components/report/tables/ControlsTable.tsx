/**
 * ControlsTable Component
 * 
 * Displays controls with edit, ignore, confirm, and recompute functionality.
 * Includes confidence tooltip/modal integration and duplicate detection.
 */

import React, { useState, useMemo, useEffect, useCallback } from 'react';
import { IconButton, Tooltip, CircularProgress, Box, Chip, Dialog, DialogTitle, DialogContent, DialogActions, Button, Typography } from '@mui/material';
import { Refresh as RefreshIcon, Link as LinkIcon, Warning as WarningIcon, WarningAmber as WarningAmberIcon } from '@mui/icons-material';
import { Transform as ConvertIcon, OpenInNew as OpenEditPanelIcon, CheckCircleOutline as AcceptIcon, Block as IgnoreIcon } from '@mui/icons-material';
import EditableTable from '../../EditableTable';
import { controlColumns, defaultVisibleControlColumns } from '../../../config/report/columnDefinitions';
import { MergeSuggestionsPanel } from './MergeSuggestionsPanel';
import { getObjectives, getObjectiveControls, getPrimaryObjectiveCriteria, convertControlToObjective } from '../../../services/objectiveService';
import { ObjectiveSelector } from '../../../components/ObjectiveSelector';

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
  objectives?: any[];
  objectivesLoading?: boolean;
  objectiveMappings?: Map<string | number, any>;
  onObjectivesRefresh?: () => void;
  showToast?: (message: string, severity?: 'success' | 'error' | 'info' | 'warning') => void;
  onOpenEditPanel?: (control: any) => void;
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
  onOpenMappingDetails,
  objectives,
  objectivesLoading,
  objectiveMappings: objectiveMappingsProp,
  onObjectivesRefresh,
  showToast,
  onOpenEditPanel
}: ControlsTableProps) {
  const [recomputingIds, setRecomputingIds] = useState<Set<number>>(new Set());
  const [togglingDeviationIds, setTogglingDeviationIds] = useState<Set<number>>(new Set());
  const [criteriaOpen, setCriteriaOpen] = useState(false);
  const [criteriaLoading, setCriteriaLoading] = useState(false);
  const [criteriaError, setCriteriaError] = useState<string | null>(null);
  const [criteriaData, setCriteriaData] = useState<any | null>(null);
  const [objectiveEditorOpen, setObjectiveEditorOpen] = useState(false);
  const [objectiveEditorControl, setObjectiveEditorControl] = useState<any>(null);
  const [tableResetCounter, setTableResetCounter] = useState(0);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [bulkProcessing, setBulkProcessing] = useState<string | null>(null); // 'convert' | 'ignore' | 'accept' | 'recompute'
  
  // Use cached objective mappings from props, or fallback to fetching if not provided
  const [localObjectiveMappings, setLocalObjectiveMappings] = useState<Map<string | number, any>>(new Map());
  
  // Fetch objective mappings for all controls (only if not provided via props)
  useEffect(() => {
    const fetchMappings = async () => {
      
      if (!scanId || controls.length === 0) return;
      
      try {
        // Fetch all objectives for this scan
        const objectives = await getObjectives(scanId);
        
        // Build a map of control_db_id -> highest-confidence objective
        const mappingsMap = new Map<string | number, any>();
        
        // For each objective, fetch its controls and mappings
        await Promise.all(
          objectives.map(async (objective: any) => {
            try {
              const result = await getObjectiveControls(scanId, objective.id);
              
              // For each control mapping, keep the highest-confidence one
              result.controls.forEach((controlMapping: any) => {
                const controlDbId = controlMapping.control_db_id;
                const controlId = controlMapping.control_id;
                const mappingPayload = { ...controlMapping, objective };
                const confidence = controlMapping.mapping_confidence ?? 0;

                // Only replace if this mapping has higher confidence
                const existingByDbId = controlDbId != null ? mappingsMap.get(controlDbId) : undefined;
                const existingByCtrlId = controlId != null ? mappingsMap.get(controlId) : undefined;
                const existingConfidence = (existingByDbId?.mapping_confidence ?? existingByCtrlId?.mapping_confidence) ?? -1;

                if (confidence > existingConfidence) {
                  if (controlDbId !== undefined && controlDbId !== null) {
                    mappingsMap.set(controlDbId, mappingPayload);
                  }
                  if (controlId !== undefined && controlId !== null) {
                    mappingsMap.set(controlId, mappingPayload);
                  }
                }
              });
            } catch (error) {
              // Silently ignore errors - objectives might not have been extracted yet
              console.debug(`No controls found for objective ${objective.id}`);
            }
          })
        );
        
        setLocalObjectiveMappings(mappingsMap);
      } catch (error) {
        // Silently ignore errors - objectives feature might not be used yet
        console.debug('Objectives not available for this scan');
      }
    };
    
    fetchMappings();
  }, [scanId, controls, objectiveMappingsProp]);
  
  // Merge local mappings with props mappings (props take precedence)
  const objectiveMappings = useMemo(() => {
    const merged = new Map<string | number, any>(localObjectiveMappings);
    if (objectiveMappingsProp) {
      objectiveMappingsProp.forEach((value, key) => {
        merged.set(key, value);
      });
    }
    return merged;
  }, [localObjectiveMappings, objectiveMappingsProp]);
  
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

  const handleOpenObjectiveCriteria = async (control: Control) => {
    if (!scanId || !control?.id) return;
    setCriteriaOpen(true);
    setCriteriaLoading(true);
    setCriteriaError(null);
    setCriteriaData(null);
    try {
      const data = await getPrimaryObjectiveCriteria(scanId, control.id);
      setCriteriaData(data);
    } catch (error: any) {
      setCriteriaError(error?.message || 'Failed to load mapping criteria');
    } finally {
      setCriteriaLoading(false);
    }
  };

  const handleOpenObjectiveEditor = (control: Control) => {
    setObjectiveEditorControl(control);
    setObjectiveEditorOpen(true);
  };

  const handleCloseObjectiveEditor = () => {
    setObjectiveEditorOpen(false);
    setObjectiveEditorControl(null);
  };

  const handleConvertControlToObjective = async (control: Control) => {
    if (!scanId || !control?.id) return;
    try {
      await convertControlToObjective(scanId, control.id);
      onObjectivesRefresh?.();
    } catch (error) {
      console.error('Failed to convert control to objective:', error);
    }
  };

  const handleResetTablePrefs = () => {
    try {
      localStorage.removeItem('table_prefs:report_controls_all_v3');
    } catch {
      // ignore
    }
    setTableResetCounter(prev => prev + 1);
  };

  // Get columns with confidence modal handler
  const columns = useMemo(
    () => controlColumns(
      onOpenConfidenceModal,
      onOpenControlModal,
      frameworkCriteria,
      onOpenMappingDetails,
      handleOpenObjectiveCriteria,
      handleOpenObjectiveEditor,
      handleConvertControlToObjective
    ), 
    [
      onOpenConfidenceModal,
      onOpenControlModal,
      frameworkCriteria,
      onOpenMappingDetails,
      handleOpenObjectiveCriteria,
      handleOpenObjectiveEditor,
      handleConvertControlToObjective
    ]
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
      
      // Add primary objective if available
      const controlDbId = typeof row.id === 'string' ? parseInt(row.id, 10) : row.id;
      const mapping = objectiveMappings.get(controlDbId) ?? objectiveMappings.get(row.control_id);
      if (mapping?.objective) {
        newRow.primary_objective = mapping.objective;
        if (mapping.mapping_confidence !== undefined && mapping.mapping_confidence !== null) {
          newRow.primary_objective_confidence = mapping.mapping_confidence;
        }
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
  }, [controls, objectiveMappings]);

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

  // --- Bulk action handlers ---
  const getSelectedControls = useCallback(() => {
    return controls.filter(c => selectedIds.has(c.id));
  }, [controls, selectedIds]);

  const handleBulkConvert = useCallback(async () => {
    const selected = getSelectedControls();
    if (selected.length === 0) return;
    setBulkProcessing('convert');
    try {
      let successes = 0;
      for (const ctrl of selected) {
        try {
          await convertControlToObjective(scanId, ctrl.id);
          successes++;
        } catch (e) {
          console.error(`Failed to convert control ${ctrl.control_id}:`, e);
        }
      }
      showToast?.(`Converted ${successes}/${selected.length} controls to objectives`, successes === selected.length ? 'success' : 'warning');
      setSelectedIds(new Set());
      onObjectivesRefresh?.();
      onRefresh?.();
    } finally {
      setBulkProcessing(null);
    }
  }, [getSelectedControls, scanId, showToast, onObjectivesRefresh, onRefresh]);

  const handleBulkIgnore = useCallback(async () => {
    const selected = getSelectedControls();
    if (selected.length === 0 || !onIgnore) return;
    setBulkProcessing('ignore');
    try {
      for (const ctrl of selected) {
        onIgnore(ctrl);
      }
      showToast?.(`Ignored ${selected.length} controls`, 'success');
      setSelectedIds(new Set());
    } finally {
      setBulkProcessing(null);
    }
  }, [getSelectedControls, onIgnore, showToast]);

  const handleBulkAccept = useCallback(async () => {
    const selected = getSelectedControls();
    if (selected.length === 0 || !onConfirm) return;
    setBulkProcessing('accept');
    try {
      for (const ctrl of selected) {
        onConfirm(ctrl);
      }
      showToast?.(`Accepted ${selected.length} controls`, 'success');
      setSelectedIds(new Set());
    } finally {
      setBulkProcessing(null);
    }
  }, [getSelectedControls, onConfirm, showToast]);

  const handleBulkRecompute = useCallback(async () => {
    const selected = getSelectedControls();
    if (selected.length === 0) return;
    setBulkProcessing('recompute');
    try {
      let successes = 0;
      for (const ctrl of selected) {
        try {
          await onRecompute(ctrl);
          successes++;
        } catch (e) {
          console.error(`Failed to recompute control ${ctrl.control_id}:`, e);
        }
      }
      showToast?.(`Recomputed ${successes}/${selected.length} controls`, successes === selected.length ? 'success' : 'warning');
      setSelectedIds(new Set());
    } finally {
      setBulkProcessing(null);
    }
  }, [getSelectedControls, onRecompute, showToast]);

  const actionsRenderer = (row: any) => (
    <>
      {onOpenEditPanel && (
        <Tooltip title="Open Edit Panel">
          <span>
            <IconButton size="small" onClick={() => onOpenEditPanel(row)} color="primary">
              <OpenEditPanelIcon fontSize="small" />
            </IconButton>
          </span>
        </Tooltip>
      )}
      <Tooltip title="Convert to Objective">
        <span>
          <IconButton size="small" onClick={() => handleConvertControlToObjective(row)}>
            <ConvertIcon fontSize="small" />
          </IconButton>
        </span>
      </Tooltip>
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
    </>
  );

  return (
    <>
      <EditableTable
        key={tableResetCounter}
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
        storageKey="report_controls_all_v3"
        additionalButtons={
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
            {additionalButtons}
            <Button variant="outlined" size="small" onClick={handleResetTablePrefs}>
              Reset Table View
            </Button>
            <MergeSuggestionsPanel 
              scanId={scanId} 
              onMergeComplete={() => onRefresh?.()} 
            />
            {selectedIds.size > 0 && (
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, ml: 1, pl: 1, borderLeft: '2px solid', borderColor: 'primary.main' }}>
                <Chip label={`${selectedIds.size} selected`} size="small" color="primary" onDelete={() => setSelectedIds(new Set())} />
                <Tooltip title="Accept selected controls (set confidence to 100%)">
                  <span>
                    <Button size="small" variant="outlined" color="success" onClick={handleBulkAccept} disabled={bulkProcessing !== null || !onConfirm}
                      startIcon={bulkProcessing === 'accept' ? <CircularProgress size={14} /> : <AcceptIcon />} sx={{ fontSize: 11, minWidth: 0, textTransform: 'none' }}>
                      Accept
                    </Button>
                  </span>
                </Tooltip>
                <Tooltip title="Ignore selected controls">
                  <span>
                    <Button size="small" variant="outlined" color="error" onClick={handleBulkIgnore} disabled={bulkProcessing !== null || !onIgnore}
                      startIcon={bulkProcessing === 'ignore' ? <CircularProgress size={14} /> : <IgnoreIcon />} sx={{ fontSize: 11, minWidth: 0, textTransform: 'none' }}>
                      Ignore
                    </Button>
                  </span>
                </Tooltip>
                <Tooltip title="Recompute framework mappings for selected">
                  <span>
                    <Button size="small" variant="outlined" onClick={handleBulkRecompute} disabled={bulkProcessing !== null}
                      startIcon={bulkProcessing === 'recompute' ? <CircularProgress size={14} /> : <RefreshIcon />} sx={{ fontSize: 11, minWidth: 0, textTransform: 'none' }}>
                      Recompute
                    </Button>
                  </span>
                </Tooltip>
                <Tooltip title="Convert selected controls to objectives">
                  <span>
                    <Button size="small" variant="outlined" color="secondary" onClick={handleBulkConvert} disabled={bulkProcessing !== null}
                      startIcon={bulkProcessing === 'convert' ? <CircularProgress size={14} /> : <ConvertIcon />} sx={{ fontSize: 11, minWidth: 0, textTransform: 'none' }}>
                      To Objectives
                    </Button>
                  </span>
                </Tooltip>
              </Box>
            )}
          </Box>
        }
        actionsRenderer={actionsRenderer}
        onRowClick={onRowClick}
        selectedIds={selectedIds}
        onSelectionChange={setSelectedIds}
      />

      <Dialog open={criteriaOpen} onClose={() => setCriteriaOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Objective Mapping Criteria</DialogTitle>
        <DialogContent>
          {criteriaLoading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 3 }}>
              <CircularProgress />
            </Box>
          ) : criteriaError ? (
            <Typography color="error">{criteriaError}</Typography>
          ) : criteriaData ? (
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <Box>
                <Typography variant="subtitle2">Control</Typography>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  {criteriaData.control?.control_id || 'Unknown'}
                </Typography>
                <Typography variant="body2">{criteriaData.control?.control_desc}</Typography>
              </Box>
              <Box>
                <Typography variant="subtitle2">Objective</Typography>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  {criteriaData.objective?.objective_id || 'Unlabeled'}
                </Typography>
                <Typography variant="body2">{criteriaData.objective?.objective_text}</Typography>
              </Box>
              <Box>
                <Typography variant="subtitle2">Scores</Typography>
                <Typography variant="body2">Page proximity: {criteriaData.mapping?.page_proximity_score?.toFixed?.(2) ?? 'N/A'}</Typography>
                <Typography variant="body2">Line proximity: {criteriaData.mapping?.line_proximity_score?.toFixed?.(2) ?? 'N/A'}</Typography>
                <Typography variant="body2">GPT alignment: {criteriaData.mapping?.gpt_alignment_score?.toFixed?.(2) ?? 'N/A'}</Typography>
                <Typography variant="body2">ID alignment: {criteriaData.mapping?.id_alignment_score?.toFixed?.(2) ?? 'N/A'}</Typography>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  Final mapping confidence: {criteriaData.mapping?.mapping_confidence?.toFixed?.(2) ?? 'N/A'}
                </Typography>
                <Typography variant="body2">Method: {criteriaData.mapping?.mapping_method || 'N/A'}</Typography>
              </Box>
              <Box>
                <Typography variant="subtitle2">Alignment reasoning</Typography>
                <Typography variant="body2">{criteriaData.mapping?.alignment_reasoning || 'N/A'}</Typography>
              </Box>
            </Box>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCriteriaOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>

      <Dialog open={objectiveEditorOpen} onClose={handleCloseObjectiveEditor} maxWidth="md" fullWidth>
        <DialogTitle>Edit Control Objectives</DialogTitle>
        <DialogContent dividers>
          {objectiveEditorControl ? (
            <ObjectiveSelector
              scanId={scanId}
              controlId={objectiveEditorControl.id}
              onChange={() => onObjectivesRefresh?.()}
            />
          ) : (
            <Typography variant="body2">Select a control to edit objectives.</Typography>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseObjectiveEditor}>Close</Button>
        </DialogActions>
      </Dialog>
    </>
  );
});
