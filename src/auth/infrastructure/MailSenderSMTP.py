class MailSenderSMTP:
    def __init__(self, smtp_server: str, smtp_port: int, smtp_username: str,
                 smtp_password: str, *, use_tls: bool = True, use_auth: bool = True,
                 from_address: str | None = None):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.smtp_username = smtp_username
        self.smtp_password = smtp_password
        self.use_tls = use_tls
        self.use_auth = use_auth
        self.from_address = from_address or smtp_username or "no-reply@localhost"

    def send(self, to: str, subject: str, body: str) -> None:
        import smtplib
        from email.mime.text import MIMEText

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = self.from_address
        msg["To"] = to

        with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
            if self.use_tls:
                server.starttls()
            if self.use_auth:
                server.login(self.smtp_username, self.smtp_password)
            server.sendmail(self.from_address, [to], msg.as_string())
