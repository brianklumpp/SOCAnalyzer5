import React, { useState, useEffect } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  TextField,
  Box,
  Typography,
  CircularProgress,
  Alert,
} from '@mui/material';
import api from '../../api/client';

interface ManualExtractionDialogProps {
  open: boolean;
  onClose: () => void;
  scanId: number;
  entityType: 'cuec' | 'subservice_org';
  onSuccess: () => void;
}

interface ExtractionResult {
  new_count: number;
  updated_count: number;
  invalidated_count: number;
  items: any[];
}

export const ManualExtractionDialog: React.FC<ManualExtractionDialogProps> = ({
  open,
  onClose,
  scanId,
  entityType,
  onSuccess,
}) => {
  const [pages, setPages] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ExtractionResult | null>(null);

  const entityLabel = entityType === 'cuec' ? 'CUECs' : 'Subservice Organizations';

  const handleClose = () => {
    if (!loading) {
      setPages('');
      setError(null);
      setResult(null);
      onClose();
    }
  };

  const validatePages = (input: string): boolean => {
    // Allow digits, commas, spaces, and hyphens
    const regex = /^[\d,\s-]+$/;
    return regex.test(input.trim());
  };

  const parsePagePreview = (input: string): number[] => {
    try {
      const pages: number[] = [];
      const parts = input.split(',');
      
      for (const part of parts) {
        const trimmed = part.trim();
        if (trimmed.includes('-')) {
          const [start, end] = trimmed.split('-').map(x => parseInt(x.trim()));
          if (isNaN(start) || isNaN(end) || start > end) {
            throw new Error('Invalid range');
          }
          for (let i = start; i <= end; i++) {
            if (!pages.includes(i)) {
              pages.push(i);
            }
          }
        } else {
          const page = parseInt(trimmed);
          if (isNaN(page)) {
            throw new Error('Invalid page number');
          }
          if (!pages.includes(page)) {
            pages.push(page);
          }
        }
      }
      
      return pages.sort((a, b) => a - b);
    } catch {
      return [];
    }
  };

  const handleExtract = async () => {
    if (!pages.trim()) {
      setError('Please enter page numbers');
      return;
    }

    if (!validatePages(pages)) {
      setError('Invalid format. Use numbers, commas, and hyphens (e.g., 5, 7-9, 12)');
      return;
    }

    const pageList = parsePagePreview(pages);
    if (pageList.length === 0) {
      setError('No valid page numbers found');
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await api.post(`/report/${scanId}/manual-extract`, {
        entity_type: entityType,
        pages: pages.trim(),
      }, {
        timeout: 300000 // 5 minutes for GPT processing
      });

      setResult(response.data);
      
      // TEMPORARILY DISABLED for debugging - keep dialog open
      // setTimeout(() => {
      //   onSuccess();
      //   handleClose();
      // }, 2000);
    } catch (err: any) {
      console.error('[ManualExtract] Error:', err);
      console.error('[ManualExtract] Error response:', err.response);
      setError(err.response?.data?.detail || 'Failed to extract items. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const pagePreview = pages.trim() ? parsePagePreview(pages) : [];
  const isValidInput = pages.trim() && validatePages(pages) && pagePreview.length > 0;

  return (
    <Dialog open={open} onClose={handleClose} maxWidth="sm" fullWidth>
      <DialogTitle>Manual Extract {entityLabel}</DialogTitle>
      <DialogContent>
        <Box sx={{ pt: 1 }}>
          <Typography variant="body2" color="text.secondary" gutterBottom>
            Extract {entityLabel.toLowerCase()} from specific pages of the PDF. This will:
          </Typography>
          <Box component="ul" sx={{ mt: 1, mb: 2, pl: 3 }}>
            <Typography component="li" variant="body2" color="text.secondary">
              Extract items from the specified pages
            </Typography>
            <Typography component="li" variant="body2" color="text.secondary">
              Boost confidence of matching items by +0.2
            </Typography>
            <Typography component="li" variant="body2" color="text.secondary">
              Invalidate high-confidence items NOT on these pages
            </Typography>
          </Box>

          <TextField
            fullWidth
            label="Page Numbers"
            placeholder="e.g., 5, 7-9, 12"
            value={pages}
            onChange={(e) => setPages(e.target.value)}
            disabled={loading}
            helperText="Enter page numbers separated by commas. Use hyphens for ranges."
            error={!!error && !loading}
          />

          {isValidInput && (
            <Box sx={{ mt: 2, p: 2, bgcolor: 'action.hover', borderRadius: 1 }}>
              <Typography variant="body2" color="text.secondary">
                Will extract from <strong>{pagePreview.length} page{pagePreview.length !== 1 ? 's' : ''}</strong>:{' '}
                {pagePreview.slice(0, 10).join(', ')}
                {pagePreview.length > 10 && ` ... and ${pagePreview.length - 10} more`}
              </Typography>
            </Box>
          )}

          {error && !loading && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {error}
            </Alert>
          )}

          {result && (
            <Alert severity="success" sx={{ mt: 2 }}>
              <Typography variant="body2">
                <strong>Extraction Complete:</strong>
              </Typography>
              <Typography variant="body2">
                • {result.new_count} new item{result.new_count !== 1 ? 's' : ''} added
              </Typography>
              <Typography variant="body2">
                • {result.updated_count} item{result.updated_count !== 1 ? 's' : ''} updated (confidence boosted)
              </Typography>
              <Typography variant="body2">
                • {result.invalidated_count} item{result.invalidated_count !== 1 ? 's' : ''} invalidated
              </Typography>
            </Alert>
          )}

          {loading && (
            <Box sx={{ display: 'flex', justifyContent: 'center', mt: 3 }}>
              <CircularProgress />
            </Box>
          )}
        </Box>
      </DialogContent>
      <DialogActions>
        {result ? (
          <Button 
            onClick={() => {
              onSuccess();
              handleClose();
            }} 
            variant="contained"
          >
            Close & Refresh
          </Button>
        ) : (
          <>
            <Button onClick={handleClose} disabled={loading}>
              Cancel
            </Button>
            <Button
              onClick={handleExtract}
              variant="contained"
              disabled={loading || !isValidInput}
            >
              {loading ? 'Extracting...' : 'Extract'}
            </Button>
          </>
        )}
      </DialogActions>
    </Dialog>
  );
};
