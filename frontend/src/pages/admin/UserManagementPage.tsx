import React, { useEffect, useState } from 'react';
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  IconButton,
  Menu,
  MenuItem,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  TextField,
  Typography,
  Alert,
  CircularProgress,
  Snackbar,
} from '@mui/material';
import {
  Add as AddIcon,
  MoreVert as MoreVertIcon,
  ContentCopy as CopyIcon,
} from '@mui/icons-material';
import apiClient from '../../api/client';

interface User {
  id: number;
  username: string;
  email: string;
  full_name: string | null;
  is_admin: boolean;
  is_active: boolean;
  created_at: string;
  last_login: string | null;
}

interface CreateUserData {
  username: string;
  email: string;
  password: string;
  full_name: string;
  is_admin: boolean;
}

interface UpdateUserData {
  full_name?: string;
  email?: string;
  is_active?: boolean;
  is_admin?: boolean;
}

export const UserManagementPage: React.FC = () => {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  
  // Pagination
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [searchQuery, setSearchQuery] = useState('');
  
  // Dialogs
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [resetPasswordDialogOpen, setResetPasswordDialogOpen] = useState(false);
  const [tempPassword, setTempPassword] = useState<string | null>(null);
  
  // Selected user for actions
  const [selectedUser, setSelectedUser] = useState<User | null>(null);
  
  // Menu anchor
  const [menuAnchor, setMenuAnchor] = useState<null | HTMLElement>(null);
  
  // Form states
  const [createForm, setCreateForm] = useState<CreateUserData>({
    username: '',
    email: '',
    password: '',
    full_name: '',
    is_admin: false,
  });
  
  const [editForm, setEditForm] = useState<UpdateUserData>({});

  // Fetch users
  const fetchUsers = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await apiClient.get('/users', {
        params: {
          skip: page * rowsPerPage,
          limit: rowsPerPage,
          search: searchQuery || undefined,
        },
      });
      setUsers(response.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load users');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, [page, rowsPerPage, searchQuery]);

  // Handle menu
  const handleMenuOpen = (event: React.MouseEvent<HTMLElement>, user: User) => {
    setMenuAnchor(event.currentTarget);
    setSelectedUser(user);
  };

  const handleMenuClose = () => {
    setMenuAnchor(null);
  };

  // Handle create user
  const handleCreateUser = async () => {
    try {
      setLoading(true);
      await apiClient.post('/auth/create-user', createForm);
      setSuccess(`User '${createForm.username}' created successfully`);
      setCreateDialogOpen(false);
      setCreateForm({
        username: '',
        email: '',
        password: '',
        full_name: '',
        is_admin: false,
      });
      fetchUsers();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create user');
    } finally {
      setLoading(false);
    }
  };

  // Handle update user
  const handleUpdateUser = async () => {
    if (!selectedUser) return;
    
    try {
      setLoading(true);
      await apiClient.patch(`/users/${selectedUser.id}`, editForm);
      setSuccess(`User '${selectedUser.username}' updated successfully`);
      setEditDialogOpen(false);
      setEditForm({});
      setSelectedUser(null);
      fetchUsers();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to update user');
    } finally {
      setLoading(false);
    }
  };

  // Handle delete user
  const handleDeleteUser = async () => {
    if (!selectedUser) return;
    
    try {
      setLoading(true);
      await apiClient.delete(`/users/${selectedUser.id}`);
      setSuccess(`User '${selectedUser.username}' deleted successfully`);
      setDeleteDialogOpen(false);
      setSelectedUser(null);
      fetchUsers();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to delete user');
    } finally {
      setLoading(false);
    }
  };

  // Handle reset password
  const handleResetPassword = async () => {
    if (!selectedUser) return;
    
    try {
      setLoading(true);
      const response = await apiClient.post(`/users/${selectedUser.id}/reset-password`);
      setTempPassword(response.data.temporary_password);
      setSuccess(`Password reset for '${selectedUser.username}'`);
      setResetPasswordDialogOpen(true);
      handleMenuClose();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to reset password');
    } finally {
      setLoading(false);
    }
  };

  // Handle toggle admin
  const handleToggleAdmin = async (user: User) => {
    try {
      setLoading(true);
      await apiClient.patch(`/users/${user.id}`, {
        is_admin: !user.is_admin,
      });
      setSuccess(`User '${user.username}' admin status updated`);
      fetchUsers();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to update admin status');
    } finally {
      setLoading(false);
    }
  };

  // Handle toggle active
  const handleToggleActive = async (user: User) => {
    try {
      setLoading(true);
      await apiClient.patch(`/users/${user.id}`, {
        is_active: !user.is_active,
      });
      setSuccess(`User '${user.username}' ${user.is_active ? 'deactivated' : 'activated'}`);
      fetchUsers();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to update user status');
    } finally {
      setLoading(false);
    }
  };

  // Copy temp password to clipboard
  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setSuccess('Password copied to clipboard');
  };

  // Format date
  const formatDate = (dateString: string | null) => {
    if (!dateString) return 'Never';
    return new Date(dateString).toLocaleString();
  };

  return (
    <Box sx={{ p: 3 }}>
      <Card>
        <CardContent>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
            <Typography variant="h5">User Management</Typography>
            <Button
              variant="contained"
              startIcon={<AddIcon />}
              onClick={() => setCreateDialogOpen(true)}
            >
              Create User
            </Button>
          </Box>

          <TextField
            fullWidth
            label="Search users"
            variant="outlined"
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setPage(0);
            }}
            sx={{ mb: 2 }}
          />

          {loading && !users.length ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
              <CircularProgress />
            </Box>
          ) : (
            <>
              <TableContainer component={Paper}>
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableCell>Username</TableCell>
                      <TableCell>Email</TableCell>
                      <TableCell>Full Name</TableCell>
                      <TableCell>Admin</TableCell>
                      <TableCell>Status</TableCell>
                      <TableCell>Last Login</TableCell>
                      <TableCell>Created</TableCell>
                      <TableCell>Actions</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {users.map((user) => (
                      <TableRow key={user.id}>
                        <TableCell>{user.username}</TableCell>
                        <TableCell>{user.email}</TableCell>
                        <TableCell>{user.full_name || '-'}</TableCell>
                        <TableCell>
                          {user.is_admin ? (
                            <Chip label="Admin" color="primary" size="small" />
                          ) : (
                            <Chip label="User" size="small" />
                          )}
                        </TableCell>
                        <TableCell>
                          {user.is_active ? (
                            <Chip label="Active" color="success" size="small" />
                          ) : (
                            <Chip label="Inactive" color="error" size="small" />
                          )}
                        </TableCell>
                        <TableCell>{formatDate(user.last_login)}</TableCell>
                        <TableCell>{formatDate(user.created_at)}</TableCell>
                        <TableCell>
                          <IconButton
                            size="small"
                            onClick={(e) => handleMenuOpen(e, user)}
                          >
                            <MoreVertIcon />
                          </IconButton>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>

              <TablePagination
                component="div"
                count={-1}
                page={page}
                onPageChange={(_, newPage) => setPage(newPage)}
                rowsPerPage={rowsPerPage}
                onRowsPerPageChange={(e) => {
                  setRowsPerPage(parseInt(e.target.value, 10));
                  setPage(0);
                }}
                rowsPerPageOptions={[10, 25, 50, 100]}
              />
            </>
          )}
        </CardContent>
      </Card>

      {/* Actions Menu */}
      <Menu
        anchorEl={menuAnchor}
        open={Boolean(menuAnchor)}
        onClose={handleMenuClose}
      >
        <MenuItem
          onClick={() => {
            setEditForm({
              full_name: selectedUser?.full_name || '',
              email: selectedUser?.email || '',
            });
            setEditDialogOpen(true);
            handleMenuClose();
          }}
        >
          Edit Details
        </MenuItem>
        <MenuItem
          onClick={() => {
            if (selectedUser) handleToggleAdmin(selectedUser);
            handleMenuClose();
          }}
        >
          {selectedUser?.is_admin ? 'Remove Admin' : 'Make Admin'}
        </MenuItem>
        <MenuItem
          onClick={() => {
            if (selectedUser) handleToggleActive(selectedUser);
            handleMenuClose();
          }}
        >
          {selectedUser?.is_active ? 'Deactivate' : 'Activate'}
        </MenuItem>
        <MenuItem onClick={handleResetPassword}>
          Reset Password
        </MenuItem>
        <MenuItem
          onClick={() => {
            setDeleteDialogOpen(true);
            handleMenuClose();
          }}
          sx={{ color: 'error.main' }}
        >
          Delete User
        </MenuItem>
      </Menu>

      {/* Create User Dialog */}
      <Dialog open={createDialogOpen} onClose={() => setCreateDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Create New User</DialogTitle>
        <DialogContent>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
            <TextField
              label="Username"
              value={createForm.username}
              onChange={(e) => setCreateForm({ ...createForm, username: e.target.value })}
              required
              fullWidth
            />
            <TextField
              label="Email"
              type="email"
              value={createForm.email}
              onChange={(e) => setCreateForm({ ...createForm, email: e.target.value })}
              required
              fullWidth
            />
            <TextField
              label="Password"
              type="password"
              value={createForm.password}
              onChange={(e) => setCreateForm({ ...createForm, password: e.target.value })}
              required
              fullWidth
            />
            <TextField
              label="Full Name"
              value={createForm.full_name}
              onChange={(e) => setCreateForm({ ...createForm, full_name: e.target.value })}
              fullWidth
            />
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <input
                type="checkbox"
                checked={createForm.is_admin}
                onChange={(e) => setCreateForm({ ...createForm, is_admin: e.target.checked })}
              />
              <Typography>Administrator</Typography>
            </Box>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateDialogOpen(false)}>Cancel</Button>
          <Button onClick={handleCreateUser} variant="contained" disabled={loading}>
            Create
          </Button>
        </DialogActions>
      </Dialog>

      {/* Edit User Dialog */}
      <Dialog open={editDialogOpen} onClose={() => setEditDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Edit User</DialogTitle>
        <DialogContent>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
            <TextField
              label="Full Name"
              value={editForm.full_name || ''}
              onChange={(e) => setEditForm({ ...editForm, full_name: e.target.value })}
              fullWidth
            />
            <TextField
              label="Email"
              type="email"
              value={editForm.email || ''}
              onChange={(e) => setEditForm({ ...editForm, email: e.target.value })}
              fullWidth
            />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditDialogOpen(false)}>Cancel</Button>
          <Button onClick={handleUpdateUser} variant="contained" disabled={loading}>
            Update
          </Button>
        </DialogActions>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteDialogOpen} onClose={() => setDeleteDialogOpen(false)}>
        <DialogTitle>Confirm Delete</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Are you sure you want to delete user '{selectedUser?.username}'? This action cannot be undone.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteDialogOpen(false)}>Cancel</Button>
          <Button onClick={handleDeleteUser} color="error" variant="contained" disabled={loading}>
            Delete
          </Button>
        </DialogActions>
      </Dialog>

      {/* Reset Password Dialog */}
      <Dialog open={resetPasswordDialogOpen} onClose={() => setResetPasswordDialogOpen(false)}>
        <DialogTitle>Password Reset Complete</DialogTitle>
        <DialogContent>
          <DialogContentText sx={{ mb: 2 }}>
            Password has been reset for user '{selectedUser?.username}'. Share this temporary password with the user:
          </DialogContentText>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, p: 2, bgcolor: 'grey.100', borderRadius: 1 }}>
            <Typography variant="h6" sx={{ flex: 1, fontFamily: 'monospace' }}>
              {tempPassword}
            </Typography>
            <IconButton onClick={() => tempPassword && copyToClipboard(tempPassword)} size="small">
              <CopyIcon />
            </IconButton>
          </Box>
          <Alert severity="warning" sx={{ mt: 2 }}>
            User should change this password after first login
          </Alert>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setResetPasswordDialogOpen(false)} variant="contained">
            Close
          </Button>
        </DialogActions>
      </Dialog>

      {/* Error Snackbar */}
      <Snackbar
        open={!!error}
        autoHideDuration={6000}
        onClose={() => setError(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert severity="error" onClose={() => setError(null)}>
          {error}
        </Alert>
      </Snackbar>

      {/* Success Snackbar */}
      <Snackbar
        open={!!success}
        autoHideDuration={4000}
        onClose={() => setSuccess(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert severity="success" onClose={() => setSuccess(null)}>
          {success}
        </Alert>
      </Snackbar>
    </Box>
  );
};

export default UserManagementPage;
