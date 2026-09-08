"""
Email service — sends OTP verification emails via SMTP with structured tracing.

Configuration (via environment variables or .env file):
    SMTP_HOST       SMTP server hostname          (default: smtp.gmail.com)
    SMTP_PORT       SMTP server port              (default: 587)
    SMTP_USER       Sender email address          (or SMTP_USERNAME)
    SMTP_PASSWORD   Sender email password/app key (REQUIRED for real email)
    SMTP_FROM       Display sender name/address   (default: same as SMTP_USER or EMAILS_FROM_EMAIL)
    SMTP_USE_TLS    Use TLS/STARTTLS              (default: true)

If SMTP_USER or SMTP_PASSWORD is not configured, the service falls back
to development mode, printing the OTP to console and logging [EMAIL_TRACE].
"""

import logging
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv

# Ensure .env variables are loaded
load_dotenv()

logger = logging.getLogger(__name__)


def get_smtp_config() -> dict:
    """
    Dynamically read SMTP configuration from environment variables.
    Supports standard aliases (e.g. SMTP_USERNAME, EMAILS_FROM_EMAIL).
    """
    host = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()

    port_raw = os.getenv("SMTP_PORT", "587").strip()
    try:
        port = int(port_raw)
    except ValueError:
        port = 587

    user = (os.getenv("SMTP_USER") or os.getenv("SMTP_USERNAME") or "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip()

    sender = (
        os.getenv("SMTP_FROM") or os.getenv("EMAILS_FROM_EMAIL") or user
    ).strip()

    use_tls_raw = os.getenv("SMTP_USE_TLS", "true").strip().lower()
    use_tls = use_tls_raw in ("true", "1", "yes")

    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "sender": sender,
        "use_tls": use_tls,
    }


def _build_email_html(otp_code: str, username: str) -> str:
    """Return a styled HTML email body for the OTP."""
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Sentinel AI – Email Verification</title>
</head>
<body style="margin:0;padding:0;background:#010b0f;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#010b0f;padding:40px 0;">
    <tr>
      <td align="center">
        <table width="520" cellpadding="0" cellspacing="0"
               style="background:#021218;border:1px solid rgba(0,212,176,0.2);border-radius:12px;overflow:hidden;">

          <!-- Header -->
          <tr>
            <td style="padding:28px 36px 20px;border-bottom:1px solid rgba(0,212,176,0.1);">
              <table width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td>
                    <span style="font-size:11px;letter-spacing:0.15em;color:#3a8a80;font-family:'Courier New',monospace;">
                      SENTINEL AI · BORDER SURVEILLANCE PLATFORM
                    </span><br/>
                    <span style="font-size:22px;font-weight:700;color:#e2f0ef;margin-top:4px;display:block;">
                      Email Verification
                    </span>
                  </td>
                  <td align="right" style="vertical-align:top;">
                    <div style="width:44px;height:44px;background:rgba(0,180,150,0.12);border:1.5px solid rgba(0,210,180,0.5);border-radius:10px;display:flex;align-items:center;justify-content:center;text-align:center;line-height:44px;font-size:20px;">
                      🛡️
                    </div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:28px 36px;">
              <p style="color:#c4ede7;font-size:14px;margin:0 0 16px;">
                Hello, <strong style="color:#e2f0ef;">{username}</strong>,
              </p>
              <p style="color:#8ab8b2;font-size:13px;line-height:1.7;margin:0 0 24px;">
                You have initiated a registration request for the <strong style="color:#c4ede7;">Sentinel AI</strong>
                operator platform. Use the verification code below to complete your account setup.
              </p>

              <!-- OTP Box -->
              <div style="background:#010b0f;border:1px solid rgba(0,212,176,0.3);border-radius:10px;padding:24px;text-align:center;margin:0 0 24px;">
                <p style="color:#5a9e95;font-size:11px;letter-spacing:0.12em;font-family:'Courier New',monospace;margin:0 0 10px;">
                  VERIFICATION CODE
                </p>
                <span style="font-size:42px;font-weight:800;letter-spacing:0.3em;color:#00d4b0;font-family:'Courier New',monospace;">
                  {otp_code}
                </span>
                <p style="color:#3a6e66;font-size:11px;margin:10px 0 0;font-family:'Courier New',monospace;">
                  VALID FOR 15 MINUTES
                </p>
              </div>

              <p style="color:#5a7e78;font-size:12px;line-height:1.6;margin:0;">
                If you did not request this registration, you may safely ignore this email.
                This code will expire automatically.
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:16px 36px;border-top:1px solid rgba(0,212,176,0.08);background:rgba(0,0,0,0.2);">
              <p style="color:#2a5e58;font-size:10px;font-family:'Courier New',monospace;margin:0;letter-spacing:0.06em;">
                LAT: 34.5201° N · LON: 74.8820° E &nbsp;·&nbsp; SENTINEL AI SECURITY GATEWAY
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


def send_otp_email(to_email: str, username: str, otp_code: str) -> None:
    """
    Send a 6-digit OTP verification email to `to_email`.

    If SMTP_USER or SMTP_PASSWORD is not set, prints OTP to console (Development Fallback).
    Otherwise attempts SMTP delivery with explicit [EMAIL_TRACE] logs.
    Raises RuntimeError on delivery failure.
    """
    config = get_smtp_config()
    smtp_user = config["user"]
    smtp_password = config["password"]

    # Development Fallback if credentials not present
    if not smtp_user or not smtp_password:
        logger.warning(
            "[EMAIL_TRACE] Development fallback enabled (SMTP credentials not configured). "
            "OTP for user '%s' (%s): %s",
            username, to_email, otp_code
        )
        print(
            f"\n{'='*60}\n"
            f"  [SENTINEL AI] OTP Verification Code (DEV FALLBACK)\n"
            f"  To      : {to_email}\n"
            f"  Username: {username}\n"
            f"  OTP Code: {otp_code}\n"
            f"  (Valid for 15 minutes)\n"
            f"{'='*60}\n"
        )
        return

    # Build MIME email message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Sentinel AI – Your Verification Code"
    msg["From"] = config["sender"] if config["sender"] else smtp_user
    msg["To"] = to_email

    plain_text = (
        f"Sentinel AI – Email Verification\n\n"
        f"Hello {username},\n\n"
        f"Your verification code is: {otp_code}\n\n"
        f"This code is valid for 15 minutes.\n\n"
        f"If you did not request this, ignore this email.\n"
    )

    msg.attach(MIMEText(plain_text, "plain"))
    msg.attach(MIMEText(_build_email_html(otp_code, username), "html"))

    host = config["host"]
    port = config["port"]
    use_tls = config["use_tls"]

    # Attempt SMTP Delivery
    try:
        context = ssl.create_default_context()

        if port == 465:
            # Direct SSL connection
            try:
                with smtplib.SMTP_SSL(host, port, context=context, timeout=15) as server:
                    server.login(smtp_user, smtp_password)
                    server.sendmail(smtp_user, to_email, msg.as_string())
                logger.info("[EMAIL_TRACE] SMTP email accepted by server for %s", to_email)
            except smtplib.SMTPAuthenticationError as exc:
                logger.error("[EMAIL_TRACE] SMTP authentication failed for user '%s'", smtp_user)
                raise RuntimeError("SMTP authentication failed. Verify username and password.") from exc
            except (smtplib.SMTPConnectError, TimeoutError, OSError) as exc:
                logger.error("[EMAIL_TRACE] SMTP connection failed to %s:%s: %s", host, port, exc)
                raise RuntimeError(f"SMTP connection failed to {host}:{port}") from exc
            except smtplib.SMTPException as exc:
                logger.error("[EMAIL_TRACE] SMTP send failed to %s: %s", to_email, exc)
                raise RuntimeError(f"SMTP send failed: {exc}") from exc
        else:
            # STARTTLS connection (standard port 587 or custom)
            try:
                with smtplib.SMTP(host, port, timeout=15) as server:
                    server.ehlo()
                    if use_tls:
                        server.starttls(context=context)
                        server.ehlo()
                    server.login(smtp_user, smtp_password)
                    server.sendmail(smtp_user, to_email, msg.as_string())
                logger.info("[EMAIL_TRACE] SMTP email accepted by server for %s", to_email)
            except smtplib.SMTPAuthenticationError as exc:
                logger.error("[EMAIL_TRACE] SMTP authentication failed for user '%s'", smtp_user)
                raise RuntimeError("SMTP authentication failed. Verify username and App Password.") from exc
            except (smtplib.SMTPConnectError, TimeoutError, OSError) as exc:
                logger.error("[EMAIL_TRACE] SMTP connection failed to %s:%s: %s", host, port, exc)
                raise RuntimeError(f"SMTP connection failed to {host}:{port}") from exc
            except smtplib.SMTPException as exc:
                logger.error("[EMAIL_TRACE] SMTP send failed to %s: %s", to_email, exc)
                raise RuntimeError(f"SMTP send failed: {exc}") from exc

    except RuntimeError:
        raise
    except Exception as exc:
        logger.error("[EMAIL_TRACE] SMTP send failed: %s", exc)
        raise RuntimeError(f"Failed to deliver verification email: {exc}") from exc
