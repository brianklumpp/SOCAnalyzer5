/**
 * FloatingGraceChat Component
 * 
 * Floating AI assistant available across all tabs - like a helpful assistant
 * that's always available but stays out of the way.
 */

import React, { useState, useRef, useEffect } from 'react';
import {
  Box,
  Paper,
  TextField,
  IconButton,
  Typography,
  CircularProgress,
  Fab,
  Collapse,
  Divider,
  Button,
  Tooltip,
} from '@mui/material';
import SendIcon from '@mui/icons-material/Send';
import SmartToyIcon from '@mui/icons-material/SmartToy';
import PersonIcon from '@mui/icons-material/Person';
import CloseIcon from '@mui/icons-material/Close';
import MinimizeIcon from '@mui/icons-material/Minimize';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { solidigmColors } from '../theme/solidigmTheme';
import { APP_CONFIG } from '../config';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

interface FloatingGraceChatProps {
  scanId: number;
}

const FloatingGraceChat: React.FC<FloatingGraceChatProps> = ({ scanId }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    if (isOpen) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isOpen]);

  // Load conversation history when opened
  useEffect(() => {
    if (isOpen && scanId) {
      loadHistory();
    }
  }, [isOpen, scanId]);

  const loadHistory = async () => {
    try {
      const response = await axios.get(APP_CONFIG.apiUrl(`/grace/${scanId}/history`));
      const history = response.data.messages || [];
      setMessages(history.map((msg: any) => ({
        role: msg.role,
        content: msg.content,
        timestamp: new Date(msg.timestamp),
      })));
    } catch (err) {
      console.error('Failed to load chat history:', err);
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
      const response = await axios.post(APP_CONFIG.apiUrl(`/grace/${scanId}/message`), {
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

  const handleClearHistory = async () => {
    try {
      await axios.delete(`${API_BASE}/grace/${scanId}/conversation`);
      setMessages([]);
      setError(null);
    } catch (err) {
      console.error('Failed to clear history:', err);
      setError('Failed to clear conversation history');
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <>
      {/* Floating Action Button */}
      <Tooltip title={isOpen ? "Close GRaCe" : "Ask GRaCe"} placement="left">
        <Fab
          color="primary"
          onClick={() => setIsOpen(!isOpen)}
          sx={{
            position: 'fixed',
            bottom: 24,
            right: 24,
            zIndex: 1300,
            bgcolor: solidigmColors.purple,
            '&:hover': {
              bgcolor: solidigmColors.darkBlue,
            },
          }}
        >
          {isOpen ? <CloseIcon /> : <SmartToyIcon />}
        </Fab>
      </Tooltip>

      {/* Floating Chat Window */}
      <Collapse in={isOpen} timeout={300}>
        <Paper
          elevation={8}
          sx={{
            position: 'fixed',
            bottom: 96,
            right: 24,
            width: 400,
            height: 600,
            zIndex: 1300,
            display: 'flex',
            flexDirection: 'column',
            borderRadius: 2,
            overflow: 'hidden',
            border: `2px solid ${solidigmColors.purple}`,
          }}
        >
          {/* Header */}
          <Box
            sx={{
              p: 2,
              bgcolor: solidigmColors.purple,
              color: 'white',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <SmartToyIcon />
              <Typography variant="h6" sx={{ fontWeight: 600 }}>
                Ask GRaCe
              </Typography>
            </Box>
            <Box>
              <IconButton
                size="small"
                onClick={handleClearHistory}
                sx={{ color: 'white', mr: 0.5 }}
                title="Clear conversation"
              >
                <DeleteOutlineIcon fontSize="small" />
              </IconButton>
              <IconButton
                size="small"
                onClick={() => setIsOpen(false)}
                sx={{ color: 'white' }}
              >
                <MinimizeIcon fontSize="small" />
              </IconButton>
            </Box>
          </Box>

          <Divider />

          {/* Messages Area */}
          <Box
            sx={{
              flex: 1,
              overflowY: 'auto',
              p: 2,
              bgcolor: '#f5f5f5',
            }}
          >
            {messages.length === 0 && !loading && (
              <Box sx={{ textAlign: 'center', mt: 4, color: solidigmColors.mediumGray }}>
                <SmartToyIcon sx={{ fontSize: 48, mb: 2 }} />
                <Typography variant="body2">
                  Hi! I'm GRaCe, your GRC AI assistant.
                  <br />
                  Ask me anything about this scan!
                </Typography>
              </Box>
            )}

            {messages.map((msg, idx) => (
              <Box
                key={idx}
                sx={{
                  display: 'flex',
                  gap: 1,
                  mb: 2,
                  flexDirection: msg.role === 'user' ? 'row-reverse' : 'row',
                }}
              >
                <Box
                  sx={{
                    width: 32,
                    height: 32,
                    borderRadius: '50%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    bgcolor: msg.role === 'user' ? solidigmColors.purple : solidigmColors.teal,
                    color: 'white',
                    flexShrink: 0,
                  }}
                >
                  {msg.role === 'user' ? <PersonIcon fontSize="small" /> : <SmartToyIcon fontSize="small" />}
                </Box>
                <Paper
                  sx={{
                    p: 1.5,
                    maxWidth: '75%',
                    bgcolor: msg.role === 'user' ? solidigmColors.purple : 'white',
                    color: msg.role === 'user' ? 'white' : 'inherit',
                    borderRadius: 2,
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
                    <Typography
                      variant="body2"
                      sx={{
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-word',
                      }}
                    >
                      {msg.content}
                    </Typography>
                  )}
                </Paper>
              </Box>
            ))}

            {loading && (
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, ml: 5 }}>
                <CircularProgress size={16} />
                <Typography variant="body2" color="textSecondary">
                  GRaCe is thinking...
                </Typography>
              </Box>
            )}

            {error && (
              <Box sx={{ mt: 2, p: 2, bgcolor: '#ffebee', borderRadius: 1 }}>
                <Typography variant="body2" color="error">
                  {error}
                </Typography>
              </Box>
            )}

            <div ref={messagesEndRef} />
          </Box>

          <Divider />

          {/* Input Area */}
          <Box sx={{ p: 2, bgcolor: 'white' }}>
            <TextField
              fullWidth
              multiline
              maxRows={3}
              placeholder="Ask GRaCe about this scan..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={handleKeyPress}
              disabled={loading}
              variant="outlined"
              size="small"
              InputProps={{
                endAdornment: (
                  <IconButton
                    onClick={handleSend}
                    disabled={!input.trim() || loading}
                    color="primary"
                    sx={{
                      ml: 1,
                      bgcolor: solidigmColors.purple,
                      color: 'white',
                      '&:hover': {
                        bgcolor: solidigmColors.darkBlue,
                      },
                      '&:disabled': {
                        bgcolor: solidigmColors.mediumGray,
                        color: 'white',
                      },
                    }}
                  >
                    <SendIcon fontSize="small" />
                  </IconButton>
                ),
              }}
              sx={{
                '& .MuiOutlinedInput-root': {
                  pr: 0.5,
                },
              }}
            />
          </Box>
        </Paper>
      </Collapse>
    </>
  );
};

export default FloatingGraceChat;
