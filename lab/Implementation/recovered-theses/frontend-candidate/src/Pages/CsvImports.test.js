import React from 'react';
import '@testing-library/jest-dom';
import { render, screen, fireEvent, waitFor, within, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import axios from 'axios';
import CsvImports, { progressOf } from './CsvImports';
jest.mock('axios', () => ({ get: jest.fn(), post: jest.fn() }));
const job = { id: '11111111-1111-4111-8111-111111111111', filename: 'policies.csv', status: 'ready',
  total_records: 3, processed_records: 3, valid_records: 1, duplicate_records: 1, invalid_records: 1,
  activated_records: 0, publication: { stored: 0, published: 0, existing_unverified: 0 },
  created_at: '2026-10-30T10:00:00Z', updated_at: '2026-10-30T10:00:01Z' };
beforeEach(() => {
  localStorage.setItem('token', 'session-jwt');
  window.io = jest.fn(() => ({ on: jest.fn(), disconnect: jest.fn() }));
  axios.get.mockImplementation(url => Promise.resolve({ data: url.endsWith('/preview')
    ? { rows: [{ domain: 'example.com', row_number: 2, payload: { ip_add: null, category: 'Other' } }], failures: [{ row_number: 4, domain: '', error_message: 'Domain is required' }] }
    : { jobs: [job] } }));
  axios.post.mockResolvedValue({ data: { job: { ...job, status: 'activating', updated_at: '2026-10-30T10:00:02Z' } } });
});
afterEach(() => { jest.clearAllMocks(); delete window.io; localStorage.clear(); });
test('validation and activation progress use different denominators', () => {
  expect(progressOf(job)).toBe(100);
  expect(progressOf({ ...job, status: 'activating', valid_records: 4, activated_records: 1 })).toBe(25);
  expect(progressOf({ ...job, status: 'failed', error_phase: 'activation', valid_records: 4, activated_records: 1 })).toBe(25);
  expect(progressOf({ ...job, status: 'removing' })).toBe(0);
  expect(progressOf({ ...job, status: 'removed' })).toBe(100);
});
test('existing JWT is sent to API and invalid rows require explicit review and confirmation', async () => {
  render(<MemoryRouter><CsvImports /></MemoryRouter>);
  await screen.findByRole('heading', { name: 'policies.csv' });
  const review = screen.getByRole('button', { name: 'Review activation' }); expect(review).toBeDisabled();
  await act(async () => { fireEvent.click(screen.getByRole('checkbox')); });
  await waitFor(() => expect(screen.getByRole('button', { name: 'Review activation' })).not.toBeDisabled());
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Review activation' })); });
  const dialog = screen.getByRole('dialog');
  expect(within(dialog).getByText(/Activate 1 unique valid policies/)).toBeInTheDocument();
  expect(axios.post).not.toHaveBeenCalled();
  await act(async () => { fireEvent.click(within(dialog).getByRole('button', { name: 'Confirm activation' })); });
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith(expect.stringContaining('/activate'),
    { confirmation: 'ACTIVATE', acceptInvalid: true }, expect.objectContaining({ headers: { Authorization: 'Bearer session-jwt' } })));
});
test('preview shows domain-only rules and explains that publication is not enforcement', async () => {
  render(<MemoryRouter><CsvImports /></MemoryRouter>);
  expect(await screen.findByText('Domain only')).toBeInTheDocument();
  expect(screen.getByText(/does not yet receive a Policy Server enforcement acknowledgement/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Download failed rows' })).toBeInTheDocument();
});
