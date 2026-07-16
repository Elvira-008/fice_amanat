import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import cv2
import numpy as np
from insightface.app import FaceAnalysis

from database import load_all_students, log_attendance
from settings import (
    CAMERA_FPS,
    CAMERA_READ_SLEEP_SECONDS,
    FACE_DETECTION_PROFILES,
    FACE_MODEL_NAME,
    JPEG_QUALITY,
    LIVENESS_MAX_FACE_MOTION,
    LIVENESS_MIN_FACE_MOTION,
    LIVENESS_MIN_FACE_RATIO,
    LIVENESS_MIN_TEXTURE_SCORE,
    LIVENESS_REQUIRED_SAMPLES,
    LIVENESS_WINDOW_SECONDS,
    LOW_LIGHT_GAMMA,
    LOW_LIGHT_MEAN_THRESHOLD,
    RECOGNITION_MARGIN,
    RECOGNITION_THRESHOLD,
    RECOGNITION_INTERVAL_SECONDS,
    RECOGNITION_WIDTH,
    SCREENSHOTS_DIR,
    TEACHER_NOTIFICATION_LIMIT,
    UNKNOWN_NAME,
)

camera_lock = threading.Lock()
face_lock = threading.Lock()
face_inference_lock = threading.Lock()
teacher_notification_lock = threading.Lock()
cameras = {}
face_apps = {}
teacher_notifications = []
recognition_executor = ThreadPoolExecutor(max_workers=2)

KNOWN_FACE_COLOR = (0, 220, 0)  # Жашыл рамка
UNKNOWN_FACE_COLOR = (0, 0, 255)  # Кызыл рамка
LOW_LIGHT_LUT = np.array(
    [((value / 255.0) ** max(LOW_LIGHT_GAMMA, 0.1)) * 255 for value in range(256)],
    dtype=np.uint8,
)

known_cache = {
    "loaded_at": 0.0,
    "names": [],
    "parent_codes": [],
    "embeddings": np.empty((0, 512), dtype=np.float32),
    "classes": [],
}


class LivenessState:
    def __init__(self):
        self.samples = []

    def _face_texture_score(self, frame, box):
        x1, y1, x2, y2 = clamp_box(box, frame.shape)
        if x2 <= x1 or y2 <= y1:
            return 0.0
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return 0.0
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())

    def _signature(self, face, box, frame_shape):
        height, width = frame_shape[:2]
        x1, y1, x2, y2 = [float(value) for value in box]
        values = [
            ((x1 + x2) / 2.0) / max(1.0, width),
            ((y1 + y2) / 2.0) / max(1.0, height),
            (x2 - x1) / max(1.0, width),
            (y2 - y1) / max(1.0, height),
        ]
        return np.asarray(values, dtype=np.float32)

    def is_live(self, frame, face, box):
        height, width = frame.shape[:2]
        x1, y1, x2, y2 = clamp_box(box, frame.shape)
        face_ratio = box_area((x1, y1, x2, y2)) / max(1, width * height)
        texture_score = self._face_texture_score(frame, (x1, y1, x2, y2))
        now = time.time()

        if face_ratio < LIVENESS_MIN_FACE_RATIO or texture_score < LIVENESS_MIN_TEXTURE_SCORE:
            self.samples = []
            return False

        signature = self._signature(face, (x1, y1, x2, y2), frame.shape)
        self.samples.append((now, signature))
        self.samples = [
            sample
            for sample in self.samples[-LIVENESS_REQUIRED_SAMPLES * 2:]
            if now - sample[0] <= LIVENESS_WINDOW_SECONDS
        ]

        if texture_score >= LIVENESS_MIN_TEXTURE_SCORE * 1.5 and face_ratio >= LIVENESS_MIN_FACE_RATIO:
            return True

        if len(self.samples) < LIVENESS_REQUIRED_SAMPLES:
            return False

        newest = self.samples[-1][1]
        motion_scores = [
            float(np.linalg.norm(newest[:4] - sample[1][:4]))
            for sample in self.samples[:-1]
        ]
        if not motion_scores:
            return False

        motion = max(motion_scores)
        stable_live_face = texture_score >= LIVENESS_MIN_TEXTURE_SCORE * 2 and face_ratio >= LIVENESS_MIN_FACE_RATIO * 1.5
        return (LIVENESS_MIN_FACE_MOTION <= motion <= LIVENESS_MAX_FACE_MOTION) or stable_live_face


def add_teacher_notification(name, class_name, status, photo_path):
    notification = {
        "name": name,
        "class_name": class_name,
        "status": status,
        "status_text": "Пришел" if status == "keldi" else "Ушел",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "photo_path": photo_path.replace("\\", "/") if photo_path else "",
    }
    with teacher_notification_lock:
        teacher_notifications.insert(0, notification)
        del teacher_notifications[TEACHER_NOTIFICATION_LIMIT:]


def get_teacher_notifications(limit=30):
    with teacher_notification_lock:
        return list(teacher_notifications[:limit])


class CameraStream:
    def __init__(self, index):
        self.index = index
        self.cap = self._open_camera(index)
        self.lock = threading.Lock()
        self.frame = None
        self.ok = False
        self.running = False
        self.thread = None
        self.failed_reads = 0

    def _open_camera(self, index):
        camera = cv2.VideoCapture(index)
        if not camera.isOpened():
            camera = cv2.VideoCapture(index, cv2.CAP_MSMF)
        camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        camera.set(cv2.CAP_PROP_FPS, CAMERA_FPS)
        camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        print(f"Camera {index}: opened={camera.isOpened()}")
        return camera

    def start(self):
        if not self.cap.isOpened():
            return False
        self.running = True
        self.thread = threading.Thread(target=self._reader, daemon=True)
        self.thread.start()
        return True

    def _reader(self):
        while self.running:
            try:
                ok, frame = self.cap.read()
            except Exception:
                ok, frame = False, None

            with self.lock:
                self.ok = ok
                if ok:
                    self.frame = frame
                    self.failed_reads = 0
                else:
                    self.failed_reads += 1

            if not ok and self.failed_reads >= 10:
                self._reopen()
            time.sleep(CAMERA_READ_SLEEP_SECONDS if ok else 0.1)

    def _reopen(self):
        try:
            self.cap.release()
        except Exception:
            pass
        time.sleep(0.2)
        self.cap = self._open_camera(self.index)
        with self.lock:
            self.failed_reads = 0

    def read(self):
        with self.lock:
            if not self.ok or self.frame is None:
                return False, None
            return True, self.frame.copy()

    def release(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        self.cap.release()


def get_camera_stream(index):
    """Камера агымын глобалдык сөздүктөн алат же жаңыдан түзөт."""
    with camera_lock:
        stream = cameras.get(index)
        if stream is None:
            stream = CameraStream(index)
            if stream.start():
                cameras[index] = stream
            else:
                return stream
        return stream


def get_face_app(profile_name="fast"):
    app = face_apps.get(profile_name)
    if app is not None:
        return app

    with face_lock:
        app = face_apps.get(profile_name)
        if app is None:
            det_size = next(
                (size for name, size in FACE_DETECTION_PROFILES if name == profile_name),
                FACE_DETECTION_PROFILES[0][1],
            )
            app = FaceAnalysis(
                name=FACE_MODEL_NAME,
                allowed_modules=["detection", "recognition"],
                providers=["CPUExecutionProvider"],
            )
            app.prepare(ctx_id=0, det_size=(det_size, det_size))
            face_apps[profile_name] = app
    return app


def get_fast_face_app():
    return get_face_app(FACE_DETECTION_PROFILES[0][0])


def warm_up_face_models():
    def worker():
        try:
            get_face_app(FACE_DETECTION_PROFILES[0][0])
        except Exception as exc:
            print(f"Face model warmup error: {type(exc).__name__}: {exc}")

    threading.Thread(target=worker, daemon=True).start()


def normalize_embedding(embedding):
    embedding = np.asarray(embedding, dtype=np.float32)
    norm = np.linalg.norm(embedding)
    return embedding / max(norm, 1e-6)


def select_largest_face(faces):
    return max(
        faces,
        key=lambda face: max(0, float(face.bbox[2] - face.bbox[0])) * max(0, float(face.bbox[3] - face.bbox[1])),
    )


def rotate_frame_with_matrix(frame, angle):
    height, width = frame.shape[:2]
    center = (width / 2, height / 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(
        frame,
        matrix,
        (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT_101,
    )
    return rotated, matrix


def rotate_frame(frame, angle):
    return rotate_frame_with_matrix(frame, angle)[0]


def transform_box(box, inverse_matrix, frame_shape):
    x1, y1, x2, y2 = [float(value) for value in box]
    points = np.asarray([[x1, y1], [x2, y1], [x2, y2], [x1, y2]], dtype=np.float32)
    transformed = cv2.transform(points.reshape(1, -1, 2), inverse_matrix).reshape(-1, 2)
    min_x, min_y = transformed.min(axis=0)
    max_x, max_y = transformed.max(axis=0)
    return clamp_box((min_x, min_y, max_x, max_y), frame_shape)


def enrollment_variants(frame):
    yield frame
    yield enhance_low_light_frame(frame)
    yield sharpen_frame(frame)
    for angle in (-12, 12, -20, 20):
        yield rotate_frame(frame, angle)
    flipped = cv2.flip(frame, 1)
    yield flipped
    yield sharpen_frame(flipped)


def extract_face_embedding(frame, app=None):
    if frame is None:
        return None
    app = app or get_face_app("accurate")
    embeddings = []
    for variant in enrollment_variants(frame):
        faces = app.get(variant)
        if not faces:
            continue
        embeddings.append(normalize_embedding(select_largest_face(faces).embedding))
    if not embeddings:
        return None
    return normalize_embedding(np.mean(embeddings, axis=0)).astype(np.float32)


def load_known_faces(force=False):
    now = time.time()
    if not force and now - known_cache["loaded_at"] < 5:
        return known_cache

    names, parent_codes, embeddings, classes = load_all_students()
    valid_rows = []
    for name, parent_code, embedding, class_name in zip(names, parent_codes, embeddings, classes):
        embedding = np.asarray(embedding, dtype=np.float32).reshape(-1)
        if embedding.size != 512 or not np.isfinite(embedding).all():
            continue
        valid_rows.append((name, parent_code, embedding, class_name))

    if valid_rows:
        names, parent_codes, embeddings, classes = map(list, zip(*valid_rows))
        matrix = np.asarray(embeddings, dtype=np.float32)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        matrix = matrix / np.maximum(norms, 1e-6)
    else:
        names, parent_codes, classes = [], [], []
        matrix = np.empty((0, 512), dtype=np.float32)

    known_cache.update({
        "loaded_at": now,
        "names": names,
        "parent_codes": parent_codes,
        "embeddings": matrix,
        "classes": classes,
    })
    return known_cache


def recognize_face(embedding, known, threshold=RECOGNITION_THRESHOLD, margin=RECOGNITION_MARGIN):
    if len(known["embeddings"]) == 0:
        return UNKNOWN_NAME, "", ""
    scores = known["embeddings"] @ normalize_embedding(embedding)
    best_idx = int(np.argmax(scores))
    best_score = float(scores[best_idx])
    second_score = float(np.partition(scores, -2)[-2]) if len(scores) > 1 else -1.0
    if best_score >= threshold and (len(scores) == 1 or best_score - second_score >= margin):
        return known["names"][best_idx], known["parent_codes"][best_idx], known["classes"][best_idx]
    return UNKNOWN_NAME, "", ""


def resize_for_recognition(frame):
    height, width = frame.shape[:2]
    if width <= RECOGNITION_WIDTH:
        return frame, 1.0, 1.0
    scale = RECOGNITION_WIDTH / width
    resized = cv2.resize(frame, (RECOGNITION_WIDTH, int(height * scale)))
    return resized, width / resized.shape[1], height / resized.shape[0]


def enhance_low_light_frame(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    if float(np.mean(gray)) >= LOW_LIGHT_MEAN_THRESHOLD:
        return frame
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced_l = clahe.apply(l_channel)
    enhanced = cv2.merge((enhanced_l, a_channel, b_channel))
    enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)
    enhanced = cv2.convertScaleAbs(enhanced, alpha=1.28, beta=24)
    return cv2.LUT(enhanced, LOW_LIGHT_LUT)


def sharpen_frame(frame):
    blurred = cv2.GaussianBlur(frame, (0, 0), 1.0)
    return cv2.addWeighted(frame, 1.45, blurred, -0.45, 0)


def recognition_variants(frame):
    yield frame, None
    enhanced = enhance_low_light_frame(frame)
    if enhanced is not frame:
        yield enhanced, None
        yield sharpen_frame(enhanced), None
    yield sharpen_frame(frame), None
    for angle in (-12, 12):
        rotated, matrix = rotate_frame_with_matrix(frame, angle)
        yield rotated, cv2.invertAffineTransform(matrix)


def clamp_box(box, frame_shape):
    height, width = frame_shape[:2]
    x1, y1, x2, y2 = box
    x1, x2 = sorted((int(x1), int(x2)))
    y1, y2 = sorted((int(y1), int(y2)))
    return (
        max(0, min(width - 1, x1)),
        max(0, min(height - 1, y1)),
        max(0, min(width - 1, x2)),
        max(0, min(height - 1, y2)),
    )


def box_area(box):
    x1, y1, x2, y2 = box
    return max(0, x2 - x1) * max(0, y2 - y1)


def is_reasonable_face_box(box, frame_shape):
    height, width = frame_shape[:2]
    x1, y1, x2, y2 = clamp_box(box, frame_shape)
    box_width = max(0, x2 - x1)
    box_height = max(0, y2 - y1)
    if box_width < 40 or box_height < 40:
        return False
    area_ratio = (box_width * box_height) / max(1, width * height)
    aspect_ratio = box_width / max(1, box_height)
    return 0.005 <= area_ratio <= 0.50 and 0.50 <= aspect_ratio <= 1.70


def face_box_only(box, frame_shape, scale=0.04):
    x1, y1, x2, y2 = box
    width = x2 - x1
    height = y2 - y1
    pad_x = int(width * scale)
    pad_y = int(height * scale)
    return clamp_box((x1 - pad_x, y1 - pad_y, x2 + pad_x, y2 + pad_y), frame_shape)


def draw_face_box(frame, box, color, label=""):
    x1, y1, x2, y2 = clamp_box(box, frame.shape)
    if x2 <= x1 or y2 <= y1 or not is_reasonable_face_box((x1, y1, x2, y2), frame.shape):
        return

    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
    label = (label or "").strip()
    if not label:
        return

    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.6
    thickness = 2
    text_size, baseline = cv2.getTextSize(label, font, font_scale, thickness)
    text_width, text_height = text_size
    label_y1 = max(0, y1 - text_height - baseline - 8)
    label_y2 = max(text_height + baseline + 8, y1)
    label_x2 = min(frame.shape[1] - 1, x1 + text_width + 10)

    cv2.rectangle(frame, (x1, label_y1), (label_x2, label_y2), color, -1)
    cv2.putText(
        frame,
        label,
        (x1 + 5, label_y2 - baseline - 4),
        font,
        font_scale,
        (255, 255, 255),
        thickness,
        cv2.LINE_AA,
    )


def recognize_frame(frame, status, liveness_state, allowed_classes=None):
    allowed_classes = set(allowed_classes or [])
    known = load_known_faces()
    small_frame, scale_x, scale_y = resize_for_recognition(frame)
    faces = []
    with face_inference_lock:
        for profile_name, _ in FACE_DETECTION_PROFILES:
            app = get_face_app(profile_name)
            inverse_matrix = None
            for variant, variant_inverse_matrix in recognition_variants(small_frame):
                faces = app.get(variant)
                if faces:
                    inverse_matrix = variant_inverse_matrix
                    break
            if faces:
                break
    people = []

    for face in faces:
        x1, y1, x2, y2 = face.bbox.astype(int)
        face_box = (x1, y1, x2, y2)
        if inverse_matrix is not None:
            face_box = transform_box(face_box, inverse_matrix, small_frame.shape)

        name, parent_code, class_name = recognize_face(face.embedding, known)
        is_known = (name != UNKNOWN_NAME)
        if is_known and allowed_classes and class_name not in allowed_classes:
            continue
        is_live = liveness_state.is_live(small_frame, face, face_box)

        x1, y1, x2, y2 = face_box
        box = face_box_only(
            (int(x1 * scale_x), int(y1 * scale_y), int(x2 * scale_x), int(y2 * scale_y)),
            frame.shape,
        )
        if not is_reasonable_face_box(box, frame.shape):
            continue

        # Эгер белгилүү окуучу болсо, рамка дайыма туруктуу чыгып турсун (liveness жумшартылды)
        if is_known:
            people.append((name, box, False))
            if is_live and log_attendance(name, class_name, status):
                photo_path = os.path.join(SCREENSHOTS_DIR,
                                          f"{name}_{status}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
                cv2.imwrite(photo_path, frame)
                add_teacher_notification(name, class_name, status, photo_path)
        else:
            if not is_live:
                people.append((UNKNOWN_NAME, box, True))
            else:
                people.append((UNKNOWN_NAME, box, False))

    return people


def camera_frames(status, camera_index, allowed_classes=None):
    last_recognition = 0.0
    liveness_state = LivenessState()
    recognition_task = None
    current_people = []

    while True:
        stream = get_camera_stream(camera_index)
        ok, frame = stream.read()
        if not ok:
            error_frame = np.zeros((360, 640, 3), dtype=np.uint8)
            cv2.putText(error_frame, f"Camera {camera_index} unavailable", (34, 165), cv2.FONT_HERSHEY_SIMPLEX, 0.9,
                        (255, 255, 255), 2, cv2.LINE_AA)
            ok, buffer = cv2.imencode(".jpg", error_frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
            if ok:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
            time.sleep(0.5)
            continue

        now = time.time()
        if recognition_task is not None and recognition_task.done():
            try:
                current_people = recognition_task.result()
            except Exception as exc:
                print(f"Recognition error: {exc}")
            recognition_task = None

        if recognition_task is None and now - last_recognition >= RECOGNITION_INTERVAL_SECONDS:
            last_recognition = now
            recognition_task = recognition_executor.submit(recognize_frame, frame.copy(), status, liveness_state, allowed_classes)

        # Кадрдагы ар бир адамды айланып чыгып, өз-өзүнчө рамка тартат
        for name, box, is_fake in current_people:
            if is_fake:
                draw_face_box(frame, box, UNKNOWN_FACE_COLOR, "Fake Face")
            else:
                is_known = name != UNKNOWN_NAME
                # OpenCV's built-in font cannot render Cyrillic names and shows question marks.
                draw_face_box(frame, box, KNOWN_FACE_COLOR if is_known else UNKNOWN_FACE_COLOR)

        ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
        if ok:
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
        time.sleep(max(0.001, 1 / max(1, CAMERA_FPS)))
