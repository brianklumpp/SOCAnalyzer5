import React, { useState } from 'react';
import {
  Box,
  Button,
  Paper,
  Typography,
  Stack,
  Chip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  IconButton,
  Tooltip,
  Alert,
  LinearProgress
} from '@mui/material';
import PauseIcon from '@mui/icons-material/Pause';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import UploadFileIcon from '@mui/icons-material/UploadFile';
import DeleteIcon from '@mui/icons-material/Delete';
import AddIcon from '@mui/icons-material/Add';
import api from '../../api/client';

interface QueueControlsProps {
  isPaused: boolean;
  queueLength: number;
  stats?: {
    total_queued?: number;
    total_completed?: number;
    total_failed?: number;
    total_cancelled?: number;
  };
  onQueueUpdate: () => void;
}

interface FileToUpload {
  file: File;
  reportType: string;
  priority: number;
}

const QueueControls: React.FC<QueueControlsProps> = ({
  isPaused,
  queueLength,
  stats,
  onQueueUpdate
}) => {
  const [batchDialogOpen, setBatchDialogOpen] = useState(false);
  const [files, setFiles] = useState<FileToUpload[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  // Handle pause/resume
  const handlePauseResume = async () => {
    try {
      if (isPaused) {
        await api.post('/analyze/queue/resume');
      } else {
        await api.post('/analyze/queue/pause');
      }
      onQueueUpdate();
    } catch (error) {
      console.error('Failed to pause/resume queue:', error);
    }
  };

  // Handle file selection
  const handleFileSelect = (event: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = Array.from(event.target.files || []);
    const newFiles: FileToUpload[] = selectedFiles.map(file => ({
      file,
      reportType: 'Auto', // Default to auto-detect
      priority: 2 // Default to medium priority
    }));
    setFiles(prev => [...prev, ...newFiles]);
  };

  // Handle drag-and-drop events
  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const droppedFiles = Array.from(e.dataTransfer.files).filter(
      file => file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')
    );

    if (droppedFiles.length > 0) {
      const newFiles: FileToUpload[] = droppedFiles.map(file => ({
        file,
        reportType: 'Auto',
        priority: 2
      }));
      setFiles(prev => [...prev, ...newFiles]);
      setBatchDialogOpen(true);
    }
  };

  // Remove file from list
  const handleRemoveFile = (index: number) => {
    setFiles(prev => prev.filter((_, i) => i !== index));
  };

  // Update file settings
  const handleUpdateFile = (index: number, field: 'reportType' | 'priority', value: string | number) => {
    setFiles(prev => prev.map((f, i) => i === index ? { ...f, [field]: value } : f));
  };

  // Submit batch upload
  const handleBatchUpload = async () => {
    if (files.length === 0) return;

    setUploading(true);
    setUploadError(null);
    setUploadSuccess(null);

    try {
      const formData = new FormData();
      
      // Add files
      files.forEach(f => formData.append('files', f.file));
      
      // Add report types (comma-separated, empty string for auto-detect)
      const reportTypes = files.map(f => f.reportType === 'Auto' ? '' : f.reportType).join(',');
      formData.append('report_types', reportTypes);
      
      // Add priorities (comma-separated)
      const priorities = files.map(f => f.priority.toString()).join(',');
      formData.append('priorities', priorities);

      const response = await api.post('/analyze/batch', formData);

      const { queued_count, errors } = response.data;
      
      if (errors && errors.length > 0) {
        setUploadError(`${queued_count} files queued, ${errors.length} failed: ${errors.join(', ')}`);
      } else {
        setUploadSuccess(`Successfully queued ${queued_count} scan${queued_count > 1 ? 's' : ''}`);
      }

      // Clear files and close dialog after successful upload
      setTimeout(() => {
        setFiles([]);
        setBatchDialogOpen(false);
        setUploadSuccess(null);
        onQueueUpdate();
      }, 2000);

    } catch (error: any) {
      setUploadError(error.response?.data?.detail || 'Failed to upload files');
    } finally {
      setUploading(false);
    }
  };

  return (
    <>
      <Paper sx={{ 
        p: 2, 
        mb: 3,
        bgcolor: 'rgba(0, 43, 92, 0.08)',
        border: '2px solid',
        borderColor: 'rgba(0, 43, 92, 0.3)',
        borderRadius: 2,
      }}>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems="center">
          {/* Queue Stats */}
          <Box flex={1}>
            <Typography variant="h6" gutterBottom>
              Scan Queue
            </Typography>
            <Stack direction="row" spacing={1}>
              <Chip
                label={`${queueLength} in queue`}
                color={queueLength > 0 ? 'primary' : 'default'}
                size="small"
              />
              {stats?.total_failed !== undefined && stats.total_failed > 0 && (
                <Chip
                  label={`${stats.total_failed} failed`}
                  color="error"
                  size="small"
                  variant="outlined"
                />
              )}
            </Stack>
          </Box>

          {/* Control Buttons */}
          <Stack direction="row" spacing={1}>
            <Tooltip title={isPaused ? 'Start processing queue' : 'Pause queue processing'}>
              <Button
                variant="contained"
                startIcon={isPaused ? <PlayArrowIcon /> : <PauseIcon />}
                onClick={handlePauseResume}
                color={isPaused ? 'success' : 'warning'}
              >
                {isPaused ? 'Start Queue' : 'Pause Queue'}
              </Button>
            </Tooltip>
          </Stack>
        </Stack>
        
        {/* Drag-and-Drop Zone */}
        <Box
          sx={{
            mt: 2,
            border: '2px dashed',
            borderColor: isDragging ? 'rgb(79, 0, 181)' : 'rgba(0, 43, 92, 0.4)',
            borderRadius: 2,
            p: 3,
            textAlign: 'center',
            cursor: 'pointer',
            transition: 'all 0.2s',
            bgcolor: isDragging ? 'rgba(79, 0, 181, 0.12)' : 'rgba(0, 43, 92, 0.05)',
            '&:hover': {
              borderColor: 'rgb(79, 0, 181)',
              bgcolor: 'rgba(0, 43, 92, 0.08)',
            },
          }}
          onClick={() => setBatchDialogOpen(true)}
          onDragEnter={handleDragEnter}
          onDragLeave={handleDragLeave}
          onDragOver={handleDragOver}
          onDrop={handleDrop}
        >
          <UploadFileIcon sx={{ fontSize: 40, color: isDragging ? 'primary.main' : 'text.secondary', mb: 1 }} />
          <Typography variant="body1" sx={{ fontWeight: 500, mb: 0.5 }}>
            {isDragging ? 'Drop PDFs to upload' : 'Drop PDFs here to queue'}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            Or click to select files for batch upload
          </Typography>
        </Box>
      </Paper>

      {/* Batch Upload Dialog */}
      <Dialog
        open={batchDialogOpen}
        onClose={() => !uploading && setBatchDialogOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>Batch Upload PDFs</DialogTitle>
        <DialogContent>
          {uploadError && (
            <Alert severity="error" sx={{ mb: 2 }} onClose={() => setUploadError(null)}>
              {uploadError}
            </Alert>
          )}
          {uploadSuccess && (
            <Alert severity="success" sx={{ mb: 2 }}>
              {uploadSuccess}
            </Alert>
          )}

          {/* File Upload Button */}
          <Button
            variant="outlined"
            component="label"
            startIcon={<AddIcon />}
            fullWidth
            sx={{ mb: 2 }}
            disabled={uploading}
          >
            Add PDF Files
            <input
              type="file"
              hidden
              multiple
              accept=".pdf"
              onChange={handleFileSelect}
            />
          </Button>

          {/* Files List */}
          {files.length > 0 && (
            <Box>
              <Typography variant="subtitle2" gutterBottom>
                Files to Upload ({files.length})
              </Typography>
              {files.map((fileItem, index) => (
                <Paper key={index} variant="outlined" sx={{ p: 2, mb: 1 }}>
                  <Stack direction="row" spacing={2} alignItems="center">
                    {/* Filename */}
                    <Box flex={1}>
                      <Typography variant="body2" noWrap>
                        {fileItem.file.name}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {(fileItem.file.size / 1024 / 1024).toFixed(2)} MB
                      </Typography>
                    </Box>

                    {/* Report Type Selector */}
                    <FormControl size="small" sx={{ minWidth: 120 }}>
                      <InputLabel>Type</InputLabel>
                      <Select
                        value={fileItem.reportType}
                        label="Type"
                        onChange={(e) => handleUpdateFile(index, 'reportType', e.target.value)}
                        disabled={uploading}
                      >
                        <MenuItem value="Auto">Auto-detect</MenuItem>
                        <MenuItem value="SOC1">SOC 1</MenuItem>
                        <MenuItem value="SOC2">SOC 2</MenuItem>
                      </Select>
                    </FormControl>

                    {/* Priority Selector */}
                    <FormControl size="small" sx={{ minWidth: 100 }}>
                      <InputLabel>Priority</InputLabel>
                      <Select
                        value={fileItem.priority}
                        label="Priority"
                        onChange={(e) => handleUpdateFile(index, 'priority', Number(e.target.value))}
                        disabled={uploading}
                      >
                        <MenuItem value={1}>High</MenuItem>
                        <MenuItem value={2}>Medium</MenuItem>
                        <MenuItem value={3}>Low</MenuItem>
                      </Select>
                    </FormControl>

                    {/* Remove Button */}
                    <IconButton
                      size="small"
                      onClick={() => handleRemoveFile(index)}
                      disabled={uploading}
                      color="error"
                    >
                      <DeleteIcon />
                    </IconButton>
                  </Stack>
                </Paper>
              ))}
            </Box>
          )}

          {uploading && (
            <Box sx={{ mt: 2 }}>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                Uploading files...
              </Typography>
              <LinearProgress />
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setBatchDialogOpen(false)} disabled={uploading}>
            Cancel
          </Button>
          <Button
            onClick={handleBatchUpload}
            variant="contained"
            disabled={files.length === 0 || uploading}
          >
            Upload {files.length > 0 && `(${files.length})`}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
};

export default QueueControls;
