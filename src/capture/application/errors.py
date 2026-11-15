"""Errores de la aplicación de captura."""


class EnrollmentError(RuntimeError):
    """La API rechazó la clave de inscripción o el secreto del sensor."""


class CaptureStartError(RuntimeError):
    """La fuente de paquetes no pudo arrancar; ``exit_code`` es el código de salida."""

    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.exit_code = exit_code
