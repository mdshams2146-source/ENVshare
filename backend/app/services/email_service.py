import resend
from app.core.config import settings

if settings.RESEND_API_KEY:
    resend.api_key = settings.RESEND_API_KEY

def send_project_invite_email(to_email: str, project_name: str, inviter_name: str):
    """Sends an invitation notification using Resend."""
    if not settings.RESEND_API_KEY:
        print(f"[MOCK EMAIL] To: {to_email} | Invited to {project_name} by {inviter_name}")
        return

    try:
        resend.Emails.send({
            "from": settings.RESEND_FROM_EMAIL,
            "to": to_email,
            "subject": f"You've been invited to '{project_name}' on EnvShare",
            "html": f"<p>Hello!</p><p><strong>{inviter_name}</strong> has granted you access to the project <strong>{project_name}</strong> on EnvShare.</p><p>Log in to access and manage project environment variables.</p>"
        })
    except Exception as e:
        print(f"[Resend Email Error]: {e}")