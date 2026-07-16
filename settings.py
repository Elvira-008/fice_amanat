import os


def env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name, default):
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return int(value)


def env_float(name, default):
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return float(value)


FACE_DIR = os.getenv("FACE_DIR", "face_database")
SCREENSHOTS_DIR = os.getenv("SCREENSHOTS_DIR", "screenshots")
DB_NAME = os.getenv("DB_NAME", "school.db")

APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = env_int("APP_PORT", 8080)
APP_AUTO_PORT = env_bool("APP_AUTO_PORT", True)
PRODUCTION = env_bool("PRODUCTION", False)
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin2026")

# Мугалим панелине кирүү паролу. Бул жерден өзгөртсө болот:
TEACHER_PASSWORD = os.getenv("TEACHER_PASSWORD", "mektep2026")

MAX_UPLOAD_BYTES = env_int("MAX_UPLOAD_BYTES", 5 * 1024 * 1024)
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "http://127.0.0.1:8000,http://localhost:8000").split(",")
    if origin.strip()
]

UNKNOWN_NAME = "not_in_database"

# RECOGNITION_WIDTH = env_int("RECOGNITION_WIDTH", 640)
#
# RECOGNITION_INTERVAL_SECONDS = env_float("RECOGNITION_INTERVAL_SECONDS", 0.02)

RECOGNITION_THRESHOLD = env_float("RECOGNITION_THRESHOLD", 0.48)
RECOGNITION_MARGIN = env_float("RECOGNITION_MARGIN", 0.04)
FACE_MODEL_NAME = os.getenv("FACE_MODEL_NAME", "buffalo_l")

FACE_DETECTION_PROFILES = (
    ("fast", 640),
    ("accurate", 800),
    ("fallback", 960),
)
# ... жогорудагы коддор ...
RECOGNITION_WIDTH = 320  # 640дан 320га өзгөртүлдү
RECOGNITION_INTERVAL_SECONDS = 0.2  # 0.02ден 0.2ге өзгөртүлдү
# ...
CAMERA_FPS = 15  # 30дан 15ке өзгөртүлдү
CAMERA_READ_SLEEP_SECONDS = 0.03  # 0.001ден 0.03кө өзгөртүлдү
JPEG_QUALITY = 40  # 60тан 40ка өзгөртүлдү
# ... төмөнкү коддор ...
LIVENESS_REQUIRED_SAMPLES = 2
LIVENESS_WINDOW_SECONDS = 2.0
LIVENESS_MIN_FACE_MOTION = 0.001
LIVENESS_MAX_FACE_MOTION = 0.22
LIVENESS_MIN_FACE_RATIO = 0.008
LIVENESS_MIN_TEXTURE_SCORE = 6.0
TEACHER_NOTIFICATION_LIMIT = env_int("TEACHER_NOTIFICATION_LIMIT", 100)
ATTENDANCE_UPDATE_INTERVAL_MINUTES = env_int("ATTENDANCE_UPDATE_INTERVAL_MINUTES", 15)
LOW_LIGHT_MEAN_THRESHOLD = env_int("LOW_LIGHT_MEAN_THRESHOLD", 115)
LOW_LIGHT_GAMMA = env_float("LOW_LIGHT_GAMMA", 0.58)
CAMERA_FPS = env_int("CAMERA_FPS", 30)
CAMERA_READ_SLEEP_SECONDS = env_float("CAMERA_READ_SLEEP_SECONDS", 0.001)
JPEG_QUALITY = env_int("JPEG_QUALITY", 60)

CAMERA_INDEXES = {
    "keldi": 1,
    "ketti": 0,
}
