import React, { useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Paper, Typography, Box, TextField, Select, MenuItem, FormControl, InputLabel, CircularProgress } from '@mui/material';
import { VirtualHistoryGrid } from '../index';

interface ScanResult {
  id: number | string;
  timestamp: string;
  filename: string;
  results: any;
}

interface HistorySectionProps {
  history: ScanResult[];
  historyLoading: boolean;
  searchQuery: string;
  reportTypeFilter: string;
  onSearchChange: (query: string) => void;
  onFilterChange: (filter: string) => void;
  onDeleteScan: (scanId: number | string) => void;
}

const HistorySection: React.FC<HistorySectionProps> = ({
  history,
  historyLoading,
  searchQuery,
  reportTypeFilter,
  onSearchChange,
  onFilterChange,
  onDeleteScan
}) => {
  const navigate = useNavigate();

  // Memoize filtered history
  const filteredHistory = useMemo(() => {
    return history.filter(scan => {
      // Search filter
      const searchLower = searchQuery.toLowerCase();
      const matchesSearch = !searchQuery || 
        scan.filename?.toLowerCase().includes(searchLower) ||
        (scan as any).company?.toLowerCase().includes(searchLower);
      
      // Report type filter
      const matchesType = reportTypeFilter === 'All' || 
        (scan.results as any)?.report_type === reportTypeFilter;
      
      return matchesSearch && matchesType;
    });
  }, [history, searchQuery, reportTypeFilter]);

  // Memoize callbacks
  const handleScanClick = useCallback((scanId: number | string) => {
    navigate(`/app/report/${scanId}`);
  }, [navigate]);

  return (
    <Paper sx={{ p: 1.5, mt: 1.5, mb: 1.5 }}>
      <Typography variant="h6" sx={{ mb: 1, fontSize: '1.1rem' }}>
        Scan History
      </Typography>
      
      {/* Search and Filter Controls */}
      <Box sx={{ display: 'flex', gap: 1.5, mb: 1 }}>
        <TextField
          label="Search by filename"
          variant="outlined"
          size="small"
          value={searchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          sx={{ flexGrow: 1 }}
        />
        <FormControl size="small" sx={{ minWidth: 150 }}>
          <InputLabel>Report Type</InputLabel>
          <Select
            value={reportTypeFilter}
            label="Report Type"
            onChange={(e) => onFilterChange(e.target.value)}
          >
            <MenuItem value="All">All Types</MenuItem>
            <MenuItem value="SOC 1">SOC 1</MenuItem>
            <MenuItem value="SOC 2">SOC 2</MenuItem>
          </Select>
        </FormControl>
      </Box>

      {historyLoading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
          <CircularProgress />
        </Box>
      ) : (
        <VirtualHistoryGrid
          scans={filteredHistory}
          onScanClick={handleScanClick}
          onDeleteScan={onDeleteScan}
        />
      )}
    </Paper>
  );
};

// Memoize the entire component - only re-render when these props change
export default React.memo(HistorySection, (prevProps, nextProps) => {
  return (
    prevProps.history === nextProps.history &&
    prevProps.historyLoading === nextProps.historyLoading &&
    prevProps.searchQuery === nextProps.searchQuery &&
    prevProps.reportTypeFilter === nextProps.reportTypeFilter &&
    prevProps.onSearchChange === nextProps.onSearchChange &&
    prevProps.onFilterChange === nextProps.onFilterChange &&
    prevProps.onDeleteScan === nextProps.onDeleteScan
  );
});
