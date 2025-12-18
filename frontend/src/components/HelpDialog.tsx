import React, { useState, useEffect, useMemo } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  IconButton,
  Box,
  Typography,
  TextField,
  InputAdornment,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  Drawer,
  useTheme,
  useMediaQuery,
  Skeleton,
  Alert,
  Button,
  Collapse,
  Divider
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import SearchIcon from '@mui/icons-material/Search';
import MenuIcon from '@mui/icons-material/Menu';
import ExpandLess from '@mui/icons-material/ExpandLess';
import ExpandMore from '@mui/icons-material/ExpandMore';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { vs } from 'react-syntax-highlighter/dist/esm/styles/hljs';
import api from '../api/client';

interface HelpDialogProps {
  open: boolean;
  onClose: () => void;
  initialTopic?: string;
}

interface HelpTopic {
  id: string;
  title: string;
  description: string;
  filePath: string;
}

interface HelpCategory {
  id: string;
  title: string;
  description: string;
  topics: HelpTopic[];
}

interface HelpIndex {
  version: string;
  lastUpdated: string;
  categories: HelpCategory[];
}

const DRAWER_WIDTH = 280;

const HelpDialog: React.FC<HelpDialogProps> = ({ open, onClose, initialTopic }) => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  
  const [helpIndex, setHelpIndex] = useState<HelpIndex | null>(null);
  const [currentTopic, setCurrentTopic] = useState<string | null>(initialTopic || null);
  const [content, setContent] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false);
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set());
  
  // In-memory cache for loaded content
  const [contentCache] = useState<Map<string, string>>(new Map());

  // Load help index on mount
  useEffect(() => {
    if (open && !helpIndex) {
      fetchHelpIndex();
    }
  }, [open]);

  // Load initial topic if provided
  useEffect(() => {
    if (initialTopic && helpIndex && open) {
      loadTopic(initialTopic);
    }
  }, [initialTopic, helpIndex, open]);

  // Parse URL query param for deep linking
  useEffect(() => {
    if (open && helpIndex) {
      const params = new URLSearchParams(window.location.search);
      const helpParam = params.get('help');
      if (helpParam) {
        loadTopic(helpParam);
      }
    }
  }, [open, helpIndex]);

  const fetchHelpIndex = async () => {
    try {
      const response = await api.get('/help/index');
      const data = response.data;
      setHelpIndex(data);
      
      // Expand first category by default
      if (data.categories.length > 0) {
        setExpandedCategories(new Set([data.categories[0].id]));
      }
      
      // Load first topic if no initial topic
      if (!initialTopic && data.categories.length > 0 && data.categories[0].topics.length > 0) {
        loadTopic(data.categories[0].topics[0].id);
      }
    } catch (err) {
      console.error('Error fetching help index:', err);
      setError('Failed to load help topics. Please try again.');
    }
  };

  const loadTopic = async (topicId: string) => {
    // Check cache first
    if (contentCache.has(topicId)) {
      setContent(contentCache.get(topicId)!);
      setCurrentTopic(topicId);
      setError(null);
      updateUrl(topicId);
      if (isMobile) setMobileDrawerOpen(false);
      return;
    }

    setLoading(true);
    setError(null);
    
    try {
      const response = await api.get(`/help/content/${topicId}`, {
        responseType: 'text'
      });
      const markdown = response.data;
      
      // Cache the content
      contentCache.set(topicId, markdown);
      
      setContent(markdown);
      setCurrentTopic(topicId);
      updateUrl(topicId);
      if (isMobile) setMobileDrawerOpen(false);
    } catch (err) {
      console.error('Error fetching help content:', err);
      setError('Failed to load help content. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const updateUrl = (topicId: string) => {
    const url = new URL(window.location.href);
    url.searchParams.set('help', topicId);
    window.history.replaceState({}, '', url.toString());
  };

  const handleCategoryToggle = (categoryId: string) => {
    setExpandedCategories(prev => {
      const newSet = new Set(prev);
      if (newSet.has(categoryId)) {
        newSet.delete(categoryId);
      } else {
        newSet.add(categoryId);
      }
      return newSet;
    });
  };

  const handleRetry = () => {
    if (currentTopic) {
      contentCache.delete(currentTopic);
      loadTopic(currentTopic);
    } else if (helpIndex) {
      fetchHelpIndex();
    }
  };

  // Filter topics based on search query
  const filteredCategories = useMemo(() => {
    if (!helpIndex || !searchQuery.trim()) return helpIndex?.categories || [];
    
    const query = searchQuery.toLowerCase();
    return helpIndex.categories
      .map(category => ({
        ...category,
        topics: category.topics.filter(topic =>
          topic.title.toLowerCase().includes(query) ||
          topic.description.toLowerCase().includes(query) ||
          (contentCache.has(topic.id) && contentCache.get(topic.id)!.toLowerCase().includes(query))
        )
      }))
      .filter(category => category.topics.length > 0);
  }, [helpIndex, searchQuery, contentCache]);

  // Auto-expand categories with search results
  useEffect(() => {
    if (searchQuery.trim() && filteredCategories.length > 0) {
      setExpandedCategories(new Set(filteredCategories.map(c => c.id)));
    }
  }, [searchQuery, filteredCategories]);

  const drawerContent = (
    <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <Box sx={{ p: 2 }}>
        <TextField
          fullWidth
          size="small"
          placeholder="Search help..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon />
              </InputAdornment>
            ),
          }}
        />
      </Box>
      <Divider />
      <Box sx={{ flexGrow: 1, overflowY: 'auto' }}>
        <List dense>
          {filteredCategories.map((category) => (
            <React.Fragment key={category.id}>
              <ListItem disablePadding>
                <ListItemButton onClick={() => handleCategoryToggle(category.id)}>
                  <ListItemText 
                    primary={category.title}
                    primaryTypographyProps={{ fontWeight: 600, fontSize: '0.9rem' }}
                  />
                  {expandedCategories.has(category.id) ? <ExpandLess /> : <ExpandMore />}
                </ListItemButton>
              </ListItem>
              <Collapse in={expandedCategories.has(category.id)} timeout="auto" unmountOnExit>
                <List component="div" disablePadding dense>
                  {category.topics.map((topic) => (
                    <ListItem key={topic.id} disablePadding>
                      <ListItemButton
                        sx={{ pl: 4 }}
                        selected={currentTopic === topic.id}
                        onClick={() => loadTopic(topic.id)}
                      >
                        <ListItemText 
                          primary={topic.title}
                          primaryTypographyProps={{ fontSize: '0.85rem' }}
                        />
                      </ListItemButton>
                    </ListItem>
                  ))}
                </List>
              </Collapse>
            </React.Fragment>
          ))}
        </List>
      </Box>
      {helpIndex && (
        <Box sx={{ p: 2, borderTop: 1, borderColor: 'divider' }}>
          <Typography variant="caption" color="text.secondary">
            Help Version: {helpIndex.version}<br />
            Updated: {helpIndex.lastUpdated}
          </Typography>
        </Box>
      )}
    </Box>
  );

  return (
    <Dialog 
      open={open} 
      onClose={onClose} 
      maxWidth="lg" 
      fullWidth
      fullScreen={isMobile}
      PaperProps={{
        sx: { height: isMobile ? '100%' : '90vh' }
      }}
    >
      <DialogTitle sx={{ m: 0, p: 2, bgcolor: 'primary.main', color: 'white' }}>
        <Box display="flex" alignItems="center" justifyContent="space-between">
          <Box display="flex" alignItems="center" gap={1}>
            {isMobile && (
              <IconButton
                onClick={() => setMobileDrawerOpen(!mobileDrawerOpen)}
                sx={{ color: 'white', mr: 1 }}
              >
                <MenuIcon />
              </IconButton>
            )}
            <Typography variant="h6" component="div">
              SOC Analyzer Help
            </Typography>
          </Box>
          <IconButton
            aria-label="close"
            onClick={onClose}
            sx={{ color: 'white' }}
          >
            <CloseIcon />
          </IconButton>
        </Box>
      </DialogTitle>

      <DialogContent sx={{ p: 0, display: 'flex', height: 'calc(100% - 64px)' }}>
        {/* Desktop drawer - permanent */}
        {!isMobile && (
          <Drawer
            variant="permanent"
            sx={{
              width: DRAWER_WIDTH,
              flexShrink: 0,
              '& .MuiDrawer-paper': {
                width: DRAWER_WIDTH,
                boxSizing: 'border-box',
                position: 'relative',
                height: '100%',
                borderRight: 1,
                borderColor: 'divider'
              },
            }}
          >
            {drawerContent}
          </Drawer>
        )}

        {/* Mobile drawer - temporary */}
        {isMobile && (
          <Drawer
            variant="temporary"
            open={mobileDrawerOpen}
            onClose={() => setMobileDrawerOpen(false)}
            ModalProps={{ keepMounted: true }}
            sx={{
              '& .MuiDrawer-paper': {
                width: DRAWER_WIDTH,
                boxSizing: 'border-box',
              },
            }}
          >
            {drawerContent}
          </Drawer>
        )}

        {/* Content area */}
        <Box
          sx={{
            flexGrow: 1,
            p: 3,
            overflowY: 'auto',
            bgcolor: 'background.default'
          }}
        >
          {!helpIndex && !error && (
            <Box>
              <Skeleton variant="text" width="60%" height={40} />
              <Skeleton variant="text" width="100%" />
              <Skeleton variant="text" width="100%" />
              <Skeleton variant="text" width="80%" />
            </Box>
          )}

          {error && (
            <Alert 
              severity="error"
              action={
                <Button color="inherit" size="small" onClick={handleRetry}>
                  Retry
                </Button>
              }
            >
              {error}
            </Alert>
          )}

          {loading && (
            <Box>
              <Skeleton variant="text" width="60%" height={40} />
              <Skeleton variant="rectangular" height={200} sx={{ my: 2 }} />
              <Skeleton variant="text" width="100%" />
              <Skeleton variant="text" width="100%" />
              <Skeleton variant="text" width="80%" />
            </Box>
          )}

          {!loading && !error && content && (
            <Box
              sx={{
                '& h1': { mt: 2, mb: 2, fontSize: '2rem', fontWeight: 600, color: 'primary.main' },
                '& h2': { mt: 3, mb: 1.5, fontSize: '1.5rem', fontWeight: 600 },
                '& h3': { mt: 2, mb: 1, fontSize: '1.25rem', fontWeight: 600 },
                '& p': { mb: 2, lineHeight: 1.7 },
                '& ul, & ol': { mb: 2, pl: 3 },
                '& li': { mb: 0.5 },
                '& code': { 
                  bgcolor: theme.palette.mode === 'dark' ? 'grey.800' : 'grey.100',
                  px: 0.5,
                  py: 0.25,
                  borderRadius: 0.5,
                  fontSize: '0.9em',
                  fontFamily: 'monospace'
                },
                '& pre': { mb: 2 },
                '& blockquote': {
                  borderLeft: 4,
                  borderColor: 'primary.main',
                  pl: 2,
                  py: 0.5,
                  my: 2,
                  bgcolor: theme.palette.mode === 'dark' ? 'grey.900' : 'grey.50'
                },
                '& table': {
                  width: '100%',
                  borderCollapse: 'collapse',
                  mb: 2
                },
                '& th, & td': {
                  border: 1,
                  borderColor: 'divider',
                  p: 1,
                  textAlign: 'left'
                },
                '& th': {
                  bgcolor: theme.palette.mode === 'dark' ? 'grey.800' : 'grey.100',
                  fontWeight: 600
                },
                '& a': {
                  color: 'primary.main',
                  textDecoration: 'none',
                  '&:hover': { textDecoration: 'underline' }
                },
                '& img': { maxWidth: '100%', height: 'auto' }
              }}
            >
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  code({ node, className, children, ...props }: any) {
                    const match = /language-(\w+)/.exec(className || '');
                    const inline = !props['data-inline'] && !match;
                    return !inline && match ? (
                      <SyntaxHighlighter
                        style={theme.palette.mode === 'dark' ? (vscDarkPlus as any) : (vs as any)}
                        language={match[1]}
                        PreTag="div"
                        {...props}
                      >
                        {String(children).replace(/\n$/, '')}
                      </SyntaxHighlighter>
                    ) : (
                      <code className={className} {...props}>
                        {children}
                      </code>
                    );
                  },
                  a({ node, href, children, ...props }) {
                    // Handle internal links (topic references)
                    if (href?.startsWith('#')) {
                      const topicId = href.substring(1);
                      return (
                        <a
                          href={href}
                          onClick={(e) => {
                            e.preventDefault();
                            loadTopic(topicId);
                          }}
                          {...props}
                        >
                          {children}
                        </a>
                      );
                    }
                    // External links open in new tab
                    return (
                      <a href={href} target="_blank" rel="noopener noreferrer" {...props}>
                        {children}
                      </a>
                    );
                  }
                }}
              >
                {content}
              </ReactMarkdown>
            </Box>
          )}

          {!loading && !error && !content && helpIndex && (
            <Box sx={{ textAlign: 'center', py: 8 }}>
              <Typography variant="h6" color="text.secondary" gutterBottom>
                Select a topic from the sidebar to get started
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Use the search box to find specific information
              </Typography>
            </Box>
          )}
        </Box>
      </DialogContent>
    </Dialog>
  );
};

export default HelpDialog;
