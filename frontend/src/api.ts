import axios from 'axios'

export type User = { id: string; username: string; email: string; status: string; created_at: string }
export type TokenResponse = { access_token: string; token_type: string; expires_in: number }
export type RegisterResponse = User & { verification_required: boolean; message: string }
export type Broker = {
  id: string; tenant_id: string; name: string; host: string | null; port: number | null
  created_at: string; status: 'pending' | 'connected' | 'offline' | string
  sensor_id: string | null; last_seen: string | null
}
export type BrokerCreated = Broker & { enrollment_key: string; install_command: string }
export type AnalyticalReport = Record<string, unknown>
export type NaturalReport = { report: string }

type ApiErrorBody = { error?: { code?: string; message?: string } }

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? '/api/v1',
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
})

export function getApiError(error: unknown, fallback: string): string {
  if (axios.isAxiosError<ApiErrorBody>(error)) return error.response?.data?.error?.message ?? fallback
  return fallback
}

export async function register(username: string, email: string, password: string) {
  const { data } = await api.post<RegisterResponse>('/auth/register', { username, email, password }); return data
}
export async function verifyEmail(email: string, code: string) {
  const { data } = await api.post<User>('/auth/verify-email', { email, code }); return data
}
export async function resendVerification(email: string) {
  const { data } = await api.post<{ message: string }>('/auth/resend-verification', { email }); return data
}
export async function login(email: string, password: string) {
  const { data } = await api.post<TokenResponse>('/auth/login', { email, password }); return data
}
export async function refresh() {
  const { data } = await api.post<TokenResponse>('/auth/refresh'); return data
}
export async function logout() { await api.post('/auth/logout') }

function authHeaders(token: string) { return { headers: { Authorization: `Bearer ${token}` } } }
export async function getMe(token: string) {
  const { data } = await api.get<User>('/auth/me', authHeaders(token)); return data
}
export async function listBrokers(token: string) {
  const { data } = await api.get<Broker[]>('/brokers', authHeaders(token)); return data
}
export async function createBroker(token: string, payload: { name: string; host?: string; port?: number }) {
  const { data } = await api.post<BrokerCreated>('/brokers', payload, authHeaders(token)); return data
}
export async function deleteBroker(token: string, brokerId: string) {
  await api.delete(`/brokers/${brokerId}`, authHeaders(token))
}
export async function rotateBrokerKey(token: string, brokerId: string) {
  const { data } = await api.post<{ enrollment_key: string; install_command: string }>(
    `/brokers/${brokerId}/enrollment-key`, undefined, authHeaders(token),
  ); return data
}
export async function getAnalyticalReport(token: string, brokerId?: string) {
  const { data } = await api.get<AnalyticalReport>('/reports/analytics', {
    ...authHeaders(token),
    params: brokerId ? { broker_id: brokerId } : undefined,
  })
  return data
}
export async function generateNaturalReport(token: string, brokerId?: string) {
  const { data } = await api.post<NaturalReport>(
    '/reports',
    brokerId ? { broker_id: brokerId } : {},
    authHeaders(token),
  )
  return data
}
