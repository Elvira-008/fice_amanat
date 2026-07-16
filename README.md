# School Face ID

Backend and admin panel for a school attendance system with face recognition.

## Run locally

```powershell
python -m pip install -r requirements.txt
python admin_panel.py
```

The server prints two addresses:

- `http://127.0.0.1:8000` for this computer
- `http://<LAN-IP>:8000` for phones in the same Wi-Fi network

## Mobile app architecture

The real Android/iPhone app should be a separate mobile client. This Python
project remains the backend:

- face recognition
- camera streams
- SQLite database
- admin panel
- JSON API for the mobile app

Recommended mobile stack: Flutter.

## Important files

- `admin_panel.py` - FastAPI application and web/API routes
- `camera_service.py` - camera capture and face recognition
- `database.py` - SQLite access layer
- `views.py` - admin panel HTML
- `settings.py` - camera indexes and recognition settings
- `fase_database.py` - one-time photo import helper

Do not delete `school.db`, `face_database`, or `screenshots` unless you are sure
you want to remove project data.

## Production checklist

Before using this with real students, copy `.env.example` values into your
server environment and change at least:

```powershell
$env:PRODUCTION="1"
$env:APP_PORT="8000"
$env:APP_AUTO_PORT="0"
$env:TEACHER_PASSWORD="your-strong-teacher-password"
$env:ADMIN_PASSWORD="your-strong-admin-password"
$env:ADMIN_TOKEN="your-long-random-admin-token"
$env:ALLOWED_ORIGINS="http://127.0.0.1:8000,http://localhost:8000"
python admin_panel.py
```

For the camera page, use `http://127.0.0.1:8000/camera` on the same computer.
Browsers allow camera access on `127.0.0.1`, `localhost`, or HTTPS. If you open
the page from another device by LAN IP, use HTTPS in production.

Back up these paths every day:

- `school.db`
- `face_database/`
- `screenshots/`

Operational notes:

- One USB webcam plus the laptop camera is supported from `/camera`.
- SQLite is configured with WAL and indexes for the expected school workload.
- If `ADMIN_TOKEN` is set, destructive admin actions require `?admin_token=...`
  or an `X-Admin-Token` header.
