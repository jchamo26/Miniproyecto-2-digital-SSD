"""DL Service - ECG image ONNX INT8 inference with Grad-CAM-like artifact in MinIO."""
import base64
import io
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import List
from uuid import uuid4

import numpy as np
import onnxruntime as ort
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from minio import Minio
from onnxruntime.quantization import QuantType, quantize_dynamic
from PIL import Image
from pydantic import BaseModel
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split
from skl2onnx import to_onnx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="DL Service", version="5.0.0")

# ── ECG image preprocessing constants ────────────────────────────────────────
IMG_H = 32   # height pixels used for the feature vector
IMG_W = 64   # width  pixels used for the feature vector
N_FEATURES = IMG_H * IMG_W  # 2048 input features

# ── ECG class definitions ─────────────────────────────────────────────────────
ECG_CLASSES = ["Normal", "Atrial Fibrillation", "ST-Elevation MI", "Other Arrhythmia"]

# Clinical risk weight per class (0 = lowest, 1 = highest)
ECG_CLASS_RISK_WEIGHTS = [0.10, 0.65, 0.95, 0.45]

# Map ECG class → four-level risk category
ECG_CLASS_TO_RISK: dict = {
    "Normal": "LOW",
    "Other Arrhythmia": "MEDIUM",
    "Atrial Fibrillation": "HIGH",
    "ST-Elevation MI": "CRITICAL",
}


class PredictionRequest(BaseModel):
    patient_id: str
    image_base64: str | None = None


class PredictionResponse(BaseModel):
    task_id: str
    patient_id: str
    predicted_class: str
    probabilities: dict
    is_critical: bool
    risk_score: float
    risk_category: str
    gradcam_url: str | None = None
    image_url: str | None = None
    fhir_diagnostic_report: dict | None = None
    timestamp: str


class ImageONNXService:
    def __init__(self):
        self.dataset_name = "ECG-Images-Dataset"
        self.model_dir = Path("/app/models")
        self.model_dir.mkdir(parents=True, exist_ok=True)

        self.onnx_fp32 = self.model_dir / "ecg_fp32.onnx"
        self.onnx_int8 = self.model_dir / "ecg_int8.onnx"

        self.model = None
        self.session = None
        self.x_test = None
        self.y_test = None
        self.mean_image = None
        self.metrics = {}

        self.minio_endpoint = os.getenv("MINIO_ENDPOINT", "minio:9000")
        self.minio_access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
        self.minio_secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin")
        self.minio_bucket = os.getenv("MINIO_BUCKET", "clinical-images")
        self.minio_client = Minio(
            self.minio_endpoint,
            access_key=self.minio_access_key,
            secret_key=self.minio_secret_key,
            secure=False,
        )
        self.seed_prefix = os.getenv("DL_MINIO_SEED_PREFIX", "seed/ecg-images")
        self.local_seed_dir = Path(os.getenv("DL_LOCAL_IMAGE_DIR", "/datasets/ecg-images/images"))
        self.seed_max_upload = int(os.getenv("DL_SEED_MAX_UPLOAD", "200"))
        self.seed_image_keys: List[str] = []

    # ── synthetic ECG waveform generation ────────────────────────────────────

    @staticmethod
    def _draw_ecg_wave(wave: np.ndarray, img: np.ndarray) -> np.ndarray:
        """Draw a 1-D ECG waveform into a 2-D grayscale image array."""
        h, w = img.shape
        baseline = h // 2
        wave_norm = wave / (np.max(np.abs(wave)) + 1e-8) * (h // 3)
        for x, y_off in enumerate(wave_norm[:w]):
            y = int(baseline - y_off)
            y = max(0, min(h - 1, y))
            img[y, x] = 1.0
            if y > 0:
                img[y - 1, x] = 0.6
            if y < h - 1:
                img[y + 1, x] = 0.6
        return img

    def _generate_synthetic_ecg(self, class_idx: int, seed: int) -> np.ndarray:
        """Return a (IMG_H × IMG_W) float32 array representing a synthetic ECG trace."""
        rng = np.random.default_rng(seed)
        img = np.zeros((IMG_H, IMG_W), dtype=np.float32)
        t = np.linspace(0, 2 * np.pi, IMG_W)

        if class_idx == 0:  # Normal sinus rhythm
            wave = 0.4 * np.sin(t) + 0.08 * np.sin(3 * t)
            for qrs_x in (IMG_W // 4, 3 * IMG_W // 4):
                xs = slice(max(0, qrs_x - 2), min(IMG_W, qrs_x + 3))
                template = np.array([0.0, 0.6, -0.35, 0.9, 0.0])
                wave[xs] += template[: xs.stop - xs.start]

        elif class_idx == 1:  # Atrial fibrillation – irregular baseline, no clear P waves
            freqs = rng.integers(8, 18, 6)
            wave = sum(
                rng.uniform(0.04, 0.1) * np.sin(f * t + rng.uniform(0, 2 * np.pi))
                for f in freqs
            )
            positions = sorted(rng.integers(5, IMG_W - 5, 4).tolist())
            for p in positions:
                amp = rng.uniform(0.5, 0.85)
                xs = slice(max(0, p - 1), min(IMG_W, p + 3))
                wave[xs] += amp

        elif class_idx == 2:  # ST-Elevation MI – elevated ST segment after QRS
            wave = 0.25 * np.sin(t)
            qrs_x = IMG_W // 3
            xs = slice(max(0, qrs_x - 2), min(IMG_W, qrs_x + 3))
            template = np.array([0.0, 0.7, -0.4, 1.0, 0.0])
            wave[xs] += template[: xs.stop - xs.start]
            st_start = qrs_x + 3
            st_end = min(IMG_W, st_start + IMG_W // 3)
            wave[st_start:st_end] += 0.45 - np.linspace(0, 0.2, st_end - st_start)

        else:  # Other arrhythmia – wide / aberrant QRS
            wave = 0.3 * np.sin(t)
            for qrs_x in (IMG_W // 5, 3 * IMG_W // 5):
                width = 8
                xs = slice(max(0, qrs_x - 1), min(IMG_W, qrs_x + width))
                span = xs.stop - xs.start
                wave[xs] += np.linspace(0, 1, span) * 0.8 - 0.2

        noise = rng.normal(0, 0.04, IMG_W).astype(np.float32)
        wave = (wave + noise).astype(np.float32)
        return self._draw_ecg_wave(wave, img)

    def _generate_synthetic_dataset(self, n_per_class: int = 250, seed: int = 42):
        """Generate a balanced synthetic ECG dataset for training."""
        rng = np.random.default_rng(seed)
        X, y = [], []
        for class_idx in range(len(ECG_CLASSES)):
            seeds = rng.integers(0, 100_000, n_per_class)
            for s in seeds:
                img = self._generate_synthetic_ecg(class_idx, int(s))
                noise = rng.normal(0, 0.03, img.shape).astype(np.float32)
                X.append(np.clip(img + noise, 0, 1).flatten())
                y.append(class_idx)
        return np.array(X, dtype=np.float32), np.array(y, dtype=np.int64)

    # ── dataset loading ───────────────────────────────────────────────────────

    def _load_dataset_from_dir(self):
        """
        Load ECG images from self.local_seed_dir.

        Expected layout::

            <local_seed_dir>/
                Normal/               *.png | *.jpg | *.jpeg
                Atrial Fibrillation/
                ST-Elevation MI/
                Other Arrhythmia/

        Returns (X, y) arrays ready for train_test_split.
        """
        X, y = [], []
        for class_idx, class_name in enumerate(ECG_CLASSES):
            class_dir = self.local_seed_dir / class_name
            if not class_dir.exists():
                logger.warning("ECG class dir not found: %s", class_dir)
                continue
            count = 0
            for img_path in sorted(class_dir.rglob("*")):
                if img_path.suffix.lower() not in (".png", ".jpg", ".jpeg"):
                    continue
                if count >= self.seed_max_upload:
                    break
                try:
                    pil = Image.open(img_path).convert("L")
                    X.append(self._to_vector(pil))
                    y.append(class_idx)
                    count += 1
                except Exception as exc:
                    logger.warning("Skipping %s: %s", img_path, exc)
        if not X:
            raise ValueError("No ECG images found in %s" % self.local_seed_dir)
        return np.array(X, dtype=np.float32), np.array(y, dtype=np.int64)

    def _load_dataset(self):
        if self.local_seed_dir.exists():
            try:
                logger.info("Loading ECG images from %s", self.local_seed_dir)
                X, y = self._load_dataset_from_dir()
                logger.info("Loaded %d real ECG images from disk", len(y))
            except Exception as exc:
                logger.warning(
                    "Failed to load ECG dataset (%s); falling back to synthetic data", exc
                )
                X, y = self._generate_synthetic_dataset()
        else:
            logger.info(
                "ECG dataset not found at %s; using synthetic data for demo",
                self.local_seed_dir,
            )
            X, y = self._generate_synthetic_dataset()

        self.mean_image = X.mean(axis=0).reshape(IMG_H, IMG_W)
        x_train, x_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )
        self.x_test = x_test
        self.y_test = y_test
        return x_train, x_test, y_train, y_test

    def _train_export_quantize(self):
        x_train, x_test, y_train, y_test = self._load_dataset()

        self.model = LogisticRegression(max_iter=600, solver="lbfgs", C=1.0)
        self.model.fit(x_train, y_train)

        y_pred = self.model.predict(x_test)
        self.metrics = {
            "accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
            "num_classes": len(ECG_CLASSES),
            "classes": ECG_CLASSES,
        }

        onx = to_onnx(
            self.model,
            x_train[:1],
            options={id(self.model): {"zipmap": False}},
            target_opset=13,
        )
        with open(self.onnx_fp32, "wb") as f:
            f.write(onx.SerializeToString())

        quantize_dynamic(
            model_input=str(self.onnx_fp32),
            model_output=str(self.onnx_int8),
            weight_type=QuantType.QInt8,
        )

        self.session = ort.InferenceSession(str(self.onnx_int8), providers=["CPUExecutionProvider"])

    def _ensure_bucket(self):
        if not self.minio_client.bucket_exists(self.minio_bucket):
            self.minio_client.make_bucket(self.minio_bucket)

    def _list_seed_keys(self) -> List[str]:
        keys = []
        for obj in self.minio_client.list_objects(self.minio_bucket, prefix=self.seed_prefix, recursive=True):
            name = str(obj.object_name or "")
            lower = name.lower()
            if lower.endswith(".png") or lower.endswith(".jpg") or lower.endswith(".jpeg"):
                keys.append(name)
        keys.sort()
        return keys

    @staticmethod
    def _detect_content_type(path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix == ".png":
            return "image/png"
        if suffix == ".jpg" or suffix == ".jpeg":
            return "image/jpeg"
        return "application/octet-stream"

    def _seed_minio_from_local(self):
        existing = self._list_seed_keys()
        if existing:
            self.seed_image_keys = existing
            logger.info("DL seed ECG images already present in MinIO: %s", len(existing))
            return

        if not self.local_seed_dir.exists():
            logger.info(
                "DL local seed folder not found at %s; using synthetic fallback",
                self.local_seed_dir,
            )
            self.seed_image_keys = []
            return

        candidates = []
        for pattern in ("*.png", "*.jpg", "*.jpeg"):
            candidates.extend(self.local_seed_dir.rglob(pattern))
        candidates = sorted(candidates)[: self.seed_max_upload]

        uploaded = 0
        for img_path in candidates:
            # Preserve class sub-folder in the MinIO key so seed images stay organised
            object_name = f"{self.seed_prefix}/{img_path.parent.name}/{img_path.name}"
            try:
                payload = img_path.read_bytes()
                self.minio_client.put_object(
                    self.minio_bucket,
                    object_name,
                    io.BytesIO(payload),
                    length=len(payload),
                    content_type=self._detect_content_type(img_path),
                )
                uploaded += 1
            except Exception as exc:
                logger.warning("Skipping seed image %s due to upload error: %s", img_path, exc)

        self.seed_image_keys = self._list_seed_keys()
        logger.info(
            "DL seeded ECG images from %s: uploaded=%s available=%s",
            self.local_seed_dir,
            uploaded,
            len(self.seed_image_keys),
        )

    def _load_seed_image(self, patient_id: str) -> Image.Image | None:
        if not self.seed_image_keys:
            return None
        idx = abs(hash(patient_id)) % len(self.seed_image_keys)
        key = self.seed_image_keys[idx]
        try:
            obj = self.minio_client.get_object(self.minio_bucket, key)
            payload = obj.read()
            obj.close()
            obj.release_conn()
            return Image.open(io.BytesIO(payload)).convert("L")
        except Exception as exc:
            logger.warning("Failed to load seed image %s from MinIO: %s", key, exc)
            return None

    def initialize(self):
        self._train_export_quantize()
        self._ensure_bucket()
        self._seed_minio_from_local()
        logger.info("DL ECG model initialized with metrics=%s", self.metrics)

    # ── image helpers ─────────────────────────────────────────────────────────

    def _decode_image_b64(self, image_base64: str) -> Image.Image:
        payload = image_base64.split(",", 1)[-1]
        raw = base64.b64decode(payload)
        return Image.open(io.BytesIO(raw)).convert("L")

    def _synthetic_image(self, patient_id: str) -> Image.Image:
        """Generate a deterministic synthetic ECG image from the patient ID."""
        seed = abs(hash(patient_id)) % (2**32)
        class_idx = seed % len(ECG_CLASSES)
        arr = self._generate_synthetic_ecg(class_idx, seed)
        return Image.fromarray(np.uint8(arr * 255), mode="L")

    def _to_vector(self, img: Image.Image) -> np.ndarray:
        """Resize an ECG image to (IMG_H × IMG_W) and return a flat float32 vector."""
        resized = img.resize((IMG_W, IMG_H), Image.Resampling.BILINEAR)
        arr = np.asarray(resized, dtype=np.float32) / 255.0
        return arr.flatten()

    # ── inference helpers ──────────────────────────────────────────────────────

    def _onnx_probs(self, x_vec: np.ndarray) -> np.ndarray:
        """Run ONNX inference and return class probability array (shape: [num_classes])."""
        input_name = self.session.get_inputs()[0].name
        outputs = self.session.run(None, {input_name: x_vec.reshape(1, -1).astype(np.float32)})
        for out in outputs:
            arr = np.asarray(out)
            if arr.ndim == 2 and arr.shape[1] == len(ECG_CLASSES):
                return arr[0]
        # Fallback: sklearn predict_proba
        return self.model.predict_proba(x_vec.reshape(1, -1))[0]

    def _build_gradcam(self, x_vec: np.ndarray) -> Image.Image:
        """Produce a Grad-CAM-like saliency heatmap from deviation vs mean ECG."""
        heat = np.abs(x_vec.reshape(IMG_H, IMG_W) - self.mean_image)
        heat = heat / (heat.max() + 1e-8)
        heat_u8 = np.uint8(heat * 255)
        base = Image.fromarray(heat_u8, mode="L").resize((256, 256), Image.Resampling.NEAREST)
        return base.convert("RGB")

    def _upload_to_minio(self, patient_id: str, task_id: str, image: Image.Image, gradcam: Image.Image):
        image_bytes = io.BytesIO()
        gradcam_bytes = io.BytesIO()
        image.save(image_bytes, format="PNG")
        gradcam.save(gradcam_bytes, format="PNG")
        image_payload = image_bytes.getvalue()
        gradcam_payload = gradcam_bytes.getvalue()

        image_key = f"patients/{patient_id}/images/{task_id}.png"
        gradcam_key = f"patients/{patient_id}/gradcam/{task_id}.png"
        compat_image_key = f"images/{task_id}.png"
        compat_gradcam_key = f"gradcam/{task_id}.png"

        for key, payload in [
            (image_key, image_payload),
            (compat_image_key, image_payload),
        ]:
            self.minio_client.put_object(
                self.minio_bucket, key, io.BytesIO(payload), length=len(payload), content_type="image/png"
            )
        for key, payload in [
            (gradcam_key, gradcam_payload),
            (compat_gradcam_key, gradcam_payload),
        ]:
            self.minio_client.put_object(
                self.minio_bucket, key, io.BytesIO(payload), length=len(payload), content_type="image/png"
            )
        return image_key, gradcam_key

    def predict(self, patient_id: str, task_id: str, image: Image.Image) -> dict:
        x_vec = self._to_vector(image)
        probs = self._onnx_probs(x_vec)

        # Scalar risk score = weighted sum of class probabilities
        risk_score = float(np.clip(np.dot(probs, ECG_CLASS_RISK_WEIGHTS), 0.0, 1.0))
        predicted_class_idx = int(np.argmax(probs))
        predicted_class = ECG_CLASSES[predicted_class_idx]
        risk_category = ECG_CLASS_TO_RISK[predicted_class]
        probabilities = {ECG_CLASSES[i]: float(probs[i]) for i in range(len(ECG_CLASSES))}

        gradcam = self._build_gradcam(x_vec)
        image_url = None
        gradcam_url = None
        try:
            image_key, gradcam_key = self._upload_to_minio(patient_id, task_id, image, gradcam)
            image_url = f"minio://{self.minio_bucket}/{image_key}"
            gradcam_url = f"minio://{self.minio_bucket}/{gradcam_key}"
        except Exception as exc:
            logger.warning("MinIO upload failed: %s", exc)

        return {
            "risk_score": risk_score,
            "risk_category": risk_category,
            "predicted_class": predicted_class,
            "probabilities": probabilities,
            "is_critical": risk_category == "CRITICAL",
            "image_url": image_url,
            "gradcam_url": gradcam_url,
            "fhir_diagnostic_report": {
                "resourceType": "DiagnosticReport",
                "status": "final",
                "code": {
                    "coding": [
                        {
                            "system": "http://loinc.org",
                            "code": "11524-6",
                            "display": "EKG study",
                        }
                    ],
                    "text": "DL ECG image classification report",
                },
                "subject": {"reference": f"Patient/{patient_id}"},
                "conclusion": (
                    f"ECG classification: {predicted_class}. "
                    f"Clinical risk: {risk_category} (score {risk_score:.3f})."
                ),
                "presentedForm": [
                    {"contentType": "image/png", "url": image_url, "title": "ECG input image"},
                    {"contentType": "image/png", "url": gradcam_url, "title": "Saliency map (Grad-CAM-like)"},
                ],
            },
        }


service = ImageONNXService()


@app.on_event("startup")
async def startup_event():
    service.initialize()


@app.post("/predict", response_model=PredictionResponse)
async def predict(req: PredictionRequest):
    try:
        task_id = str(uuid4())
        if req.image_base64:
            image = service._decode_image_b64(req.image_base64)
        else:
            image = service._load_seed_image(req.patient_id)
            if image is None:
                image = service._synthetic_image(req.patient_id)
        out = service.predict(req.patient_id, task_id, image)

        logger.info(
            "DL prediction task=%s patient=%s risk=%.3f category=%s",
            task_id,
            req.patient_id,
            out["risk_score"],
            out["risk_category"],
        )

        return PredictionResponse(
            task_id=task_id,
            patient_id=req.patient_id,
            predicted_class=out["predicted_class"],
            probabilities=out["probabilities"],
            is_critical=out["is_critical"],
            risk_score=out["risk_score"],
            risk_category=out["risk_category"],
            gradcam_url=out["gradcam_url"],
            image_url=out["image_url"],
            fhir_diagnostic_report=out["fhir_diagnostic_report"],
            timestamp=datetime.utcnow().isoformat(),
        )
    except Exception as e:
        logger.exception("DL prediction error")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/predict-image", response_model=PredictionResponse)
async def predict_image(patient_id: str = Form(...), image: UploadFile = File(...)):
    try:
        task_id = str(uuid4())
        payload = await image.read()
        pil = Image.open(io.BytesIO(payload)).convert("L")
        out = service.predict(patient_id, task_id, pil)

        return PredictionResponse(
            task_id=task_id,
            patient_id=patient_id,
            predicted_class=out["predicted_class"],
            probabilities=out["probabilities"],
            is_critical=out["is_critical"],
            risk_score=out["risk_score"],
            risk_category=out["risk_category"],
            gradcam_url=out["gradcam_url"],
            image_url=out["image_url"],
            fhir_diagnostic_report=out["fhir_diagnostic_report"],
            timestamp=datetime.utcnow().isoformat(),
        )
    except Exception as e:
        logger.exception("DL image prediction error")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/version")
async def get_version():
    fp32_size = round(service.onnx_fp32.stat().st_size / (1024 * 1024), 3) if service.onnx_fp32.exists() else None
    int8_size = round(service.onnx_int8.stat().st_size / (1024 * 1024), 3) if service.onnx_int8.exists() else None

    return {
        "model": "ECG-Image-LogReg",
        "framework": "ONNX Runtime",
        "quantization": "INT8",
        "metrics": service.metrics,
        "input_shape": [1, N_FEATURES],
        "ecg_classes": ECG_CLASSES,
        "artifacts": {
            "onnx_fp32_mb": fp32_size,
            "onnx_int8_mb": int8_size,
            "dataset": service.dataset_name,
        },
        "hardware": "CPU-only",
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "dl-service",
        "dataset_loaded": service.x_test is not None,
        "onnx_session_ready": service.session is not None,
        "minio_bucket": service.minio_bucket,
        "seed_images_count": len(service.seed_image_keys),
        "seed_local_dir": str(service.local_seed_dir),
        "ecg_classes": ECG_CLASSES,
    }