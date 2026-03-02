import React, { useState, useEffect, useCallback } from "react";
import { Table, TableBody, TableCell, TableContainer, TableHead, TableRow, IconButton, TextField, Button, TableSortLabel, Box, Tooltip, Menu, MenuItem, Checkbox, ListItemText, Select, FormControl, useTheme, CircularProgress, Backdrop } from "@mui/material";
import EditIcon from "@mui/icons-material/Edit";
import SaveIcon from "@mui/icons-material/Save";
import CancelIcon from "@mui/icons-material/Cancel";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";

interface EditableTableColumn {
  key: string;
  label: string;
  width?: number;
  format?: (value: any) => string;
  editable?: boolean; // new: allow marking columns as read-only
  headerInfo?: string; // optional header info tooltip text; shows info badge
}

interface EditableTableProps {
  columns: EditableTableColumn[];
  rows: any[];
  ignored: Set<number>;
  onIgnore: (rowIdx: number) => void;
  onEdit: (rowIdx: number, newRow: any) => void;
  onBatchEdit?: (changes: { [rowIdx: number]: any }, displayRows: any[]) => void;
  recentlyChangedIds?: Set<number>;
  duplicateIds?: Set<string>; // Set of control_id values that have duplicates
  tableSx?: any;
  cellSx?: any;
  defaultVisibleColumns?: string[];
  storageKey?: string; // persist widths/visible columns
  actionsRenderer?: (row: any, rowIdx: number) => React.ReactNode; // optional extra actions per row
  onConfirm?: (row: any) => void; // optional confirm button to set confidence to 100%
  additionalButtons?: React.ReactNode; // optional additional buttons to prepend to button row
  onRowClick?: (row: any) => void; // optional row click handler for PDF navigation
  selectedIds?: Set<number>; // optional set of selected row IDs for bulk actions
  onSelectionChange?: (selectedIds: Set<number>) => void; // callback when selection changes
}


const minColWidth = 60;
const defaultColWidth = 120;

const EditableTable: React.FC<EditableTableProps> = ({ columns, rows, ignored, onIgnore, onEdit, onBatchEdit, recentlyChangedIds, duplicateIds, tableSx, cellSx, defaultVisibleColumns, storageKey, actionsRenderer, onConfirm, additionalButtons, onRowClick, selectedIds, onSelectionChange }) => {
  const theme = useTheme();
  const [editIdx, setEditIdx] = useState<number | null>(null);
  const [editRow, setEditRow] = useState<any>({});
  const [batchEditMode, setBatchEditMode] = useState(false);
  const [batchEditLoading, setBatchEditLoading] = useState(false);
  const [batchChanges, setBatchChanges] = useState<{[rowIdx: number]: any}>({});
  const [sortCol, setSortCol] = useState<string | null>('control_seq');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');
  const [colWidths, setColWidths] = useState<{[key:string]:number}>(() => {
    const base = Object.fromEntries(columns.map(c => [c.key, c.width ?? defaultColWidth]));
    return { ...base, __actions__: 80 };
  });
  const [filters, setFilters] = useState<{[key:string]:string}>(Object.fromEntries(columns.map(c => [c.key, ''])));
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const [visibleCols, setVisibleCols] = useState<Set<string>>(
    new Set(defaultVisibleColumns && defaultVisibleColumns.length > 0 ? defaultVisibleColumns : columns.map(c => c.key))
  );
  const [colOrder, setColOrder] = useState<string[]>(() => columns.map(c => c.key));
  const [dragColKey, setDragColKey] = useState<string | null>(null);

  // Load persisted prefs
  useEffect(() => {
    if (!storageKey) return;
    try {
      const raw = localStorage.getItem(`table_prefs:${storageKey}`);
      if (raw) {
        const obj = JSON.parse(raw);
        if (obj.colWidths && typeof obj.colWidths === 'object') setColWidths(obj.colWidths);
        if (obj.visibleCols && Array.isArray(obj.visibleCols)) setVisibleCols(new Set(obj.visibleCols));
        if (obj.colOrder && Array.isArray(obj.colOrder)) setColOrder(obj.colOrder);
        if (obj.sortCol !== undefined) setSortCol(obj.sortCol);
        if (obj.sortDir) setSortDir(obj.sortDir);
        if (obj.filters && typeof obj.filters === 'object') setFilters(obj.filters);
      }
    } catch {}
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey]);

  // Persist prefs on change
  useEffect(() => {
    if (!storageKey) return;
    try {
      localStorage.setItem(
        `table_prefs:${storageKey}`,
        JSON.stringify({ 
          colWidths, 
          visibleCols: Array.from(visibleCols), 
          colOrder, 
          sortCol, 
          sortDir, 
          filters 
        })
      );
    } catch {}
  }, [colWidths, visibleCols, colOrder, sortCol, sortDir, filters, storageKey]);

  // Update column widths when columns prop changes
  useEffect(() => {
    const base = Object.fromEntries(columns.map(c => [c.key, c.width ?? defaultColWidth]));
    setColWidths(prev => ({ __actions__: prev.__actions__ ?? 80, ...base }));
  }, [columns]);

  // Keep column order in sync with incoming columns while preserving user's prior order
  useEffect(() => {
    setColOrder(prev => {
      const incoming = columns.map(c => c.key);
      const kept = prev.filter(k => incoming.includes(k));
      const missing = incoming.filter(k => !kept.includes(k));
      return [...kept, ...missing];
    });
  }, [columns]);

  // Batch edit functions
  const handleBatchEditToggle = async () => {
    if (batchEditMode) {
      // Exiting batch mode - no loading needed
      setBatchChanges({});
      setBatchEditMode(false);
    } else {
      // Entering batch mode - show loading for large tables
      if (filteredRows.length > 50) {
        setBatchEditLoading(true);
      }
      setEditIdx(null);
      setEditRow({});
      
      // Use setTimeout to allow the loading indicator to render
      setTimeout(() => {
        setBatchEditMode(true);
        setBatchEditLoading(false);
      }, 50);
    }
  };

  const handleBatchSave = () => {
    if (onBatchEdit && Object.keys(batchChanges).length > 0) {
      // Pass filteredRows so parent can map sorted indices back to original array
      const sortedRows = [...rows].sort((a, b) => {
        if (!sortCol) return 0;
        const aVal = a[sortCol] ?? '';
        const bVal = b[sortCol] ?? '';
        if (aVal < bVal) return sortDir === 'asc' ? -1 : 1;
        if (aVal > bVal) return sortDir === 'asc' ? 1 : -1;
        return 0;
      });
      const filteredRows = sortedRows.filter(row =>
        columns.every(col => {
          if (!filters[col.key]) return true;
          
          // Use formatted value if format function exists, otherwise use raw value
          const displayValue = col.format 
            ? String(col.format(row[col.key], row) ?? '')
            : String(row[col.key] ?? '');
          
          return displayValue.toLowerCase().includes(filters[col.key].toLowerCase());
        })
      );
      onBatchEdit(batchChanges, filteredRows);
      setBatchChanges({});
      setBatchEditMode(false);
    }
  };

  const handleBatchCancel = () => {
    setBatchChanges({});
    setBatchEditMode(false);
  };

  const updateBatchChange = useCallback((rowIdx: number, field: string, value: any) => {
    // Normalize blank control_strength to null so backend updates to None
    const normalized = field === 'control_strength' && (value === '' || value === undefined) ? null : value;
    setBatchChanges(prev => ({
      ...prev,
      [rowIdx]: {
        ...prev[rowIdx],
        [field]: normalized
      }
    }));
  }, []);

  const getBatchValue = (rowIdx: number, field: string, originalValue: any) => {
    const value = batchChanges[rowIdx]?.[field] ?? originalValue;
    // Convert null/undefined to empty string for TextField
    if (value === null || value === undefined) {
      return "";
    }
    return value;
  };

  const getSingleEditValue = (field: string, editRowValue: any, originalValue: any) => {
    const value = editRowValue ?? originalValue ?? "";
    if (value === null && field === 'control_strength') {
      return "";
    }
    return value;
  };

  const handleColMenuOpen = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(event.currentTarget);
  };
  const handleColMenuClose = () => {
    setAnchorEl(null);
  };
  const handleColToggle = (colKey: string) => {
    setVisibleCols(prev => {
      const next = new Set(prev);
      if (next.has(colKey)) next.delete(colKey);
      else next.add(colKey);
      return next;
    });
  };

  // Sorting
  const sortedRows = [...rows].sort((a, b) => {
    if (!sortCol) return 0;
    const aVal = a[sortCol] ?? '';
    const bVal = b[sortCol] ?? '';
    if (aVal < bVal) return sortDir === 'asc' ? -1 : 1;
    if (aVal > bVal) return sortDir === 'asc' ? 1 : -1;
    return 0;
  });

  // Filtering
  const filteredRows = sortedRows.filter(row =>
    columns.every(col => {
      if (!filters[col.key]) return true;
      
      // Use formatted value if format function exists, otherwise use raw value
      const displayValue = col.format 
        ? String(col.format(row[col.key], row) ?? '')
        : String(row[col.key] ?? '');
      
      return displayValue.toLowerCase().includes(filters[col.key].toLowerCase());
    })
  );

  // Column resize handler
  const startResize = (colKey: string, e: React.MouseEvent) => {
    e.preventDefault();
    const startX = e.clientX;
    const startWidth = colWidths[colKey];
    const onMove = (moveEvent: MouseEvent) => {
      const delta = moveEvent.clientX - startX;
      setColWidths(w => ({ ...w, [colKey]: Math.max(minColWidth, startWidth + delta) }));
    };
    const onUp = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  const orderedColumns = [...columns].sort((a, b) => colOrder.indexOf(a.key) - colOrder.indexOf(b.key));
  const visibleColumns = orderedColumns.filter(col => visibleCols.has(col.key));

  // Drag & drop handlers for header reordering
  const onHeaderDragStart = (e: React.DragEvent, key: string) => {
    setDragColKey(key);
    try { e.dataTransfer.setData('text/plain', key); } catch {}
    e.dataTransfer.effectAllowed = 'move';
  };
  const onHeaderDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  };
  const onHeaderDrop = (e: React.DragEvent, targetKey: string) => {
    e.preventDefault();
    const sourceKey = dragColKey || (() => { try { return e.dataTransfer.getData('text/plain'); } catch { return ''; } })();
    if (!sourceKey || sourceKey === targetKey) return;
    setColOrder(prev => {
      const next = prev.filter(k => k !== sourceKey);
      const idx = next.indexOf(targetKey);
      if (idx === -1) return prev;
      next.splice(idx, 0, sourceKey);
      return [...next];
    });
    setDragColKey(null);
  };

  const isEditableCol = useCallback((colKey: string) => {
    const col = columns.find(c => c.key === colKey);
    return col?.editable !== false; // default true, unless explicitly false
  }, [columns]);

  return (
    <>
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 1, gap: 1 }}>
        {additionalButtons}
        <Button variant="outlined" size="small" onClick={handleColMenuOpen}>
          Select Columns
        </Button>
        <span style={{ fontSize: 10, color: batchEditMode ? 'blue' : 'gray' }}>
          {batchEditMode ? 'BATCH EDIT ACTIVE' : 'Normal Mode'}
        </span>
        <Menu anchorEl={anchorEl} open={Boolean(anchorEl)} onClose={handleColMenuClose}>
          {columns.map(col => (
            <MenuItem key={col.key} onClick={() => handleColToggle(col.key)}>
              <Checkbox checked={visibleCols.has(col.key)} />
              <ListItemText primary={col.label} />
            </MenuItem>
          ))}
        </Menu>
        {onBatchEdit ? (
          <>
            <Tooltip title={filteredRows.length > 100 ? "Warning: Large tables may cause performance issues in batch edit mode" : ""}>
              <Button 
                variant={batchEditMode ? "contained" : "outlined"} 
                size="small" 
                onClick={handleBatchEditToggle}
                {...(batchEditMode ? { color: "primary" } : {})}
              >
                {batchEditMode ? "Exit Batch Edit" : "Batch Edit"}
              </Button>
            </Tooltip>
            {batchEditMode && (
              <>
                <Button 
                  variant="contained" 
                  size="small" 
                  color="success" 
                  onClick={handleBatchSave}
                  disabled={Object.keys(batchChanges).length === 0}
                >
                  Save All ({Object.keys(batchChanges).length})
                </Button>
                <Button 
                  variant="outlined" 
                  size="small" 
                  color="secondary" 
                  onClick={handleBatchCancel}
                >
                  Cancel All
                </Button>
              </>
            )}
          </>
        ) : null}
      </Box>
      <TableContainer sx={{ fontSize: 10, p: 0, m: 0, mb: 1, overflowX: 'auto', maxHeight: '100%' }} className="content-text">
        <Table size="small" className="table-compact" stickyHeader sx={{ fontSize: 10, borderCollapse: 'collapse', tableLayout: 'fixed', width: '100%', ...tableSx }}>
          <colgroup>
            {onSelectionChange && <col key="__checkbox__" width={36} />}
            <col key="__actions__" width={colWidths.__actions__ || 80} />
            {visibleColumns.map(col => (
              <col key={col.key} width={colWidths[col.key] || defaultColWidth} />
            ))}
          </colgroup>
          <TableHead>
            <TableRow>
                {onSelectionChange && (
                  <TableCell sx={{ fontSize: 10, p: 0.25, border: `1px solid ${theme.palette.divider}`, background: theme.palette.mode === 'dark' ? theme.palette.grey[800] : '#f7f7f7', width: 36, maxWidth: 36, textAlign: 'center' }}>
                    <Checkbox
                      size="small"
                      sx={{ p: 0 }}
                      checked={filteredRows.length > 0 && selectedIds != null && filteredRows.every(r => selectedIds.has(r.id))}
                      indeterminate={selectedIds != null && selectedIds.size > 0 && !filteredRows.every(r => selectedIds.has(r.id))}
                      onChange={(e) => {
                        if (!onSelectionChange) return;
                        if (e.target.checked) {
                          const all = new Set(selectedIds);
                          filteredRows.forEach(r => { if (r.id != null) all.add(r.id); });
                          onSelectionChange(all);
                        } else {
                          const cleared = new Set(selectedIds);
                          filteredRows.forEach(r => cleared.delete(r.id));
                          onSelectionChange(cleared);
                        }
                      }}
                    />
                  </TableCell>
                )}
                <TableCell sx={{ fontSize: 10, p: 0.5, border: `1px solid ${theme.palette.divider}`, background: theme.palette.mode === 'dark' ? theme.palette.grey[800] : '#f7f7f7', minWidth: minColWidth, width: colWidths.__actions__, maxWidth: colWidths.__actions__, position: 'relative' }}>
                  <Box sx={{ display: 'flex', alignItems: 'center' }}>
                    <span>Actions</span>
                    <Box sx={{ flexGrow: 1 }} />
                  </Box>
                  <div
                    onMouseDown={e => { e.preventDefault(); e.stopPropagation(); startResize('__actions__', e as any); }}
                    style={{ position: 'absolute', top: 0, right: 0, width: 8, height: '100%', cursor: 'col-resize', zIndex: 5 }}
                  />
                </TableCell>
              {visibleColumns.map(col => (
                <TableCell
                  key={col.key}
                  sx={{
                    fontSize: 10,
                    p: 0.5,
                    border: `1px solid ${theme.palette.divider}`,
                     minWidth: minColWidth,
                     width: colWidths[col.key],
                     maxWidth: colWidths[col.key],
                    position: 'relative',
                    userSelect: 'none',
                    background: theme.palette.mode === 'dark' ? theme.palette.grey[800] : '#f7f7f7',
                    wordWrap: 'break-word',
                    overflowWrap: 'break-word',
                    whiteSpace: 'normal',
                    ...(cellSx || {}),
                    ...(col.key === 'control_seq' ? { position: 'sticky', top: 0, background: theme.palette.mode === 'dark' ? theme.palette.grey[800] : '#f5f7fa', zIndex: 2 } : {})
                  }}
                  onDragOver={onHeaderDragOver}
                  onDrop={e => onHeaderDrop(e, col.key)}
                >
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                    <span
                      title="Drag to reorder"
                      style={{ cursor: 'grab', width: 10, height: 18, display: 'inline-block', marginRight: 4 }}
                      draggable
                      onDragStart={e => onHeaderDragStart(e, col.key)}
                    />
                    <Tooltip title={col.label}>
                      <span>
                        <TableSortLabel
                          active={sortCol === col.key}
                          direction={sortCol === col.key ? sortDir : 'asc'}
                          onClick={() => {
                            if (sortCol === col.key) setSortDir(d => (d === 'asc' ? 'desc' : 'asc'));
                            else { setSortCol(col.key); setSortDir('asc'); }
                          }}
                        >
                          {col.label}
                        </TableSortLabel>
                      </span>
                    </Tooltip>
                    {col.headerInfo ? (
                      <Tooltip title={col.headerInfo} placement="top">
                        <InfoOutlinedIcon sx={{ fontSize: 12, color: '#607d8b' }} />
                      </Tooltip>
                    ) : null}
                    <Box sx={{ flexGrow: 1 }} />
                  </Box>
                  <div
                    onMouseDown={e => { e.preventDefault(); e.stopPropagation(); startResize(col.key, e as any); }}
                    style={{ position: 'absolute', top: 0, right: 0, width: 12, height: '100%', cursor: 'col-resize', zIndex: 5, borderRight: '2px solid rgba(0,0,0,0.05)' }}
                  />
                </TableCell>
              ))}
            </TableRow>
            {/* Filter row */}
            <TableRow>
              {onSelectionChange && (
                <TableCell sx={{ fontSize: 10, p: 0.25, border: `1px solid ${theme.palette.divider}`, width: 36, maxWidth: 36 }} />
              )}
              <TableCell sx={{ fontSize: 10, p: 0.5, border: `1px solid ${theme.palette.divider}`, width: colWidths.__actions__, maxWidth: colWidths.__actions__ }} />
              {visibleColumns.map(col => (
                <TableCell 
                  key={col.key} 
                  sx={{ 
                    fontSize: 10, 
                    p: 0.5, 
                    border: `1px solid ${theme.palette.divider}`, 
                    width: colWidths[col.key] || defaultColWidth,
                    maxWidth: 'none',
                    wordWrap: 'break-word',
                    overflowWrap: 'break-word',
                    ...(cellSx || {}) 
                  }}
                >
                  <TextField
                    value={filters[col.key]}
                    onChange={e => setFilters(f => ({ ...f, [col.key]: e.target.value }))}
                    size="small"
                    placeholder="Filter"
                    variant="standard"
                    InputProps={{ disableUnderline: true, style: { fontSize: 10, padding: 2 } }}
                    sx={{ width: '100%', maxWidth: '100%' }}
                  />
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {filteredRows.map((row, i) => (
              <TableRow 
                key={row.id ?? i}
                sx={{
                  ...(ignored.has(row.id ?? i) ? { opacity: 0.4, textDecoration: "line-through" } : {}),
                  ...(row?.is_duplicate_instance ? 
                    { backgroundColor: theme.palette.mode === 'dark' ? 'rgba(33, 150, 243, 0.2)' : 'rgba(33, 150, 243, 0.15)', borderLeft: '3px solid #2196f3' } : 
                    duplicateIds?.has(String(row.control_id)) ? 
                      { backgroundColor: theme.palette.mode === 'dark' ? '#663d00' : '#ffe4cc', borderLeft: '3px solid #ff9800' } : {}),
                  ...(row?.confidence === 0 || row?.cuec_confidence === 0 || row?.control_confidence === 0 ? 
                    { backgroundColor: theme.palette.mode === 'dark' ? '#665500' : '#fff3cd', borderLeft: '3px solid #ffc107' } : {}),
                  // Light purple highlight for controls with no mapped objectives
                  ...(row?.all_objectives && Array.isArray(row.all_objectives) && row.all_objectives.length === 0 ?
                    { backgroundColor: theme.palette.mode === 'dark' ? '#2d1b4e' : '#f3e5f5', borderLeft: '3px solid #9c27b0' } : {}),
                  ...(row?.has_deviation ? { backgroundColor: theme.palette.mode === 'dark' ? '#5c1a1a' : '#fdecea', borderLeft: '3px solid #f44336' } : {}),
                  ...(recentlyChangedIds?.has(row.id) ? 
                    { backgroundColor: theme.palette.mode === 'dark' ? '#1a4d2e' : '#d4edda', borderLeft: '3px solid #28a745', transition: 'background-color 0.3s ease' } : {})
                }}
              >
              {onSelectionChange && (
                <TableCell sx={{ fontSize: 10, p: 0.25, border: `1px solid ${theme.palette.divider}`, width: 36, maxWidth: 36, textAlign: 'center' }}>
                  <Checkbox
                    size="small"
                    sx={{ p: 0 }}
                    checked={selectedIds?.has(row.id) ?? false}
                    onClick={(e) => e.stopPropagation()}
                    onChange={() => {
                      if (!onSelectionChange || row.id == null) return;
                      const next = new Set(selectedIds);
                      if (next.has(row.id)) next.delete(row.id); else next.add(row.id);
                      onSelectionChange(next);
                    }}
                  />
                </TableCell>
              )}
              <TableCell sx={{ fontSize: 10, p: 0.5, border: `1px solid ${theme.palette.divider}`, width: colWidths.__actions__, maxWidth: colWidths.__actions__ }}>
                <Box sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '2px' }}>
                  {batchEditMode ? (
                    <Button size="small" color={ignored.has(row.id ?? i) ? "secondary" : "error"} onClick={(e) => { e.stopPropagation(); onIgnore(i); }} sx={{ fontSize: 9, minWidth: 0, px: 0.5, py: 0.25 }}>
                      {ignored.has(row.id ?? i) ? "Unign" : "Ign"}
                    </Button>
                  ) : editIdx === i ? (
                    <>
                      <IconButton onClick={(e) => { e.stopPropagation(); onEdit(i, editRow); setEditIdx(null); }} size="small" sx={{ p: 0.25 }}><SaveIcon sx={{ fontSize: 16 }} /></IconButton>
                      <IconButton onClick={(e) => { e.stopPropagation(); setEditIdx(null); }} size="small" sx={{ p: 0.25 }}><CancelIcon sx={{ fontSize: 16 }} /></IconButton>
                    </>
                  ) : (
                    <>
                      <IconButton onClick={(e) => { e.stopPropagation(); setEditIdx(i); setEditRow(row); }} size="small" sx={{ p: 0.25 }}><EditIcon sx={{ fontSize: 16 }} /></IconButton>
                      {actionsRenderer ? actionsRenderer(row, i) : null}
                      <Button size="small" color={ignored.has(row.id ?? i) ? "secondary" : "error"} onClick={(e) => { e.stopPropagation(); onIgnore(row); }} sx={{ fontSize: 9, minWidth: 0, px: 0.5, py: 0.25 }}>
                        {ignored.has(row.id ?? i) ? "Unign" : "Ign"}
                      </Button>
                      {onConfirm && (
                        <Button size="small" color="success" onClick={(e) => { e.stopPropagation(); onConfirm(row); }} sx={{ fontSize: 9, minWidth: 0, px: 0.5, py: 0.25 }}>
                          ✓
                        </Button>
                      )}
                    </>
                  )}
                </Box>
                </TableCell>
                {visibleColumns.map(col => {
                  const isEditing = (batchEditMode || editIdx === i) && isEditableCol(col.key);
                  const isDescriptionColumn = col.key === 'control_desc' || col.key === 'cuec_description' || col.key === 'third_party_description' || col.key === 'objective_text';
                  return (
                    <TableCell 
                      key={col.key} 
                      onClick={isDescriptionColumn ? () => onRowClick?.(row) : undefined}
                      sx={{ 
                        fontSize: 10, 
                        p: isEditing ? 0.25 : 0.5, 
                        border: `1px solid ${theme.palette.divider}`, 
                        width: colWidths[col.key] || defaultColWidth,
                        maxWidth: 'none',
                        wordWrap: 'break-word',
                        overflowWrap: 'break-word',
                        whiteSpace: 'normal',
                        ...(cellSx || {}),
                        ...((col as any).cellSx || {}),
                        ...(isDescriptionColumn && onRowClick ? { cursor: 'pointer', '&:hover': { backgroundColor: theme.palette.action.hover } } : {})
                      }}
                    >
                      {isEditing ? (
                        col.key === 'control_strength' ? (
                          <FormControl size="small" fullWidth>
                            <Select
                              value={batchEditMode ? 
                                getBatchValue(i, col.key, row[col.key]) : 
                                getSingleEditValue(col.key, editRow[col.key], row[col.key])
                              }
                              onChange={e => batchEditMode ? 
                                updateBatchChange(i, col.key, e.target.value) : 
                                setEditRow({ ...editRow, [col.key]: e.target.value })
                              }
                              size="small"
                              sx={{ fontSize: 10 }}
                            >
                              <MenuItem value="">Not Set</MenuItem>
                              <MenuItem value="High">High</MenuItem>
                              <MenuItem value="Medium">Medium</MenuItem>
                              <MenuItem value="Low">Low</MenuItem>
                            </Select>
                          </FormControl>
                        ) : (
                          <TextField
                            value={String(batchEditMode ? getBatchValue(i, col.key, row[col.key]) : (editRow[col.key] ?? row[col.key] ?? ""))}
                            onChange={e => batchEditMode ? 
                              updateBatchChange(i, col.key, e.target.value) : 
                              setEditRow({ ...editRow, [col.key]: e.target.value })
                            }
                            size="small"
                            fullWidth
                            multiline
                            minRows={1}
                            maxRows={6}
                            InputProps={{ 
                              style: { 
                                fontSize: 10, 
                                padding: '4px 6px'
                              } 
                            }}
                            sx={{
                              '& .MuiInputBase-root': {
                                padding: 0
                              },
                              '& .MuiInputBase-input': {
                                padding: '4px 6px'
                              }
                            }}
                          />
                        )
                      ) : (
                        <div style={{ 
                          wordWrap: 'break-word', 
                          overflowWrap: 'break-word', 
                          whiteSpace: ((col as any).cellSx?.whiteSpace) || 'normal',
                          maxWidth: '100%'
                        }}>
                          {col.key === 'control_id' && row._instance_badge ? (
                            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
                              <span>{(col as any).render ? (col as any).render(row) : (col.format ? col.format(row[col.key]) : row[col.key])}</span>
                              {row._instance_badge}
                            </Box>
                          ) : (
                            (col as any).render ? (col as any).render(row) : (col.format ? col.format(row[col.key]) : row[col.key])
                          )}
                        </div>
                      )}
                    </TableCell>
                  );
                })}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
      
      {/* Loading backdrop for batch edit mode */}
      <Backdrop
        sx={{ 
          color: '#fff', 
          zIndex: (theme) => theme.zIndex.drawer + 1,
          position: 'absolute',
          backgroundColor: 'rgba(0, 0, 0, 0.7)'
        }}
        open={batchEditLoading}
      >
        <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
          <CircularProgress color="inherit" size={60} />
          <Box sx={{ fontSize: 16, fontWeight: 500 }}>
            Preparing {filteredRows.length} rows for batch editing...
          </Box>
        </Box>
      </Backdrop>
    </>
  );
};

export default EditableTable;
