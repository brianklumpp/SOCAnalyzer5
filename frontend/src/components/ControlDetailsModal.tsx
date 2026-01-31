import React from 'react';
import { Dialog, DialogTitle, DialogContent, DialogActions, Button, Typography, Box } from '@mui/material';

interface ControlDetailsModalProps {
  open: boolean;
  control: any;
  onClose: () => void;
  onConvertToObjective?: (control: any) => void;
}

const ControlDetailsModal: React.FC<ControlDetailsModalProps> = ({
  open,
  control,
  onClose,
  onConvertToObjective
}) => {
  if (!control) return null;

  const formatField = (value: any): string => {
    if (!value) return 'N/A';
    if (Array.isArray(value)) {
      return value.length > 0 ? value.join('\n• ') : 'N/A';
    }
    return String(value);
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>Control Details</DialogTitle>
      <DialogContent>
        <Box sx={{ mb: 1.5 }}>
          <Typography variant="subtitle2" color="textSecondary" sx={{ fontSize: '11px', fontWeight: 600, mb: 0.5 }}>
            Control ID
          </Typography>
          <Typography sx={{ fontSize: '12px' }}>{control.control_id || 'N/A'}</Typography>
        </Box>

        <Box sx={{ mb: 1.5 }}>
          <Typography variant="subtitle2" color="textSecondary" sx={{ fontSize: '11px', fontWeight: 600, mb: 0.5 }}>
            Description
          </Typography>
          <Typography sx={{ fontSize: '11px', lineHeight: 1.5 }}>
            {formatField(control.control_desc)}
          </Typography>
        </Box>

        <Box sx={{ mb: 1.5 }}>
          <Typography variant="subtitle2" color="textSecondary" sx={{ fontSize: '11px', fontWeight: 600, mb: 0.5 }}>
            Test Procedure
          </Typography>
          <Typography sx={{ fontSize: '11px', lineHeight: 1.5 }}>
            {formatField(control.control_test)}
          </Typography>
        </Box>

        {control.has_deviation && control.deviation_desc && (
          <Box sx={{ mb: 1.5 }}>
            <Typography variant="subtitle2" color="textSecondary" sx={{ fontSize: '11px', fontWeight: 600, mb: 0.5 }}>
              Deviation Summary
            </Typography>
            <Typography sx={{ fontSize: '11px', lineHeight: 1.5, color: 'error.main' }}>
              {formatField(control.deviation_desc)}
            </Typography>
          </Box>
        )}

        <Box sx={{ mb: 1.5 }}>
          <Typography variant="subtitle2" color="textSecondary" sx={{ fontSize: '11px', fontWeight: 600, mb: 0.5 }}>
            Page Reference
          </Typography>
          <Typography sx={{ fontSize: '11px' }}>
            {control.control_page_ref ? `Page ${control.control_page_ref}` : 'N/A'}
          </Typography>
        </Box>

      </DialogContent>
      <DialogActions>
        {onConvertToObjective && (
          <Button
            variant="outlined"
            onClick={() => onConvertToObjective(control)}
          >
            Convert to Objective
          </Button>
        )}
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
};

export default ControlDetailsModal;
