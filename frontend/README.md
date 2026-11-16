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

También cubren el cliente de gestión de brokers, incluyendo el envío autenticado del payload de creación.

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

## Gestión de brokers

Después de iniciar sesión, la pantalla principal muestra la sección **Brokers MQTT**. Desde allí puedes:

1. Crear un broker indicando su nombre y, opcionalmente, host y puerto.
2. Copiar la clave de enrolamiento y el comando Docker que la API devuelve al crear el broker. La clave se muestra una sola vez.
3. Consultar la lista de brokers registrados y su estado (`Pendiente`, `Conectado` o `Sin conexión`).
4. Renovar la clave de un broker. La clave anterior deja de funcionar y se muestra un nuevo comando de instalación.
5. Eliminar un broker después de confirmar la operación.

Para probar el flujo completo:

```bash
cd frontend
npm install
npm run dev
```

Con la API ejecutándose en `http://localhost:8001`, abre `http://localhost:5173`, crea o utiliza una cuenta, inicia sesión y entra en **Brokers MQTT**. El proxy de Vite redirige las solicitudes `/api` a la API local.

La sección utiliza estos endpoints autenticados:

- `GET /api/v1/brokers`: listar brokers.
- `POST /api/v1/brokers`: crear un broker.
- `POST /api/v1/brokers/{broker_id}/enrollment-key`: renovar la clave.
- `DELETE /api/v1/brokers/{broker_id}`: eliminar un broker.

## Reportes

La pestaña **Reportes** del inicio permite elegir un broker o consultar todos los datos del tenant. Incluye:

- **Datos del reporte:** consulta el resumen estructurado mediante `GET /api/v1/reports/analytics`.
- **Resumen en lenguaje natural:** genera una explicación mediante `POST /api/v1/reports`.

Ambas acciones muestran estados de carga, errores del backend y el resultado dentro de la pantalla.

Si la API está publicada en otra dirección, configura la URL antes de iniciar Vite:

```bash
VITE_API_URL=https://api.example.com/api/v1 npm run dev
```

## Dirección visual

- **Identidad:** tecnología confiable y humana; azul petróleo para estructura y verde menta para estados activos y acciones positivas.
- **Paleta:** fondo profundo `#07111F`, superficie clara `#F4F8FA`, texto `#122335`, acento `#6DE0C9`.
- **Semántica:** verde para éxito/conexión, rojo para errores, azul para información y ámbar reservado para advertencias futuras.
- **Tipografía:** una sola familia del sistema, con jerarquía basada en tamaño, peso y espaciado.
- **Geometría:** controles de 9px de radio, tarjetas de 15–20px y espaciado basado en múltiplos de 4px.
- **Interacción:** estados de foco visibles, botones con estados de carga, mensajes con `role="alert"`/`role="status"` y navegación por teclado.
- **Responsive:** la composición de dos columnas se convierte en una vista única en pantallas menores a 760px.

Los estilos globales y tokens visuales viven en [`src/styles.css`](./src/styles.css), mientras que las llamadas HTTP están centralizadas en [`src/api.ts`](./src/api.ts).
