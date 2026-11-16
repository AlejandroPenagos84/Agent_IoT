import { describe, expect, it, vi } from 'vitest'
import { api, getApiError, getMe, login, register, verifyEmail } from './api'

describe('auth API client', () => {
  it('configures credentials for the HttpOnly refresh cookie', () => {
    expect(api.defaults.withCredentials).toBe(true)
    expect(api.defaults.baseURL).toBe('/api/v1')
  })

  it('sends registration data to the auth endpoint', async () => {
    const response = { id: 'u1', email: 'ana@example.com' }
    const post = vi.spyOn(api, 'post').mockResolvedValueOnce({ data: response } as never)

    await expect(register('ana', 'ana@example.com', 'secreto123')).resolves.toEqual(response)
    expect(post).toHaveBeenCalledWith('/auth/register', {
      username: 'ana',
      email: 'ana@example.com',
      password: 'secreto123',
    })
  })

  it('sends a bearer token when requesting the current user', async () => {
    const response = { id: 'u1', username: 'ana' }
    const get = vi.spyOn(api, 'get').mockResolvedValueOnce({ data: response } as never)

    await expect(getMe('access-token')).resolves.toEqual(response)
    expect(get).toHaveBeenCalledWith('/auth/me', {
      headers: { Authorization: 'Bearer access-token' },
    })
  })

  it('extracts a backend error message and uses the fallback otherwise', () => {
    const error = {
      isAxiosError: true,
      response: { data: { error: { message: 'Correo inválido' } } },
    }

    expect(getApiError(error, 'Error genérico')).toBe('Correo inválido')
    expect(getApiError(new Error('network'), 'Error genérico')).toBe('Error genérico')
  })

  it('posts login and email verification payloads', async () => {
    const post = vi.spyOn(api, 'post')
      .mockResolvedValueOnce({ data: { access_token: 'token' } } as never)
      .mockResolvedValueOnce({ data: { id: 'u1' } } as never)

    await login('ana@example.com', 'secreto123')
    await verifyEmail('ana@example.com', '123456')

    expect(post).toHaveBeenNthCalledWith(1, '/auth/login', {
      email: 'ana@example.com',
      password: 'secreto123',
    })
    expect(post).toHaveBeenNthCalledWith(2, '/auth/verify-email', {
      email: 'ana@example.com',
      code: '123456',
    })
  })
})
