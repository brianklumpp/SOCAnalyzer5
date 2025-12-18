/**
 * VirtualHistoryGrid Component
 * 
 * High-performance virtualized grid for displaying scan history cards.
 * Uses react-virtualized for efficient rendering of large datasets.
 * Responsive design with automatic column adjustment based on viewport width.
 */

import React, { useMemo } from 'react';
import { Grid, AutoSizer, GridCellProps } from 'react-virtualized';
import { Box, Typography } from '@mui/material';
import { History as HistoryIcon } from '@mui/icons-material';
import HistoryCard, { ScanData } from './HistoryCard';
import { solidigmColors } from '../theme/solidigmTheme';

interface VirtualHistoryGridProps {
  scans: ScanData[];
  onScanClick?: (scanId: number | string) => void;
  onDeleteScan?: (scanId: number | string) => void;
  containerWidth?: number;
  containerHeight?: number;
}

// Grid spacing and sizing - Fixed 2 columns
const GRID_CONFIG = {
  CARD_HEIGHT: 260,
  HORIZONTAL_SPACING: 24,
  VERTICAL_SPACING: 24,
  PADDING: 16,
  COLUMN_COUNT: 2,  // Fixed to 2 columns
};

/**
 * Calculate cell width based on container width (fixed 2 columns)
 */
const calculateCellWidth = (containerWidth: number): number => {
  const columnCount = GRID_CONFIG.COLUMN_COUNT;
  const totalSpacing = GRID_CONFIG.HORIZONTAL_SPACING * (columnCount + 1);
  const availableWidth = containerWidth - totalSpacing;
  return Math.floor(availableWidth / columnCount);
};

/**
 * Calculate cell height including vertical spacing
 */
const calculateCellHeight = (): number => {
  return GRID_CONFIG.CARD_HEIGHT + GRID_CONFIG.VERTICAL_SPACING;
};

/**
 * Empty State Component
 */
const EmptyState: React.FC = () => (
  <Box
    sx={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      height: '100%',
      gap: 2,
      color: solidigmColors.mediumGray,
    }}
  >
    <HistoryIcon sx={{ fontSize: 64, color: solidigmColors.lightGray }} />
    <Typography variant="h5" sx={{ fontWeight: 500 }}>
      No Scan History
    </Typography>
    <Typography variant="body2" sx={{ maxWidth: 400, textAlign: 'center' }}>
      Your scan history will appear here once you've uploaded and analyzed reports.
    </Typography>
  </Box>
);

/**
 * VirtualHistoryGrid Component
 */
export const VirtualHistoryGrid: React.FC<VirtualHistoryGridProps> = ({
  scans,
  onScanClick,
  onDeleteScan,
  containerWidth: propWidth,
  containerHeight: propHeight,
}) => {
  // Show empty state if no scans
  if (!scans || scans.length === 0) {
    return <EmptyState />;
  }

  /**
   * Cell renderer for react-virtualized Grid
   */
  const cellRenderer = (
    cellWidth: number,
    cellHeight: number
  ) => ({ columnIndex, key, rowIndex, style }: GridCellProps): React.ReactNode => {
    const columnCount = GRID_CONFIG.COLUMN_COUNT;
    const scanIndex = rowIndex * columnCount + columnIndex;
    
    // Return empty cell if beyond scan array bounds
    if (scanIndex >= scans.length) {
      return <div key={key} style={style} />;
    }

    const scan = scans[scanIndex];

    return (
      <div
        key={key}
        style={{
          ...style,
          padding: `${GRID_CONFIG.VERTICAL_SPACING / 2}px ${GRID_CONFIG.HORIZONTAL_SPACING / 2}px`,
        }}
      >
        <HistoryCard 
          scan={scan} 
          onDelete={onDeleteScan}
        />
      </div>
    );
  };

  /**
   * Grid component with AutoSizer for responsive sizing
   */
  const GridComponent: React.FC<{ width: number; height: number }> = ({
    width,
    height,
  }) => {
    const columnCount = GRID_CONFIG.COLUMN_COUNT;
    const cellWidth = useMemo(
      () => calculateCellWidth(width),
      [width]
    );
    const cellHeight = useMemo(() => calculateCellHeight(), []);
    const rowCount = useMemo(
      () => Math.ceil(scans.length / columnCount),
      []
    );

    return (
      <Grid
        cellRenderer={cellRenderer(cellWidth, cellHeight)}
        columnCount={columnCount}
        columnWidth={cellWidth}
        height={height}
        rowCount={rowCount}
        rowHeight={cellHeight}
        width={width}
        style={{
          outline: 'none',
        }}
        overscanRowCount={2}
      />
    );
  };

  // If explicit dimensions provided, use them directly
  if (propWidth && propHeight) {
    return (
      <Box sx={{ width: propWidth, height: propHeight }}>
        <GridComponent width={propWidth} height={propHeight} />
      </Box>
    );
  }

  // Otherwise, use AutoSizer for automatic container sizing
  return (
    <Box
      sx={{
        width: '100%',
        height: '100%',
        minHeight: 400,
      }}
    >
      <AutoSizer>
        {({ width, height }) => <GridComponent width={width} height={height} />}
      </AutoSizer>
    </Box>
  );
};

export default VirtualHistoryGrid;
