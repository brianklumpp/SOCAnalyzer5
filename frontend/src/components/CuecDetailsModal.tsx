import React from 'react';
import { Dialog, DialogTitle, DialogContent, DialogActions, Button, Typography, Box } from '@mui/material';

interface CuecDetailsModalProps {
  open: boolean;
  cuec: any;
  onClose: () => void;
}

const CuecDetailsModal: React.FC<CuecDetailsModalProps> = ({ open, cuec, onClose }) => {
  if (!cuec) return null;

  // Helper to safely parse framework mappings
  const parseFrameworkMappings = (mappings: any) => {
    if (!mappings) return { TSC: [], COSO: [] };
    
    if (typeof mappings === 'string') {
      try {
        return JSON.parse(mappings);
      } catch {
        return { TSC: [], COSO: [] };
      }
    }
    return mappings;
  };

  const frameworkMappings = parseFrameworkMappings(cuec.framework_mappings);
  const tscMappings = frameworkMappings.TSC || [];
  const cosoMappings = frameworkMappings.COSO || [];

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>CUEC Details</DialogTitle>
      <DialogContent>
        <Box sx={{ mb: 2 }}>
          <Typography variant="subtitle2" color="textSecondary">CUEC ID</Typography>
          <Typography>{cuec.cuec_id || `CUEC ${cuec.id}`}</Typography>
        </Box>
        <Box sx={{ mb: 2 }}>
          <Typography variant="subtitle2" color="textSecondary">Description</Typography>
          <Typography>{cuec.cuec_description || 'No description available'}</Typography>
        </Box>
        {tscMappings && tscMappings.length > 0 && (
          <Box sx={{ mb: 2 }}>
            <Typography variant="subtitle2" color="textSecondary">TSC Mappings</Typography>
            {tscMappings.map((mapping: any, idx: number) => (
              <Typography key={idx}>
                • {mapping.id} (Confidence: {(mapping.confidence * 100).toFixed(1)}%)
                {mapping.reasoning && ` - ${mapping.reasoning}`}
              </Typography>
            ))}
          </Box>
        )}
        {cosoMappings && cosoMappings.length > 0 && (
          <Box sx={{ mb: 2 }}>
            <Typography variant="subtitle2" color="textSecondary">COSO Mappings</Typography>
            {cosoMappings.map((mapping: any, idx: number) => (
              <Typography key={idx}>
                • {mapping.id} (Confidence: {(mapping.confidence * 100).toFixed(1)}%)
                {mapping.reasoning && ` - ${mapping.reasoning}`}
              </Typography>
            ))}
          </Box>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
};

export default CuecDetailsModal;
