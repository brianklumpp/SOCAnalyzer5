/**
 * ObjectivesCoverageTab Component
 * 
 * Displays approved control objectives with their linked controls in a table format
 * matching the framework coverage (TSC/COSO) style. Each objective is an accordion
 * section with a table of controls showing ID, description, page/line refs, deviation,
 * and management response. Supports PDF split view — clicking a control or objective
 * header scrolls the PDF to that location.
 * 
 * Quick mapping actions per control row:
 *   x  — Remove/unlink this control from the objective
 *   →  — Redirect: move this control to a different objective (proximity-sorted picker)
 *   +  — Add a new control to the objective (proximity-sorted picker, high-confidence only)
 */

import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import {
  Box,
  Typography,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  CircularProgress,
  Alert,
  IconButton,
  Tooltip,
  Autocomplete,
  TextField,
  Snackbar,
} from '@mui/material';
import {
  ExpandMore as ExpandMoreIcon,
  Warning as WarningIcon,
  Info as InfoIcon,
  Close as CloseIcon,
  Redo as RedoIcon,
  Add as AddIcon,
  CheckCircle as CheckCircleIcon,
  NoteAdd as NoteAddIcon,
  ArrowUpward as ArrowUpIcon,
  ArrowDownward as ArrowDownIcon,
} from '@mui/icons-material';
import {
  getObjectiveControls,
  sortByObjectiveId,
  createMapping,
  deleteMapping,
  updateMapping,
  type ControlObjective,
} from '../../../services/objectiveService';

// ─── Helpers ───────────────────────────────────────────────────────────────────

/** First numeric page ref (or Infinity if none). */
const firstPage = (refs: any): number => {
  if (Array.isArray(refs) && refs.length > 0) {
    const n = Number(refs[0]);
    return Number.isFinite(n) ? n : Infinity;
  }
  return Infinity;
};

/** Absolute page distance between an entity and a reference page. */
const pageDist = (entityPageRefs: any, refPage: number): number => {
  const p = firstPage(entityPageRefs);
  return p === Infinity || refPage === Infinity ? Infinity : Math.abs(p - refPage);
};

/** Sort controls by proximity to a reference page, then by control_id alphanumeric. */
const sortByProximity = (controls: any[], refPage: number): any[] =>
  [...controls].sort((a, b) => {
    const da = pageDist(a.control_page_refs, refPage);
    const db = pageDist(b.control_page_refs, refPage);
    if (da !== db) return da - db;
    const la = a.control_line_ref ?? Infinity;
    const lb = b.control_line_ref ?? Infinity;
    if (la !== lb) return la - lb;
    return (a.control_id || '').localeCompare(b.control_id || '', undefined, { numeric: true });
  });

/** Sort objectives by proximity to a control's page, then by objective_id. */
const sortObjectivesByProximity = (objectives: ControlObjective[], controlPageRefs: any): ControlObjective[] => {
  const cp = firstPage(controlPageRefs);
  return [...objectives].sort((a, b) => {
    const da = pageDist(a.page_refs, cp);
    const db = pageDist(b.page_refs, cp);
    if (da !== db) return da - db;
    const aId = a.objective_id_normalized || a.objective_id || '';
    const bId = b.objective_id_normalized || b.objective_id || '';
    return aId.localeCompare(bId, undefined, { numeric: true });
  });
};

/** Build Autocomplete label for a control. */
const controlLabel = (c: any): string => {
  const id = c.control_id || `#${c.id}`;
  const desc = (c.control_desc || '').substring(0, 60);
  const page = firstPage(c.control_page_refs);
  const suffix = page !== Infinity ? ` (p.${page})` : '';
  return `${id} — ${desc}${desc.length >= 60 ? '…' : ''}${suffix}`;
};

/** Build Autocomplete label for an objective. */
const objectiveLabel = (o: ControlObjective): string => {
  const id = o.objective_id_normalized || o.objective_id || `Obj ${o.id}`;
  const text = (o.objective_text || '').substring(0, 50);
  const page = firstPage(o.page_refs);
  const suffix = page !== Infinity ? ` (p.${page})` : '';
  return `${id} — ${text}${text.length >= 50 ? '…' : ''}${suffix}`;
};

// ─── Component ─────────────────────────────────────────────────────────────────

interface ObjectivesCoverageTabProps {
  scanId: number;
  objectives: ControlObjective[];
  allControls?: any[];            // High-confidence controls for "Add" picker
  onRefresh?: () => void;
  tocPageOffset?: number;
  pdfNavigateHandler?: ((snippet: string | null, page?: number | null) => void) | null;
  onCreateControlForObjective?: (objectiveId: number) => void;
}

export const ObjectivesCoverageTab: React.FC<ObjectivesCoverageTabProps> = ({
  scanId,
  objectives,
  allControls = [],
  onRefresh,
  tocPageOffset,
  pdfNavigateHandler,
  onCreateControlForObjective,
}) => {
  // ── Data state ───────────────────────────────────────────────────────────────
  const [objectiveControls, setObjectiveControls] = useState<Map<number, any[]>>(new Map());
  const [objectiveMeta, setObjectiveMeta] = useState<Map<number, { page_refs?: number[]; line_ref?: number }>>(new Map());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // ── Picker / action state ────────────────────────────────────────────────────
  // Only one picker open at a time.  Key format: "add-{objId}" | "redirect-{objId}-{ctrlDbId}"
  const [activePickerKey, setActivePickerKey] = useState<string | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);          // row being mutated
  const [toast, setToast] = useState<{ message: string; severity: 'success' | 'error' } | null>(null);

  // Ref for container
  const containerRef = useRef<HTMLDivElement>(null);

  // ── Column resize state ──────────────────────────────────────────────────────
  // Default widths in px: [Actions, Control ID, Description, Page, Line, Deviation, Mgmt Response]
  // Description (index 2) is 0 = "auto / remaining space" and handled via CSS flex.
  const COL_HEADERS = ['', 'Control ID', 'Description', 'Page', 'Line', 'Deviation', 'Management Response'];
  const COL_KEYS = ['actions', 'control_id', 'control_desc', 'page', 'line', 'deviation', 'mgmt_response'] as const;
  const SORTABLE_COLS = new Set([1, 2, 3, 4, 5, 6]); // indices of sortable columns (skip actions)
  const [colWidths, setColWidths] = useState<(number | null)[]>([66, 80, null, 48, 44, null, null]);
  const resizeRef = useRef<{ colIdx: number; startX: number; startW: number } | null>(null);

  // ── Sort state (per-objective) ───────────────────────────────────────────────
  type SortDir = 'asc' | 'desc';
  const [sortCol, setSortCol] = useState<number | null>(null);
  const [sortDir, setSortDir] = useState<SortDir>('asc');

  const handleSortClick = useCallback((colIdx: number) => {
    if (!SORTABLE_COLS.has(colIdx)) return;
    if (sortCol === colIdx) {
      setSortDir(prev => prev === 'asc' ? 'desc' : 'asc');
    } else {
      setSortCol(colIdx);
      setSortDir('asc');
    }
  }, [sortCol]);

  /** Sort controls array by current sort column. */
  const applySorting = useCallback((controls: any[]): any[] => {
    if (sortCol === null) return controls;
    const dir = sortDir === 'asc' ? 1 : -1;
    return [...controls].sort((a, b) => {
      let va: any, vb: any;
      switch (sortCol) {
        case 1: // Control ID
          va = a.control_id || '';
          vb = b.control_id || '';
          return dir * va.localeCompare(vb, undefined, { numeric: true });
        case 2: // Description
          va = (a.control_desc || '').toLowerCase();
          vb = (b.control_desc || '').toLowerCase();
          return dir * va.localeCompare(vb);
        case 3: // Page
          va = firstPage(a.control_page_refs);
          vb = firstPage(b.control_page_refs);
          return dir * ((va === Infinity ? 999999 : va) - (vb === Infinity ? 999999 : vb));
        case 4: // Line
          va = a.control_line_ref ?? Number.MAX_SAFE_INTEGER;
          vb = b.control_line_ref ?? Number.MAX_SAFE_INTEGER;
          return dir * (va - vb);
        case 5: // Deviation
          va = a.has_deviation ? 1 : 0;
          vb = b.has_deviation ? 1 : 0;
          if (va !== vb) return dir * (vb - va); // deviations first in asc
          return dir * ((a.deviation_desc || '').localeCompare(b.deviation_desc || ''));
        case 6: // Mgmt Response
          va = a.management_response_text ? 1 : 0;
          vb = b.management_response_text ? 1 : 0;
          if (va !== vb) return dir * (vb - va);
          return dir * ((a.management_response_text || '').localeCompare(b.management_response_text || ''));
        default:
          return 0;
      }
    });
  }, [sortCol, sortDir]);

  const onResizeStart = useCallback((colIdx: number, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const th = (e.target as HTMLElement).closest('th');
    if (!th) return;
    const startW = th.getBoundingClientRect().width;
    resizeRef.current = { colIdx, startX: e.clientX, startW };

    const onMouseMove = (ev: MouseEvent) => {
      if (!resizeRef.current) return;
      const delta = ev.clientX - resizeRef.current.startX;
      const newW = Math.max(30, resizeRef.current.startW + delta);
      setColWidths(prev => {
        const next = [...prev];
        next[resizeRef.current!.colIdx] = newW;
        return next;
      });
    };

    const onMouseUp = () => {
      resizeRef.current = null;
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };

    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
  }, []);

  // ── Deduplicate + sort objectives ────────────────────────────────────────────
  const sortedObjectives = useMemo(() => {
    const seen = new Map<string, ControlObjective>();
    for (const obj of objectives) {
      const key = (obj.objective_id_normalized || obj.objective_id || `__id_${obj.id}`).trim().toLowerCase();
      const existing = seen.get(key);
      if (!existing || (obj.final_confidence || 0) > (existing.final_confidence || 0)) {
        seen.set(key, obj);
      }
    }
    return sortByObjectiveId(Array.from(seen.values()));
  }, [objectives]);

  // ── Load controls per objective ──────────────────────────────────────────────
  const loadControlsForObjective = useCallback(async (objId: number) => {
    try {
      const result = await getObjectiveControls(scanId, objId);
      setObjectiveControls(prev => {
        const next = new Map(prev);
        next.set(objId, result.controls || []);
        return next;
      });
      setObjectiveMeta(prev => {
        const next = new Map(prev);
        next.set(objId, {
          page_refs: (result as any).objective_page_refs,
          line_ref: (result as any).objective_line_ref,
        });
        return next;
      });
    } catch {
      // keep whatever we had
    }
  }, [scanId]);

  const loadAllControls = useCallback(async () => {
    if (objectives.length === 0) {
      setObjectiveControls(new Map());
      setObjectiveMeta(new Map());
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const controlsMap = new Map<number, any[]>();
      const metaMap = new Map<number, { page_refs?: number[]; line_ref?: number }>();
      await Promise.all(
        objectives.map(async (obj) => {
          try {
            const result = await getObjectiveControls(scanId, obj.id);
            controlsMap.set(obj.id, result.controls || []);
            metaMap.set(obj.id, {
              page_refs: (result as any).objective_page_refs,
              line_ref: (result as any).objective_line_ref,
            });
          } catch {
            controlsMap.set(obj.id, []);
          }
        })
      );
      setObjectiveControls(controlsMap);
      setObjectiveMeta(metaMap);
    } catch (err: any) {
      setError(err.message || 'Failed to load objective controls');
    } finally {
      setLoading(false);
    }
  }, [scanId, objectives]);

  useEffect(() => { loadAllControls(); }, [loadAllControls]);

  // ── Escape key to close picker ───────────────────────────────────────────────
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setActivePickerKey(null);
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, []);

  // ── PDF Navigation ───────────────────────────────────────────────────────────
  const handleControlClick = useCallback((control: any, e: React.MouseEvent) => {
    // Don't navigate if clicking an action button or picker
    if ((e.target as HTMLElement).closest('.mapping-actions')) return;
    if (!pdfNavigateHandler) return;
    const pageRefs = control.control_page_refs;
    if (Array.isArray(pageRefs) && pageRefs.length > 0) {
      const offset = tocPageOffset ?? 0;
      pdfNavigateHandler(control.pdf_snippet || control.control_desc || null, pageRefs[0] + offset);
    }
  }, [pdfNavigateHandler, tocPageOffset]);

  const handleObjectiveClick = useCallback((objective: ControlObjective, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!pdfNavigateHandler) return;
    const meta = objectiveMeta.get(objective.id);
    const pageRefs = objective.page_refs || meta?.page_refs;
    if (Array.isArray(pageRefs) && pageRefs.length > 0) {
      const offset = tocPageOffset ?? 0;
      pdfNavigateHandler(objective.objective_text || null, pageRefs[0] + offset);
    }
  }, [pdfNavigateHandler, tocPageOffset, objectiveMeta]);

  // ── Dedup & sort controls within a single objective ──────────────────────────
  const deduplicateControls = (controls: any[]) => {
    const seen = new Map<string, any>();
    for (const ctrl of controls) {
      const key = ctrl.control_id ? String(ctrl.control_id).trim() : `__db_${ctrl.control_db_id}`;
      const existing = seen.get(key);
      if (!existing || (ctrl.mapping_confidence ?? 0) > (existing.mapping_confidence ?? 0)) {
        seen.set(key, ctrl);
      }
    }
    return Array.from(seen.values());
  };

  const sortByLineRef = (controls: any[]) =>
    [...controls].sort((a, b) =>
      (a.control_line_ref ?? Number.MAX_SAFE_INTEGER) - (b.control_line_ref ?? Number.MAX_SAFE_INTEGER)
    );

  // ── Remove mapping (x) ──────────────────────────────────────────────────────
  const handleRemove = useCallback(async (objectiveId: number, control: any, e: React.MouseEvent) => {
    e.stopPropagation();
    const ctrlDbId = control.control_db_id ?? control.id;
    const key = `remove-${objectiveId}-${ctrlDbId}`;
    if (busyKey) return;
    setBusyKey(key);

    // Optimistic: remove from local state immediately
    setObjectiveControls(prev => {
      const next = new Map(prev);
      const list = (next.get(objectiveId) || []).filter(
        (c: any) => (c.control_db_id ?? c.id) !== ctrlDbId
      );
      next.set(objectiveId, list);
      return next;
    });

    try {
      await deleteMapping(scanId, objectiveId, ctrlDbId);
      setToast({ message: `Unmapped ${control.control_id || 'control'}`, severity: 'success' });
    } catch (err: any) {
      setToast({ message: `Failed to remove mapping: ${err.message || err}`, severity: 'error' });
      await loadControlsForObjective(objectiveId);    // revert
    } finally {
      setBusyKey(null);
    }
  }, [scanId, busyKey, loadControlsForObjective]);

  // ── Redirect mapping (→) ────────────────────────────────────────────────────
  const handleRedirect = useCallback(async (
    sourceObjectiveId: number,
    control: any,
    targetObjective: ControlObjective | null,
  ) => {
    if (!targetObjective) return;
    const ctrlDbId = control.control_db_id ?? control.id;
    const key = `redirect-${sourceObjectiveId}-${ctrlDbId}`;
    if (busyKey) return;
    setBusyKey(key);
    setActivePickerKey(null);

    // Optimistic: remove from source
    setObjectiveControls(prev => {
      const next = new Map(prev);
      const list = (next.get(sourceObjectiveId) || []).filter(
        (c: any) => (c.control_db_id ?? c.id) !== ctrlDbId
      );
      next.set(sourceObjectiveId, list);
      return next;
    });

    try {
      // Step 1: unlink from current objective
      await deleteMapping(scanId, sourceObjectiveId, ctrlDbId);
      // Step 2: link to target objective
      await createMapping(scanId, {
        objective_id: targetObjective.id,
        control_id: ctrlDbId,
        mapping_confidence: 1.0,
      } as any);
      setToast({
        message: `Moved ${control.control_id || 'control'} → ${targetObjective.objective_id_normalized || targetObjective.objective_id || 'objective'}`,
        severity: 'success',
      });
      // Refresh target accordion's controls
      await loadControlsForObjective(targetObjective.id);
    } catch (err: any) {
      setToast({ message: `Redirect failed: ${err.message || err}`, severity: 'error' });
      // Re-fetch source to restore
      await loadControlsForObjective(sourceObjectiveId);
    } finally {
      setBusyKey(null);
    }
  }, [scanId, busyKey, loadControlsForObjective]);

  // ── Add mapping (+) ─────────────────────────────────────────────────────────
  const handleAdd = useCallback(async (objectiveId: number, selectedControl: any | null) => {
    if (!selectedControl) return;
    const ctrlDbId = selectedControl.id;
    const key = `add-${objectiveId}-${ctrlDbId}`;
    if (busyKey) return;
    setBusyKey(key);
    setActivePickerKey(null);

    try {
      await createMapping(scanId, {
        objective_id: objectiveId,
        control_id: ctrlDbId,
        mapping_confidence: 1.0,
      } as any);
      setToast({
        message: `Mapped ${selectedControl.control_id || 'control'} to objective`,
        severity: 'success',
      });
      // Refresh to get full mapping data from backend
      await loadControlsForObjective(objectiveId);
    } catch (err: any) {
      setToast({ message: `Failed to add mapping: ${err.message || err}`, severity: 'error' });
    } finally {
      setBusyKey(null);
    }
  }, [scanId, busyKey, loadControlsForObjective]);

  // ── Confirm / unconfirm mapping (✓) ──────────────────────────────────────────
  const handleConfirmMapping = useCallback(async (objectiveId: number, control: any, e: React.MouseEvent) => {
    e.stopPropagation();
    const mappingId = control.mapping_id;
    if (!mappingId || busyKey) return;
    const isCurrentlyConfirmed = control.confirmed || false;
    const key = `confirm-${objectiveId}-${mappingId}`;
    setBusyKey(key);

    // Optimistic toggle
    setObjectiveControls(prev => {
      const next = new Map(prev);
      const list = (next.get(objectiveId) || []).map((c: any) =>
        (c.mapping_id === mappingId) ? { ...c, confirmed: !isCurrentlyConfirmed } : c
      );
      next.set(objectiveId, list);
      return next;
    });

    try {
      await updateMapping(scanId, mappingId, { confirmed: !isCurrentlyConfirmed } as any);
      setToast({
        message: !isCurrentlyConfirmed ? `Mapping confirmed` : `Confirmation removed`,
        severity: 'success',
      });
    } catch (err: any) {
      setToast({ message: `Failed to update: ${err.message || err}`, severity: 'error' });
      await loadControlsForObjective(objectiveId);
    } finally {
      setBusyKey(null);
    }
  }, [scanId, busyKey, loadControlsForObjective]);

  // ── Build the "Add" picker options for a given objective ─────────────────────
  const getAddCandidates = useCallback((objectiveId: number, objective: ControlObjective) => {
    const alreadyMapped = new Set(
      (objectiveControls.get(objectiveId) || []).map((c: any) => c.control_db_id ?? c.id)
    );
    const candidates = allControls.filter((c: any) => !alreadyMapped.has(c.id));
    const objPage = firstPage(objective.page_refs || objectiveMeta.get(objectiveId)?.page_refs);
    return sortByProximity(candidates, objPage);
  }, [allControls, objectiveControls, objectiveMeta]);

  // ── Build the "Redirect" picker options (all other objectives) ──────────────
  const getRedirectCandidates = useCallback((currentObjectiveId: number, control: any) => {
    const others = sortedObjectives.filter(o => o.id !== currentObjectiveId);
    return sortObjectivesByProximity(others, control.control_page_refs);
  }, [sortedObjectives]);

  // ── Render ───────────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 400 }}>
        <CircularProgress />
        <Typography sx={{ ml: 2 }}>Loading objective coverage...</Typography>
      </Box>
    );
  }

  if (error) {
    return <Alert severity="error" sx={{ m: 2 }}>{error}</Alert>;
  }

  if (objectives.length === 0) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="info" icon={<InfoIcon />}>
          <Typography variant="body1" gutterBottom>No approved objectives found for this scan.</Typography>
          <Typography variant="body2">Objectives must be extracted and approved before they appear in coverage view.</Typography>
        </Alert>
      </Box>
    );
  }

  return (
    <Box ref={containerRef} sx={{ minWidth: 0, overflow: 'hidden', width: '100%', maxWidth: '100%' }}>
      <div className="tsc-coso-align-heading">Objective Coverage</div>

      {sortedObjectives.map((objective, index) => {
        const rawControls = objectiveControls.get(objective.id) || [];
        const uniqueControls = deduplicateControls(rawControls);
        const sortedControls = sortCol !== null ? applySorting(uniqueControls) : sortByLineRef(uniqueControls);
        const controlsWithDeviation = uniqueControls.filter((c: any) => c.has_deviation === true);
        const controlCount = uniqueControls.length;
        const meta = objectiveMeta.get(objective.id);
        const objPageRefs = objective.page_refs || meta?.page_refs;

        const addPickerKey = `add-${objective.id}`;
        const addPickerOpen = activePickerKey === addPickerKey;

        return (
          <Accordion key={objective.id} defaultExpanded={index === 0} sx={{ mb: 1, boxShadow: 1, minWidth: 0, maxWidth: '100%', overflow: 'hidden', width: '100%' }}>
            {/* ── Accordion header ────────────────────────────────────────── */}
            <AccordionSummary expandIcon={<ExpandMoreIcon />} sx={{ bgcolor: 'grey.50', '&:hover': { bgcolor: 'grey.100' }, minWidth: 0, maxWidth: '100%', overflow: 'hidden', '& .MuiAccordionSummary-content': { minWidth: 0, overflow: 'hidden' } }}>
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%', minWidth: 0, overflow: 'hidden', pr: 2 }}>
                <Box sx={{ flex: 1, minWidth: 0, overflow: 'hidden' }}>
                  <Typography sx={{ fontWeight: 600, fontSize: 14 }}>
                    {objective.objective_id_normalized || objective.objective_id || `Objective ${objective.id}`}
                    {objPageRefs && objPageRefs.length > 0 && (
                      <Typography
                        component="span"
                        sx={{ ml: 1.5, fontSize: 11, color: 'primary.main', cursor: 'pointer', textDecoration: 'underline', '&:hover': { color: 'primary.dark' } }}
                        onClick={(e) => handleObjectiveClick(objective, e)}
                      >
                        (p.{objPageRefs[0]})
                      </Typography>
                    )}
                  </Typography>
                  <Typography sx={{ fontSize: 12, color: 'text.secondary', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {objective.objective_text}
                  </Typography>
                </Box>
                <Box sx={{ display: 'flex', gap: 2, fontSize: 12, color: 'text.secondary', flexShrink: 0, ml: 2 }}>
                  <span><strong>{controlCount}</strong> control{controlCount !== 1 ? 's' : ''}</span>
                  {(() => {
                    const confirmedCount = uniqueControls.filter((c: any) => c.confirmed).length;
                    return confirmedCount > 0 ? (
                      <span style={{ color: '#2e7d32' }}>
                        <CheckCircleIcon sx={{ fontSize: 12, verticalAlign: 'text-bottom', mr: 0.25 }} />
                        <strong>{confirmedCount}</strong>/{controlCount}
                      </span>
                    ) : null;
                  })()}
                  {controlsWithDeviation.length > 0 && (
                    <span style={{ color: '#d32f2f' }}><strong>{controlsWithDeviation.length}</strong> deviation{controlsWithDeviation.length !== 1 ? 's' : ''}</span>
                  )}
                </Box>
              </Box>
            </AccordionSummary>

            {/* ── Accordion body ──────────────────────────────────────────── */}
            <AccordionDetails sx={{ p: 0, minWidth: 0, maxWidth: '100%', overflow: 'hidden' }}>
              <table className="tsc-coso-table objective-coverage-table">
                <colgroup>
                  {colWidths.map((w, i) => (
                    <col key={i} style={w ? { width: w } : undefined} />
                  ))}
                </colgroup>
                <thead>
                  <tr>
                    {COL_HEADERS.map((label, i) => {
                      const isResizing = resizeRef.current?.colIdx === i;
                      const isSortable = SORTABLE_COLS.has(i);
                      const isSorted = sortCol === i;
                      return (
                        <th
                          key={i}
                          style={{
                            ...(i === 0 ? { textAlign: 'center', padding: '4px 2px' } : {}),
                            ...(isSortable ? { cursor: 'pointer', userSelect: 'none' } : {}),
                          }}
                          onClick={isSortable ? () => handleSortClick(i) : undefined}
                        >
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 2 }}>
                            {label}
                            {isSorted && (
                              sortDir === 'asc'
                                ? <ArrowUpIcon sx={{ fontSize: 13, verticalAlign: 'middle' }} />
                                : <ArrowDownIcon sx={{ fontSize: 13, verticalAlign: 'middle' }} />
                            )}
                          </span>
                          {/* Resize handle on right edge of every column except last */}
                          {i < COL_HEADERS.length - 1 && (
                            <div
                              className={`col-resize-handle${isResizing ? ' resizing' : ''}`}
                              onMouseDown={(e) => onResizeStart(i, e)}
                            />
                          )}
                        </th>
                      );
                    })}
                  </tr>
                </thead>
                <tbody>
                  {sortedControls.length > 0 ? sortedControls.map((control: any) => {
                    const ctrlDbId = control.control_db_id ?? control.id;
                    const hasDev = control.has_deviation === true && control.deviation_desc;
                    const hasMgmtResponse = control.management_response_text;
                    const pageRefs = control.control_page_refs;
                    const hasPageRef = Array.isArray(pageRefs) && pageRefs.length > 0;

                    const redirectKey = `redirect-${objective.id}-${ctrlDbId}`;
                    const isRedirectOpen = activePickerKey === redirectKey;
                    const isConfirmed = control.confirmed || false;
                    const isBusy = busyKey?.startsWith(`remove-${objective.id}-${ctrlDbId}`) ||
                                   busyKey?.startsWith(`redirect-${objective.id}-${ctrlDbId}`) ||
                                   busyKey === `confirm-${objective.id}-${control.mapping_id}`;

                    return (
                      <React.Fragment key={control.mapping_id || ctrlDbId}>
                        <tr
                          className={hasDev ? 'tsc-coso-row-exception' : ''}
                          style={{
                            cursor: 'pointer',
                            ...(isConfirmed ? { background: 'rgba(46, 125, 50, 0.04)', borderLeft: '3px solid #2e7d32' } : {}),
                          }}
                          onClick={(e) => handleControlClick(control, e)}
                        >
                          {/* ── Actions cell ─────────────────────────────── */}
                          <td style={{ textAlign: 'center', padding: '2px 2px', whiteSpace: 'nowrap', overflow: 'hidden' }} className="mapping-actions">
                            {isBusy ? (
                              <CircularProgress size={14} />
                            ) : (
                              <>
                                <Tooltip title="Remove mapping" arrow>
                                  <IconButton
                                    size="small"
                                    onClick={(e) => handleRemove(objective.id, control, e)}
                                    sx={{ p: '2px', color: '#d32f2f', '&:hover': { bgcolor: 'error.light', color: '#fff' } }}
                                  >
                                    <CloseIcon sx={{ fontSize: 15 }} />
                                  </IconButton>
                                </Tooltip>
                                <Tooltip title="Move to different objective" arrow>
                                  <IconButton
                                    size="small"
                                    onClick={(e) => {
                                      e.stopPropagation();
                                      setActivePickerKey(isRedirectOpen ? null : redirectKey);
                                    }}
                                    sx={{
                                      p: '2px', ml: '1px',
                                      color: isRedirectOpen ? '#fff' : '#1976d2',
                                      bgcolor: isRedirectOpen ? '#1976d2' : 'transparent',
                                      '&:hover': { bgcolor: isRedirectOpen ? '#1565c0' : 'action.hover' },
                                    }}
                                  >
                                    <RedoIcon sx={{ fontSize: 15 }} />
                                  </IconButton>
                                </Tooltip>
                                <Tooltip title={isConfirmed ? 'Unconfirm mapping' : 'Confirm mapping'} arrow>
                                  <IconButton
                                    size="small"
                                    onClick={(e) => handleConfirmMapping(objective.id, control, e)}
                                    sx={{
                                      p: '2px', ml: '1px',
                                      color: isConfirmed ? '#2e7d32' : '#bdbdbd',
                                      '&:hover': { bgcolor: isConfirmed ? 'error.light' : 'success.light', color: '#fff' },
                                    }}
                                  >
                                    <CheckCircleIcon sx={{ fontSize: 15 }} />
                                  </IconButton>
                                </Tooltip>
                              </>
                            )}
                          </td>

                          <td>{control.control_id}</td>
                          <td>{control.control_desc || '\u2014'}</td>
                          <td style={{ textAlign: 'center' }}>
                            {hasPageRef ? (
                              <span style={{ color: '#1976d2' }}>
                                {pageRefs.length > 1
                                  ? (pageRefs[pageRefs.length - 1] - pageRefs[0] === pageRefs.length - 1
                                      ? `${pageRefs[0]}\u2013${pageRefs[pageRefs.length - 1]}`  // contiguous range: "103–105"
                                      : pageRefs.join(', '))                                       // non-contiguous: "103, 110"
                                  : pageRefs[0]}
                              </span>
                            ) : <span style={{ color: '#999' }}>{'\u2014'}</span>}
                          </td>
                          <td style={{ textAlign: 'center' }}>
                            {control.control_line_ref
                              ? <span style={{ color: '#1976d2' }}>{control.control_line_ref}</span>
                              : <span style={{ color: '#999' }}>{'\u2014'}</span>}
                          </td>
                          <td>
                            {hasDev ? (
                              <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 0.5 }}>
                                <WarningIcon sx={{ color: '#d32f2f', fontSize: 14, mt: '1px', flexShrink: 0 }} />
                                <span>{control.deviation_desc}</span>
                              </Box>
                            ) : <span style={{ color: '#999' }}>{'\u2014'}</span>}
                          </td>
                          <td>
                            {hasMgmtResponse
                              ? <span>{control.management_response_text}</span>
                              : hasDev
                                ? <span style={{ color: '#999', fontStyle: 'italic' }}>None provided</span>
                                : <span style={{ color: '#999' }}>{'\u2014'}</span>}
                          </td>
                        </tr>

                        {/* ── Inline redirect picker row ────────────────── */}
                        {isRedirectOpen && (
                          <tr>
                            <td colSpan={7} style={{ padding: '4px 8px', background: '#f5f5f5' }}>
                              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                <RedoIcon sx={{ fontSize: 16, color: '#1976d2', flexShrink: 0 }} />
                                <Typography sx={{ fontSize: 12, color: 'text.secondary', flexShrink: 0 }}>
                                  Move to:
                                </Typography>
                                <Autocomplete
                                  size="small"
                                  autoFocus
                                  openOnFocus
                                  options={getRedirectCandidates(objective.id, control)}
                                  getOptionLabel={objectiveLabel}
                                  onChange={(_e, value) => handleRedirect(objective.id, control, value)}
                                  renderInput={(params) => (
                                    <TextField
                                      {...params}
                                      placeholder="Search objectives…"
                                      variant="outlined"
                                      autoFocus
                                      sx={{ '& .MuiInputBase-root': { fontSize: 12, py: 0 } }}
                                    />
                                  )}
                                  renderOption={(props, option) => {
                                    const { key, ...rest } = props as any;
                                    const dist = pageDist(option.page_refs, firstPage(control.control_page_refs));
                                    return (
                                      <li key={option.id} {...rest} style={{ fontSize: 12, padding: '4px 8px' }}>
                                        <Box sx={{ display: 'flex', justifyContent: 'space-between', width: '100%', gap: 1 }}>
                                          <span>{objectiveLabel(option)}</span>
                                          {dist !== Infinity && (
                                            <Typography sx={{ fontSize: 10, color: 'text.disabled', flexShrink: 0 }}>
                                              {dist === 0 ? 'same page' : `${dist}p away`}
                                            </Typography>
                                          )}
                                        </Box>
                                      </li>
                                    );
                                  }}
                                  sx={{ flex: 1, minWidth: 200 }}
                                  slotProps={{
                                    paper: { sx: { fontSize: 12 } },
                                    listbox: { sx: { maxHeight: 220 } },
                                  }}
                                />
                                <IconButton size="small" onClick={() => setActivePickerKey(null)} sx={{ p: '2px' }}>
                                  <CloseIcon sx={{ fontSize: 14 }} />
                                </IconButton>
                              </Box>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  }) : (
                    <tr>
                      <td colSpan={7} style={{ textAlign: 'center', padding: 12, color: '#999' }}>
                        No controls mapped to this objective
                      </td>
                    </tr>
                  )}

                  {/* ── Add control row ──────────────────────────────────── */}
                  <tr>
                    <td colSpan={7} style={{ padding: '4px 8px', borderTop: '1px solid #eee' }}>
                      {addPickerOpen ? (
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                          <AddIcon sx={{ fontSize: 16, color: '#2e7d32', flexShrink: 0 }} />
                          <Typography sx={{ fontSize: 12, color: 'text.secondary', flexShrink: 0 }}>
                            Add control:
                          </Typography>
                          <Autocomplete
                            size="small"
                            autoFocus
                            openOnFocus
                            options={getAddCandidates(objective.id, objective)}
                            getOptionLabel={controlLabel}
                            onChange={(_e, value) => handleAdd(objective.id, value)}
                            renderInput={(params) => (
                              <TextField
                                {...params}
                                placeholder="Search controls…"
                                variant="outlined"
                                autoFocus
                                sx={{ '& .MuiInputBase-root': { fontSize: 12, py: 0 } }}
                              />
                            )}
                            renderOption={(props, option) => {
                              const { key, ...rest } = props as any;
                              const dist = pageDist(option.control_page_refs, firstPage(objective.page_refs || objectiveMeta.get(objective.id)?.page_refs));
                              return (
                                <li key={option.id} {...rest} style={{ fontSize: 12, padding: '4px 8px' }}>
                                  <Box sx={{ display: 'flex', justifyContent: 'space-between', width: '100%', gap: 1 }}>
                                    <span>{controlLabel(option)}</span>
                                    {dist !== Infinity && (
                                      <Typography sx={{ fontSize: 10, color: 'text.disabled', flexShrink: 0 }}>
                                        {dist === 0 ? 'same page' : `${dist}p away`}
                                      </Typography>
                                    )}
                                  </Box>
                                </li>
                              );
                            }}
                            sx={{ flex: 1, minWidth: 200 }}
                            slotProps={{
                              paper: { sx: { fontSize: 12 } },
                              listbox: { sx: { maxHeight: 220 } },
                            }}
                          />
                          <IconButton size="small" onClick={() => setActivePickerKey(null)} sx={{ p: '2px' }}>
                            <CloseIcon sx={{ fontSize: 14 }} />
                          </IconButton>
                        </Box>
                      ) : (
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                          <Tooltip title="Add existing control to this objective" arrow>
                            <IconButton
                              size="small"
                              onClick={() => setActivePickerKey(addPickerKey)}
                              disabled={busyKey !== null}
                              sx={{ p: '2px', color: '#2e7d32', '&:hover': { bgcolor: 'success.light', color: '#fff' } }}
                            >
                              <AddIcon sx={{ fontSize: 16 }} />
                            </IconButton>
                          </Tooltip>
                          {onCreateControlForObjective && (
                            <Tooltip title="Create new control and map to this objective" arrow>
                              <IconButton
                                size="small"
                                onClick={() => onCreateControlForObjective(objective.id)}
                                disabled={busyKey !== null}
                                sx={{ p: '2px', color: '#1976d2', '&:hover': { bgcolor: 'primary.light', color: '#fff' } }}
                              >
                                <NoteAddIcon sx={{ fontSize: 16 }} />
                              </IconButton>
                            </Tooltip>
                          )}
                        </Box>
                      )}
                    </td>
                  </tr>
                </tbody>
              </table>
            </AccordionDetails>
          </Accordion>
        );
      })}

      {/* ── Toast ────────────────────────────────────────────────────────── */}
      <Snackbar
        open={toast !== null}
        autoHideDuration={3000}
        onClose={() => setToast(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        {toast ? (
          <Alert
            onClose={() => setToast(null)}
            severity={toast.severity}
            variant="filled"
            sx={{ fontSize: 12 }}
          >
            {toast.message}
          </Alert>
        ) : undefined}
      </Snackbar>
    </Box>
  );
};

export default ObjectivesCoverageTab;
