import React from 'react';
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
// Mock the API client with a factory to avoid importing the real axios ESM module
jest.mock('../api/client', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    post: jest.fn(),
  },
}));

import SettingsPage from './SettingsPage';
import api from '../api/client';
const mockedApi = api as unknown as { get: jest.Mock; post: jest.Mock };

describe('SettingsPage', () => {
  beforeEach(() => {
    jest.resetAllMocks();
  });

  test('shows loading then renders data when API succeeds', async () => {
    // Arrange mock responses in the same order fetchAll requests them
    mockedApi.get
      .mockResolvedValueOnce({ data: { model: { default_model: 'gpt-5', provider: 'dataiku_dss', temperature: 0, top_p: 0 }, token_windows: { max_total_tokens: 100000, max_input_tokens: 60000, max_output_tokens: 40000 }, budgets: { system_tokens: 1000, user_tokens: 2000, response_tokens: 3000, available_tokens: 50000 }, chunking: {}, executive_summary: {}, feature_toggles: {} } })
      .mockResolvedValueOnce({ data: { derived_chunk_sizes: { default: 4000, primary: 3500, description: 3000, subservice: 2500 }, overlap_chars: 200, chars_per_token: 4 } })
      .mockResolvedValueOnce({ data: { SOME_SETTING: 'value' } })
      .mockResolvedValueOnce({ data: { services: [] } });

    render(<SettingsPage />);

    // Loading indicators visible initially
    expect(screen.getByText(/Loading runtime/i)).toBeInTheDocument();

    // Eventually the form fields appear
    const modelField = await screen.findByLabelText('Default Model');
    expect(modelField).toHaveValue('gpt-5');

    // Budgets fields appear
    expect(await screen.findByLabelText('Default Chunk Size')).toHaveValue('4000');
  });

  test('shows error alert and Retry works when runtime fails', async () => {
    // First call: runtime fails, others succeed
    mockedApi.get
      .mockRejectedValueOnce({ message: 'Not Found' })
      .mockResolvedValueOnce({ data: { derived_chunk_sizes: { default: 4000, primary: 3500, description: 3000, subservice: 2500 }, overlap_chars: 200, chars_per_token: 4 } })
      .mockResolvedValueOnce({ data: {} })
      .mockResolvedValueOnce({ data: { services: [] } });

    render(<SettingsPage />);

  const errorText = await screen.findByText(/Runtime: Not Found/i);
  expect(errorText).toBeInTheDocument();
    const retryBtn = screen.getByRole('button', { name: /Retry/i });

    // Second attempt: all succeed
    mockedApi.get
      .mockResolvedValueOnce({ data: { model: { default_model: 'gpt-5', provider: 'dataiku_dss', temperature: 0, top_p: 0 }, token_windows: { max_total_tokens: 100000, max_input_tokens: 60000, max_output_tokens: 40000 }, budgets: { system_tokens: 1000, user_tokens: 2000, response_tokens: 3000, available_tokens: 50000 }, chunking: {}, executive_summary: {}, feature_toggles: {} } })
      .mockResolvedValueOnce({ data: { derived_chunk_sizes: { default: 4000, primary: 3500, description: 3000, subservice: 2500 }, overlap_chars: 200, chars_per_token: 4 } })
      .mockResolvedValueOnce({ data: {} })
      .mockResolvedValueOnce({ data: { services: [] } });

    await act(async () => {
      fireEvent.click(retryBtn);
    });

    // After retry, the Default Model field should be present
    const modelField = await screen.findByLabelText('Default Model');
    expect(modelField).toHaveValue('gpt-5');
  });
});
