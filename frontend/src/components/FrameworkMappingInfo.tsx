import React, { useState } from 'react';
import { Tooltip, Box, Typography, Popper, Paper, ClickAwayListener } from '@mui/material';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import WarningIcon from '@mui/icons-material/Warning';

interface FrameworkMatch {
  id: string;
  confidence: number;
  reasoning?: string;
  deviation?: string | null;
}

interface FrameworkMappingInfoProps {
  mappings: FrameworkMatch[];
  type: 'tsc' | 'coso';
  controlId?: string;
  onOpenConfidenceModal?: (control: any) => void;
  control?: any;
}

/**
 * Compact info icon with minimal tooltip showing multi-match framework mappings.
 * Displays count, top 3 IDs with percentages, and exception badge if any deviations exist.
 * Tooltip limited to ~6 lines max. Click row for full details.
 */
export const FrameworkMappingInfo: React.FC<FrameworkMappingInfoProps> = ({ 
  mappings, 
  type, 
  controlId,
  onOpenConfidenceModal,
  control
}) => {
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);
  const open = Boolean(anchorEl);

  if (!mappings || mappings.length === 0) {
    return null;
  }

  const handleClick = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorEl(anchorEl ? null : event.currentTarget);
  };

  const handleClose = () => {
    setAnchorEl(null);
  };

  const handleMappingClick = () => {
    if (onOpenConfidenceModal && control) {
      onOpenConfidenceModal(control);
      setAnchorEl(null); // Close the popper after opening modal
    }
  };

  const hasDeviations = mappings.some(m => m.deviation != null && m.deviation !== '');
  const frameworkLabel = type.toUpperCase();
  
  // Take top 3 mappings
  const topMappings = mappings.slice(0, 3);
  
  const tooltipContent = (
    <Box sx={{ maxWidth: 400, fontSize: 11 }}>
      <Typography variant="caption" sx={{ fontWeight: 700, display: 'block', mb: 1, fontSize: 12 }}>
        {frameworkLabel} Multi-Match Mappings
      </Typography>
      <Box sx={{ mb: 0.5 }}>
        <Typography variant="caption" sx={{ fontSize: 10, color: '#ccc' }}>
          Total: {mappings.length} match{mappings.length !== 1 ? 'es' : ''} | 
          {controlId && ` Control: ${controlId}`}
        </Typography>
      </Box>
      {topMappings.map((match, idx) => (
        <Box 
          key={idx} 
          onClick={handleMappingClick}
          sx={{ 
            mb: 0.8, 
            pl: 1, 
            borderLeft: '2px solid #1976d2',
            cursor: onOpenConfidenceModal ? 'pointer' : 'default',
            '&:hover': onOpenConfidenceModal ? {
              backgroundColor: 'rgba(25, 118, 210, 0.1)',
              borderRadius: '4px'
            } : {}
          }}
        >
          <Typography variant="caption" sx={{ fontSize: 11, fontWeight: 600 }}>
            {idx + 1}. {match.id} 
            <Box component="span" sx={{ color: '#4caf50', ml: 0.5, fontWeight: 700 }}>
              {Math.round(match.confidence * 100)}%
            </Box>
            {match.deviation && (
              <Box component="span" sx={{ color: '#ff9800', ml: 0.5, fontWeight: 600 }}>
                ⚠ Exception
              </Box>
            )}
          </Typography>
          {match.reasoning && (
            <Typography variant="caption" sx={{ fontSize: 10, color: '#ddd', display: 'block', mt: 0.2 }}>
              {match.reasoning.substring(0, 80)}{match.reasoning.length > 80 ? '...' : ''}
            </Typography>
          )}
          {match.deviation && (
            <Typography variant="caption" sx={{ fontSize: 10, color: '#ffb74d', display: 'block', mt: 0.2, fontStyle: 'italic' }}>
              Deviation: {match.deviation.substring(0, 60)}{match.deviation.length > 60 ? '...' : ''}
            </Typography>
          )}
        </Box>
      ))}
      {mappings.length > 3 && (
        <Typography variant="caption" sx={{ fontSize: 10, fontStyle: 'italic', color: '#999', mt: 0.5, display: 'block' }}>
          +{mappings.length - 3} more mapping{mappings.length - 3 !== 1 ? 's' : ''}
        </Typography>
      )}
      <Box sx={{ mt: 1, pt: 0.5, borderTop: '1px solid #444' }}>
        <Typography variant="caption" sx={{ fontSize: 9, fontStyle: 'italic', color: '#888' }}>
          💡 Click row to open full confidence modal
        </Typography>
      </Box>
    </Box>
  );

  return (
    <>
      <Box 
        onClick={handleClick}
        sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.5, cursor: 'pointer' }}
      >
        <InfoOutlinedIcon sx={{ fontSize: 14, color: open ? '#1976d2' : '#1976d2' }} />
        {hasDeviations && (
          <WarningIcon sx={{ fontSize: 12, color: '#ff9800' }} />
        )}
        {mappings.length > 1 && (
          <Box component="span" sx={{ fontSize: 9, color: '#666', fontWeight: 600 }}>
            ×{mappings.length}
          </Box>
        )}
      </Box>
      <Popper 
        open={open} 
        anchorEl={anchorEl} 
        placement="top"
        sx={{ zIndex: 1500 }}
      >
        <ClickAwayListener onClickAway={handleClose}>
          <Paper sx={{ 
            p: 2, 
            maxWidth: 400, 
            backgroundColor: '#2c2c2c',
            color: '#fff'
          }}>
            {tooltipContent}
          </Paper>
        </ClickAwayListener>
      </Popper>
    </>
  );
};

export default FrameworkMappingInfo;
