# Frontend AgentIoT

Frontend inicial de AgentIoT para registro, verificación de correo, autenticación y cierre de sesión. Está construido con Vite, React, TypeScript, Tailwind CSS y Axios.

## Desarrollo

Desde esta carpeta:

```bash
npm install
npm run dev
```

La aplicación queda disponible en `http://localhost:5173`. Durante el desarrollo, Vite redirige `/api` hacia `http://localhost:8001`, donde debe estar ejecutándose la API.

## Pruebas

Ejecuta la suite una vez:

```bash
npm test
```

Para dejar Vitest observando cambios:

```bash
npm run test:watch
```

Las pruebas cubren la configuración del cliente Axios, payloads de autenticación, navegación entre pantallas, registro, login y presentación de errores del backend.

Para usar otra URL:

```bash
VITE_API_URL=https://api.example.com/api/v1 npm run dev
```

## Flujo de autenticación

1. **Registro:** `POST /api/v1/auth/register`.
2. **Verificación:** el usuario introduce el código recibido por correo en `POST /api/v1/auth/verify-email`.
3. **Login:** `POST /api/v1/auth/login` devuelve el access token y establece la cookie HttpOnly de refresh.
4. **Sesión:** el access token se mantiene en memoria y se consulta el perfil con `GET /api/v1/auth/me`.
5. **Refresh y logout:** Axios envía credenciales (`withCredentials`) para `POST /refresh` y `POST /logout`.

El access token no se guarda en `localStorage`; al recargar la página se intenta recuperar la sesión mediante la cookie HttpOnly.

## Dirección visual

- **Identidad:** tecnología confiable y humana; azul petróleo para estructura y verde menta para estados activos y acciones positivas.
- **Paleta:** fondo profundo `#07111F`, superficie clara `#F4F8FA`, texto `#122335`, acento `#6DE0C9`.
- **Semántica:** verde para éxito/conexión, rojo para errores, azul para información y ámbar reservado para advertencias futuras.
- **Tipografía:** una sola familia del sistema, con jerarquía basada en tamaño, peso y espaciado.
- **Geometría:** controles de 9px de radio, tarjetas de 15–20px y espaciado basado en múltiplos de 4px.
- **Interacción:** estados de foco visibles, botones con estados de carga, mensajes con `role="alert"`/`role="status"` y navegación por teclado.
- **Responsive:** la composición de dos columnas se convierte en una vista única en pantallas menores a 760px.

Los estilos globales y tokens visuales viven en [`src/styles.css`](./src/styles.css), mientras que las llamadas HTTP están centralizadas en [`src/api.ts`](./src/api.ts).
