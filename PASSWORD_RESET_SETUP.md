# StudyNaija password reset email setup

The password reset feature is already included in the application.

It uses SMTP to send a one-time reset link. Passwords are never emailed.

## Render environment variables

Add these variables to the StudyNaija Render service:

```text
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=YOUR_GMAIL_ADDRESS
SMTP_PASSWORD=YOUR_GOOGLE_APP_PASSWORD
MAIL_FROM=YOUR_GMAIL_ADDRESS
SMTP_USE_SSL=false
```

Do not put the real values in GitHub.

## Gmail

Use a Google App Password for `SMTP_PASSWORD`, not your normal Gmail password.

Your Google account must have 2-Step Verification enabled before an App Password can be created.

## What users will experience

1. Click `Forgot your password?` on the login page.
2. Enter their email address.
3. StudyNaija sends a secure reset link.
4. The link expires after 30 minutes.
5. The link can only be used once.
6. The user chooses a new password.
7. StudyNaija stores the new password using the existing secure password hashing system.

The system also uses the same public response whether an email exists or not, which helps prevent account-enumeration attacks.
