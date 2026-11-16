import axios from 'axios'

export type User = {
  id: string
  username: string
  email: string
  status: string
  created_at: string
}

export type TokenResponse = {
  access_token: string
  token_type: string
  expires_in: number
}

export type RegisterResponse = User & {
  verification_required: boolean
  message: string
}

type ApiErrorBody = {
  error?: {
    code?: string
    message?: string
  }
}

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? '/api/v1',
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
})

export function getApiError(error: unknown, fallback: string): string {
  if (axios.isAxiosError<ApiErrorBody>(error)) {
    return error.response?.data?.error?.message ?? fallback
  }
  return fallback
}

export async function register(username: string, email: string, password: string) {
  const { data } = await api.post<RegisterResponse>('/auth/register', {
    username,
    email,
    password,
  })
  return data
}

export async function verifyEmail(email: string, code: string) {
  const { data } = await api.post<User>('/auth/verify-email', { email, code })
  return data
}

export async function resendVerification(email: string) {
  const { data } = await api.post<{ message: string }>('/auth/resend-verification', { email })
  return data
}

export async function login(email: string, password: string) {
  const { data } = await api.post<TokenResponse>('/auth/login', { email, password })
  return data
}

export async function refresh() {
  const { data } = await api.post<TokenResponse>('/auth/refresh')
  return data
}

export async function logout() {
  await api.post('/auth/logout')
}

export async function getMe(token: string) {
  const { data } = await api.get<User>('/auth/me', {
    headers: { Authorization: `Bearer ${token}` },
  })
  return data
}
