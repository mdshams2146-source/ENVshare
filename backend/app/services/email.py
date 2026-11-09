import os
import smtplib
from email.message import EmailMessage
from pathlib import Path
from dotenv import load_dotenv

# Load variables deterministically from backend/.env
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE_PATH = BASE_DIR / ".env"
if ENV_FILE_PATH.exists():
    load_dotenv(ENV_FILE_PATH)
else:
    load_dotenv()

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")

def _get_smtp_port() -> int:
    port_val = os.getenv("SMTP_PORT", "587")
    try:
        return int(port_val)
    except (ValueError, TypeError):
        return 587

SMTP_PORT = _get_smtp_port()
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://en-vshare.vercel.app").rstrip("/")


def send_password_reset_email(to_email: str, reset_token: str):
    """Sends a password reset email containing a secure one-time link in hash fragment."""
    reset_url = f"{FRONTEND_URL}/#reset_token={reset_token}"


    msg = EmailMessage()
    msg["Subject"] = "Reset Your EnvShare Password"
    msg["From"] = SMTP_USER
    msg["To"] = to_email

    # Plain text version (fallback)
    msg.set_content(
        f"Hello,\n\n"
        f"You requested to reset your password for EnvShare.\n"
        f"Click the link below to set a new password:\n{reset_url}\n\n"
        f"This link expires in 15 minutes. If you did not request this, please ignore this email."
    )

    # HTML formatted version
    msg.add_alternative(
        f"""
        <html>
          <body style="font-family: Arial, sans-serif; background-color: #0f172a; color: #f8fafc; padding: 24px;">
            <div style="max-width: 500px; margin: 0 auto; background-color: #1e293b; padding: 24px; border-radius: 8px; border: 1px solid #334155;">
              <h2 style="color: #38bdf8; margin-top: 0;">EnvShare Password Reset</h2>
              <p style="color: #cbd5e1; font-size: 15px; line-height: 1.5;">
                We received a request to reset your password. Click the button below to choose a new password:
              </p>
              <div style="text-align: center; margin: 28px 0;">
                <a href="{reset_url}" style="background-color: #0284c7; color: #ffffff; text-decoration: none; padding: 12px 24px; border-radius: 6px; font-weight: bold; display: inline-block;">
                  Reset Password
                </a>
              </div>
              <p style="color: #94a3b8; font-size: 13px;">
                This link will expire in <strong>15 minutes</strong>. If you did not request a password reset, you can safely ignore this email.
              </p>
            </div>
          </body>
        </html>
        """,
        subtype="html",
    )

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)