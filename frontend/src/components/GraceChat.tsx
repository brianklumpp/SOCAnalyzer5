import React, { useState, useRef, useEffect } from 'react';
import {
  Box,
  Paper,
  TextField,
  IconButton,
  Typography,
  CircularProgress,
  Chip,
  List,
  ListItem,
  Divider,
  Button,
} from '@mui/material';
import SendIcon from '@mui/icons-material/Send';
import SmartToyIcon from '@mui/icons-material/SmartToy';
import PersonIcon from '@mui/icons-material/Person';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { solidigmColors } from '../theme/solidigmTheme';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

interface GraceChatProps {
  scanId: number;
}

const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const GraceChat: React.FC<GraceChatProps> = ({ scanId }) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Load conversation history on mount
  useEffect(() => {
    loadHistory();
  }, [scanId]);

  const loadHistory = async () => {
    try {
      const response = await axios.get(`${API_BASE}/grace/${scanId}/history`);
      const history = response.data.messages || [];
      setMessages(history.map((msg: any) => ({
        role: msg.role,
        content: msg.content,
        timestamp: new Date(msg.timestamp),
      })));
    } catch (err) {
      console.error('Failed to load chat history:', err);
      // Don't show error for empty history
    }
  };

  const handleSend = async () => {
    if (!input.trim() || loading) return;

    const userMessage: Message = {
      role: 'user',
      content: input.trim(),
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setLoading(true);
    setError(null);

    try {
      const response = await axios.post(`${API_BASE}/grace/${scanId}/message`, {
        message: input.trim(),
        conversation_history: messages.map(m => ({
          role: m.role,
          content: m.content,
        })),
      });

      const assistantMessage: Message = {
        role: 'assistant',
        content: response.data.response,
        timestamp: new Date(),
      };

      setMessages(prev => [...prev, assistantMessage]);
    } catch (err: any) {
      console.error('Failed to send message:', err);
      setError(err.response?.data?.detail || 'Failed to get response from GRaCe');
    } finally {
      setLoading(false);
    }
  };

  const handleClear = async () => {
    try {
      await axios.delete(`${API_BASE}/grace/${scanId}/conversation`);
      setMessages([]);
      setError(null);
    } catch (err) {
      console.error('Failed to clear conversation:', err);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <Box sx={{ p: 2, borderBottom: '1px solid', borderColor: 'divider' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <SmartToyIcon color="primary" />
            <Typography variant="h6">GRaCe</Typography>
            <Chip label="AI Assistant" size="small" color="primary" variant="outlined" />
          </Box>
          {messages.length > 0 && (
            <Button
              size="small"
              startIcon={<DeleteOutlineIcon />}
              onClick={handleClear}
              variant="outlined"
            >
              Clear Conversation
            </Button>
          )}
        </Box>
        <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
          Ask questions about this report (controls, CUECs, frameworks, risks)
        </Typography>
      </Box>

      {/* Messages */}
      <Box sx={{ flexGrow: 1, overflowY: 'auto', p: 2 }}>
        {messages.length === 0 ? (
          <Box sx={{ textAlign: 'center', mt: 8, color: 'text.secondary' }}>
            <SmartToyIcon sx={{ fontSize: 64, opacity: 0.3, mb: 2 }} />
            <Typography variant="h6" gutterBottom>
              Hi! I'm GRaCe, your GRC Assistant
            </Typography>
            <Typography variant="body2" sx={{ mb: 3 }}>
              I can help you understand this SOC report. Try asking:
            </Typography>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, maxWidth: 500, mx: 'auto' }}>
              <Chip
                label="What CUECs are in this report?"
                variant="outlined"
                clickable
                onClick={() => setInput("What CUECs are in this report?")}
              />
              <Chip
                label="Which controls have deviations?"
                variant="outlined"
                clickable
                onClick={() => setInput("Which controls have deviations?")}
              />
              <Chip
                label="What's the TSC coverage like?"
                variant="outlined"
                clickable
                onClick={() => setInput("What's the TSC coverage like?")}
              />
              <Chip
                label="Summarize the key risks"
                variant="outlined"
                clickable
                onClick={() => setInput("Summarize the key risks")}
              />
            </Box>
          </Box>
        ) : (
          <List>
            {messages.map((msg, idx) => (
              <React.Fragment key={idx}>
                <ListItem
                  sx={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: msg.role === 'user' ? 'flex-end' : 'flex-start',
                    py: 1,
                  }}
                >
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                    {msg.role === 'assistant' && <SmartToyIcon fontSize="small" color="primary" />}
                    <Typography variant="caption" color="text.secondary">
                      {msg.role === 'user' ? 'You' : 'GRaCe'}
                    </Typography>
                    {msg.role === 'user' && <PersonIcon fontSize="small" color="action" />}
                  </Box>
                  <Paper
                    elevation={1}
                    sx={{
                      p: 1.5,
                      maxWidth: '80%',
                      bgcolor: msg.role === 'user' ? solidigmColors.purple : 'white',
                      color: msg.role === 'user' ? 'white' : 'text.primary',
                    }}
                  >
                    {msg.role === 'assistant' ? (
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          p: ({ children }) => <Typography variant="body2" paragraph sx={{ mb: 1, '&:last-child': { mb: 0 } }}>{children}</Typography>,
                          ul: ({ children }) => <Box component="ul" sx={{ pl: 2, my: 1, '&:last-child': { mb: 0 } }}>{children}</Box>,
                          ol: ({ children }) => <Box component="ol" sx={{ pl: 2, my: 1, '&:last-child': { mb: 0 } }}>{children}</Box>,
                          li: ({ children }) => <Box component="li" sx={{ mb: 0.5 }}>{children}</Box>,
                          code: ({ inline, children }: any) => 
                            inline 
                              ? <Box component="code" sx={{ bgcolor: '#f5f5f5', px: 0.5, py: 0.25, borderRadius: 0.5, fontFamily: 'monospace', fontSize: '0.9em' }}>{children}</Box>
                              : <Box component="pre" sx={{ bgcolor: '#f5f5f5', p: 1, borderRadius: 1, overflowX: 'auto', my: 1 }}><code>{children}</code></Box>,
                          strong: ({ children }) => <Box component="strong" sx={{ fontWeight: 700 }}>{children}</Box>,
                          em: ({ children }) => <Box component="em" sx={{ fontStyle: 'italic' }}>{children}</Box>,
                          h1: ({ children }) => <Typography variant="h6" sx={{ fontWeight: 600, mt: 2, mb: 1 }}>{children}</Typography>,
                          h2: ({ children }) => <Typography variant="subtitle1" sx={{ fontWeight: 600, mt: 1.5, mb: 1 }}>{children}</Typography>,
                          h3: ({ children }) => <Typography variant="subtitle2" sx={{ fontWeight: 600, mt: 1, mb: 0.5 }}>{children}</Typography>,
                        }}
                      >
                        {msg.content}
                      </ReactMarkdown>
                    ) : (
                      <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                        {msg.content}
                      </Typography>
                    )}
                  </Paper>
                </ListItem>
                {idx < messages.length - 1 && <Divider variant="middle" />}
              </React.Fragment>
            ))}
            {loading && (
              <ListItem sx={{ display: 'flex', justifyContent: 'flex-start', py: 1 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <SmartToyIcon fontSize="small" color="primary" />
                  <CircularProgress size={20} />
                  <Typography variant="caption" color="text.secondary">
                    GRaCe is thinking...
                  </Typography>
                </Box>
              </ListItem>
            )}
            <div ref={messagesEndRef} />
          </List>
        )}
      </Box>

      {/* Error Display */}
      {error && (
        <Box sx={{ px: 2, pb: 1 }}>
          <Paper sx={{ p: 1, bgcolor: 'error.light' }}>
            <Typography variant="caption" color="error.contrastText">
              {error}
            </Typography>
          </Paper>
        </Box>
      )}

      {/* Input */}
      <Box sx={{ p: 2, borderTop: '1px solid', borderColor: 'divider' }}>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <TextField
            fullWidth
            multiline
            maxRows={4}
            placeholder="Ask GRaCe about this report..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
            disabled={loading}
            size="small"
          />
          <IconButton
            color="primary"
            onClick={handleSend}
            disabled={!input.trim() || loading}
            sx={{ alignSelf: 'flex-end' }}
          >
            <SendIcon />
          </IconButton>
        </Box>
        <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
          Press Enter to send, Shift+Enter for new line
        </Typography>
      </Box>
    </Box>
  );
};

export default GraceChat;
