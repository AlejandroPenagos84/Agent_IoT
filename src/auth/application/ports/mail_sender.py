from typing import Protocol


class MailSender(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...
