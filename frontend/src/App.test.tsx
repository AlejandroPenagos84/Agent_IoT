import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import * as authApi from './api'

vi.mock('./api', async () => {
  const actual = await vi.importActual<typeof import('./api')>('./api')
  return {
    ...actual,
    refresh: vi.fn(),
    getMe: vi.fn(),
    login: vi.fn(),
    register: vi.fn(),
    verifyEmail: vi.fn(),
    resendVerification: vi.fn(),
    logout: vi.fn(),
  }
})

describe('authentication screens', () => {
  afterEach(() => {
    cleanup()
  })

  beforeEach(() => {
    vi.mocked(authApi.refresh).mockRejectedValue(new Error('No active session'))
    vi.mocked(authApi.getMe).mockReset()
    vi.mocked(authApi.login).mockReset()
    vi.mocked(authApi.register).mockReset()
    vi.mocked(authApi.verifyEmail).mockReset()
    vi.mocked(authApi.resendVerification).mockReset()
    vi.mocked(authApi.logout).mockReset()
  })

  it('shows the login form and navigates to registration', async () => {
    const user = userEvent.setup()
    render(<App />)

    expect(screen.getByRole('heading', { name: 'Inicia sesión' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Regístrate' }))

    expect(screen.getByRole('heading', { name: 'Crea tu cuenta' })).toBeInTheDocument()
  })

  it('submits registration and opens email verification', async () => {
    const user = userEvent.setup()
    vi.mocked(authApi.register).mockResolvedValue({
      id: 'u1',
      username: 'ana',
      email: 'ana@example.com',
      status: 'pending',
      created_at: '2026-01-01',
      verification_required: true,
      message: 'Check your email',
    })
    render(<App />)
    await user.click(screen.getByRole('button', { name: 'Regístrate' }))
    await user.type(screen.getByLabelText('Nombre de usuario'), 'ana')
    await user.type(screen.getByLabelText('Correo electrónico'), 'ana@example.com')
    await user.type(screen.getByLabelText('Contraseña'), 'secreto123')
    await user.click(screen.getByRole('button', { name: /Crear cuenta/ }))

    expect(await screen.findByRole('heading', { name: 'Verifica tu correo' })).toBeInTheDocument()
    expect(screen.getByText('ana@example.com')).toBeInTheDocument()
    expect(authApi.register).toHaveBeenCalledWith('ana', 'ana@example.com', 'secreto123')
  })

  it('logs in and displays the authenticated user', async () => {
    const user = userEvent.setup()
    vi.mocked(authApi.login).mockResolvedValue({
      access_token: 'access-token',
      token_type: 'bearer',
      expires_in: 900,
    })
    vi.mocked(authApi.getMe).mockResolvedValue({
      id: 'u1',
      username: 'ana',
      email: 'ana@example.com',
      status: 'active',
      created_at: '2026-01-01',
    })
    render(<App />)
    await user.type(screen.getByLabelText('Correo electrónico'), 'ana@example.com')
    await user.type(screen.getByLabelText('Contraseña'), 'secreto123')
    await user.click(screen.getByRole('button', { name: /Entrar/ }))

    expect(await screen.findByRole('heading', { name: 'Hola, ana.' })).toBeInTheDocument()
    expect(authApi.getMe).toHaveBeenCalledWith('access-token')
  })

  it('renders the backend error in the login form', async () => {
    const user = userEvent.setup()
    vi.mocked(authApi.login).mockRejectedValue({
      isAxiosError: true,
      response: { data: { error: { message: 'Credenciales inválidas' } } },
    })
    render(<App />)
    await user.type(screen.getByLabelText('Correo electrónico'), 'ana@example.com')
    await user.type(screen.getByLabelText('Contraseña'), 'incorrecta')
    await user.click(screen.getByRole('button', { name: /Entrar/ }))

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Credenciales inválidas'))
  })
})
