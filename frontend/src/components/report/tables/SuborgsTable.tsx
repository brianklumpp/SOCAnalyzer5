/**
 * SuborgsTable Component
 * 
 * Displays subservice organizations with duplicate detection and highlighting.
 * Wraps EditableTable with custom duplicate name handling logic.
 */

import React, { useMemo } from 'react';
import EditableTable from '../../EditableTable';
import { subserviceOrgColumns, defaultVisibleSubOrgColumns } from '../../../config/report/columnDefinitions';
import { computeHighConfNameCounts } from '../../../services/report/dataTransformations';

interface SuborgsTableProps {
  subOrgs: any[];
  ignored: Set<number>;
  recentlyChangedIds: Set<number>;
  onIgnore: (row: any) => void;
  onConfirm: (row: any) => void;
  onEdit: (row: any, idx: number) => void;
  onBatchEdit: (changes: { [rowIdx: number]: any }, rows: any[]) => void;
  additionalButtons?: React.ReactNode;
  onRowClick?: (row: any) => void;
}

export const SuborgsTable = React.memo(function SuborgsTable({
  subOrgs,
  ignored,
  recentlyChangedIds,
  onIgnore,
  onConfirm,
  onEdit,
  onBatchEdit,
  additionalButtons,
  onRowClick
}: SuborgsTableProps) {
  // Detect duplicate names for highlighting
  const duplicateNames = useMemo(() => {
    const nameCounts = computeHighConfNameCounts(subOrgs);
    const duplicates = new Set<string>();
    nameCounts.forEach((count, name) => {
      if (count > 1) {
        duplicates.add(name);
      }
    });
    return duplicates;
  }, [subOrgs]);

  // No preprocessing needed - column definitions handle formatting
  const processedSubOrgs = subOrgs;

  return (
    <EditableTable
      columns={subserviceOrgColumns}
      rows={processedSubOrgs}
      ignored={ignored}
      onIgnore={(rowOrIdx: any) => {
        const row = typeof rowOrIdx === 'number' ? processedSubOrgs[rowOrIdx] : rowOrIdx;
        const origRow = subOrgs.find(r => r.id === row.id) || row;
        onIgnore(origRow);
      }}
      onConfirm={(row) => onConfirm(row)}
      onEdit={(rowIdxOrRow: any, newRow: any) => {
        const originalRow = typeof rowIdxOrRow === 'number' ? processedSubOrgs[rowIdxOrRow] : processedSubOrgs.find((r: any) => r.id === newRow.id);
        const mergedRow = { ...originalRow, ...newRow };
        const origIdx = subOrgs.findIndex(r => r.id === mergedRow.id);
        onEdit(mergedRow, origIdx >= 0 ? origIdx : rowIdxOrRow);
      }}
      onBatchEdit={(changes) => onBatchEdit(changes, subOrgs)}
      recentlyChangedIds={recentlyChangedIds}
      duplicateIds={duplicateNames}
      cellSx={{ 
        whiteSpace: 'pre-line', 
        overflow: 'visible', 
        textOverflow: 'clip', 
        wordBreak: 'break-word', 
        padding: '4px 6px', 
        fontSize: 12 
      }}
      defaultVisibleColumns={defaultVisibleSubOrgColumns}
      storageKey="report_suborgs"
      additionalButtons={additionalButtons}
      onRowClick={onRowClick}
    />
  );
});
