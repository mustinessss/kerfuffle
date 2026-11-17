import smtplib
from email.message import EmailMessage

from app.core.config import Settings


def smtp_is_configured(settings: Settings) -> bool:
    return all((settings.smtp_host, settings.smtp_user, settings.smtp_password, settings.smtp_from))


def send_email(settings: Settings, recipient: str, subject: str, body: str) -> None:
    if not smtp_is_configured(settings):
        raise RuntimeError("SMTP is not configured.")

    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    if settings.smtp_use_tls and settings.smtp_port == 465:
        client_context = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=15)
    else:
        client_context = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)
    with client_context as client:
        if settings.smtp_use_tls and settings.smtp_port != 465:
            client.starttls()
        client.login(settings.smtp_user, settings.smtp_password)
        client.send_message(message)
