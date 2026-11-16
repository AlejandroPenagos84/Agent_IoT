import { FormEvent, useEffect, useState } from 'react'
import {
  getApiError,
  getMe,
  login,
  logout,
  refresh,
  register,
  resendVerification,
  User,
  verifyEmail,
} from './api'

type View = 'login' | 'register' | 'verify' | 'home'

function Logo() {
  return (
    <div className="brand" aria-label="AgentIoT">
      <span className="brand-mark" aria-hidden="true">
        ◈
      </span>
      <span>Agent<span className="brand-accent">IoT</span></span>
    </div>
  )
}

function ArrowIcon() {
  return <span aria-hidden="true">→</span>
}

function Message({ kind, children }: { kind: 'error' | 'success' | 'info'; children: string }) {
  return (
    <div className={`message message-${kind}`} role={kind === 'error' ? 'alert' : 'status'}>
      <span aria-hidden="true">{kind === 'error' ? '!' : kind === 'success' ? '✓' : 'i'}</span>
      {children}
    </div>
  )
}

function Field({
  label,
  id,
  type = 'text',
  placeholder,
  autoComplete,
  minLength,
  maxLength,
}: {
  label: string
  id: string
  type?: string
  placeholder: string
  autoComplete?: string
  minLength?: number
  maxLength?: number
}) {
  return (
    <label className="field" htmlFor={id}>
      <span>{label}</span>
      <input
        id={id}
        name={id}
        type={type}
        placeholder={placeholder}
        autoComplete={autoComplete}
        minLength={minLength}
        maxLength={maxLength}
        required
      />
    </label>
  )
}

function AuthShell({
  children,
  view,
  onChangeView,
}: {
  children: React.ReactNode
  view: View
  onChangeView: (view: View) => void
}) {
  return (
    <main className="auth-layout">
      <section className="hero-panel">
        <div className="hero-content">
          <Logo />
          <div className="hero-copy">
            <p className="eyebrow">Plataforma de monitoreo inteligente</p>
            <h1>Observa. Entiende. <em>Actúa.</em></h1>
            <p className="hero-description">
              Una visión clara de tus dispositivos IoT para tomar mejores decisiones, más rápido.
            </p>
          </div>
          <div className="signal-card" aria-hidden="true">
            <div className="signal-header"><span className="status-dot" /> Sistema operativo <span>●●●</span></div>
            <div className="signal-chart">
              <span style={{ height: '34%' }} /><span style={{ height: '51%' }} /><span style={{ height: '43%' }} />
              <span style={{ height: '68%' }} /><span style={{ height: '57%' }} /><span style={{ height: '82%' }} />
              <span style={{ height: '73%' }} /><span style={{ height: '94%' }} /><span style={{ height: '78%' }} />
            </div>
            <div className="signal-footer"><strong>99.8%</strong><span>Disponibilidad de red</span></div>
          </div>
          <p className="hero-footer">Datos seguros. Decisiones confiables.</p>
        </div>
      </section>
      <section className="form-panel">
        <div className="mobile-logo"><Logo /></div>
        {children}
        {view !== 'verify' && view !== 'home' && (
          <p className="switch-copy">
            {view === 'login' ? '¿Aún no tienes una cuenta?' : '¿Ya tienes una cuenta?'}{' '}
            <button type="button" className="text-button" onClick={() => onChangeView(view === 'login' ? 'register' : 'login')}>
              {view === 'login' ? 'Regístrate' : 'Inicia sesión'}
            </button>
          </p>
        )}
      </section>
    </main>
  )
}

function App() {
  const [view, setView] = useState<View>('login')
  const [user, setUser] = useState<User | null>(null)
  const [emailForVerification, setEmailForVerification] = useState('')
  const [token, setToken] = useState('')
  const [notice, setNotice] = useState<{ kind: 'error' | 'success' | 'info'; text: string } | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    refresh()
      .then(({ access_token }) => getMe(access_token).then((me) => {
        setToken(access_token)
        setUser(me)
        setView('home')
      }))
      .catch(() => undefined)
  }, [])

  async function submit(action: () => Promise<void>) {
    setLoading(true)
    setNotice(null)
    try {
      await action()
    } catch (error) {
      setNotice({ kind: 'error', text: getApiError(error, 'No pudimos completar la operación. Inténtalo de nuevo.') })
    } finally {
      setLoading(false)
    }
  }

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    await submit(async () => {
      const session = await login(String(form.get('email')), String(form.get('password')))
      const me = await getMe(session.access_token)
      setToken(session.access_token)
      setUser(me)
      setView('home')
    })
  }

  async function handleRegister(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    await submit(async () => {
      const result = await register(String(form.get('username')), String(form.get('email')), String(form.get('password')))
      setEmailForVerification(result.email)
      setNotice({ kind: 'success', text: 'Cuenta creada. Revisa tu correo para obtener el código.' })
      setView('verify')
    })
  }

  async function handleVerify(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    await submit(async () => {
      await verifyEmail(emailForVerification, String(form.get('code')))
      setNotice({ kind: 'success', text: 'Correo verificado. Ya puedes iniciar sesión.' })
      setView('login')
    })
  }

  async function handleLogout() {
    await submit(async () => {
      await logout()
      setToken('')
      setUser(null)
      setView('login')
    })
  }

  if (view === 'home' && user) {
    return (
      <main className="home-layout">
        <header className="topbar"><Logo /><button className="quiet-button" onClick={handleLogout}>Cerrar sesión</button></header>
        <section className="welcome-card">
          <p className="eyebrow">Sesión activa</p>
          <h1>Hola, {user.username}.</h1>
          <p>Tu espacio de monitoreo está listo para comenzar.</p>
          <div className="token-note"><span className="status-dot" /> Conexión segura establecida</div>
        </section>
      </main>
    )
  }

  return (
    <AuthShell view={view} onChangeView={(nextView) => { setNotice(null); setView(nextView) }}>
      <div className="form-container">
        {view === 'login' && (
          <>
            <div className="form-heading"><p className="eyebrow">Bienvenido de nuevo</p><h2>Inicia sesión</h2><p>Accede a tu centro de control IoT.</p></div>
            {notice && <Message kind={notice.kind}>{notice.text}</Message>}
            <form onSubmit={handleLogin}>
              <Field label="Correo electrónico" id="email" type="email" placeholder="tu@correo.com" autoComplete="email" />
              <Field label="Contraseña" id="password" type="password" placeholder="Tu contraseña" autoComplete="current-password" />
              <button className="primary-button" disabled={loading}>{loading ? 'Iniciando sesión…' : <>Entrar <ArrowIcon /></>}</button>
            </form>
          </>
        )}
        {view === 'register' && (
          <>
            <div className="form-heading"><p className="eyebrow">Comienza ahora</p><h2>Crea tu cuenta</h2><p>Configura tu acceso en menos de un minuto.</p></div>
            {notice && <Message kind={notice.kind}>{notice.text}</Message>}
            <form onSubmit={handleRegister}>
              <Field label="Nombre de usuario" id="username" placeholder="Cómo te llamaremos" autoComplete="username" minLength={3} maxLength={32} />
              <Field label="Correo electrónico" id="email" type="email" placeholder="tu@correo.com" autoComplete="email" />
              <Field label="Contraseña" id="password" type="password" placeholder="Mínimo 8 caracteres" autoComplete="new-password" minLength={8} maxLength={128} />
              <button className="primary-button" disabled={loading}>{loading ? 'Creando cuenta…' : <>Crear cuenta <ArrowIcon /></>}</button>
            </form>
            <p className="terms-copy">Al continuar aceptas nuestros términos de uso y política de privacidad.</p>
          </>
        )}
        {view === 'verify' && (
          <>
            <div className="form-heading"><p className="eyebrow">Un último paso</p><h2>Verifica tu correo</h2><p>Enviamos un código de 6 dígitos a <strong>{emailForVerification}</strong>.</p></div>
            {notice && <Message kind={notice.kind}>{notice.text}</Message>}
            <form onSubmit={handleVerify}>
              <Field label="Código de verificación" id="code" placeholder="000000" autoComplete="one-time-code" minLength={6} maxLength={6} />
              <button className="primary-button" disabled={loading}>{loading ? 'Verificando…' : <>Verificar correo <ArrowIcon /></>}</button>
            </form>
            <button className="secondary-button" disabled={loading} onClick={() => submit(async () => {
              await resendVerification(emailForVerification)
              setNotice({ kind: 'success', text: 'Si la cuenta está pendiente, enviamos un nuevo código.' })
            })}>Reenviar código</button>
            <button className="back-button" onClick={() => setView('register')}>← Cambiar correo</button>
          </>
        )}
      </div>
    </AuthShell>
  )
}

export default App
