"""DL Service - image ONNX INT8 inference with Grad-CAM-like artifact in MinIO."""
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
from sklearn.datasets import load_digits
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import train_test_split
from skl2onnx import to_onnx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="DL Service", version="4.0.0")


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
        self.dataset_name = "sklearn-digits"
        self.model_dir = Path("/app/models")
        self.model_dir.mkdir(parents=True, exist_ok=True)

        self.onnx_fp32 = self.model_dir / "digits_fp32.onnx"
        self.onnx_int8 = self.model_dir / "digits_int8.onnx"

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
        self.seed_prefix = os.getenv("DL_MINIO_SEED_PREFIX", "seed/chestxray")
        self.local_seed_dir = Path(os.getenv("DL_LOCAL_IMAGE_DIR", "/datasets/nih-chestxray/images"))
        self.seed_max_upload = int(os.getenv("DL_SEED_MAX_UPLOAD", "200"))
        self.seed_image_keys: List[str] = []

    def _load_dataset(self):
        digits = load_digits()
        x = digits.data.astype(np.float32)
        y = (digits.target >= 5).astype(np.int64)
        self.mean_image = x.mean(axis=0).reshape(8, 8)

        x_train, x_test, y_train, y_test = train_test_split(
            x, y, test_size=0.2, random_state=42, stratify=y
        )
        self.x_test = x_test
        self.y_test = y_test
        return x_train, x_test, y_train, y_test

    def _train_export_quantize(self):
        x_train, x_test, y_train, y_test = self._load_dataset()

        self.model = LogisticRegression(max_iter=400, solver="lbfgs")
        self.model.fit(x_train, y_train)

        probs_test = self.model.predict_proba(x_test)[:, 1]
        y_pred = (probs_test >= 0.5).astype(np.int64)

        self.metrics = {
            "accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
            "auc_roc": round(float(roc_auc_score(y_test, probs_test)), 4),
        }

        onx = to_onnx(self.model, x_train[:1], options={id(self.model): {"zipmap": False}}, target_opset=13)
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
            logger.info("DL seed images already present in MinIO: %s", len(existing))
            return

        if not self.local_seed_dir.exists():
            logger.info("DL local seed folder not found at %s; using synthetic fallback", self.local_seed_dir)
            self.seed_image_keys = []
            return

        candidates = []
        for pattern in ("*.png", "*.jpg", "*.jpeg"):
            candidates.extend(self.local_seed_dir.rglob(pattern))
        candidates = sorted(candidates)[: self.seed_max_upload]

        uploaded = 0
        for img_path in candidates:
            object_name = f"{self.seed_prefix}/{img_path.name}"
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
            "DL seeded images from %s: uploaded=%s available=%s",
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
        logger.info("DL image model initialized with metrics=%s", self.metrics)

    def _decode_image_b64(self, image_base64: str) -> Image.Image:
        payload = image_base64.split(",", 1)[-1]
        raw = base64.b64decode(payload)
        return Image.open(io.BytesIO(raw)).convert("L")

    def _synthetic_image(self, patient_id: str) -> Image.Image:
        seed = abs(hash(patient_id)) % (2**32)
        rng = np.random.default_rng(seed)
        arr = rng.integers(0, 255, size=(256, 256), dtype=np.uint8)
        return Image.fromarray(arr, mode="L")

    def _to_vector(self, img: Image.Image) -> np.ndarray:
        resized = img.resize((8, 8), Image.Resampling.BILINEAR)
        arr = np.asarray(resized, dtype=np.float32)
        arr = np.clip(arr / 255.0 * 16.0, 0.0, 16.0)
        return arr.reshape(-1)

    def _onnx_prob(self, x_vec: np.ndarray) -> float:
        input_name = self.session.get_inputs()[0].name
        outputs = self.session.run(None, {input_name: x_vec.reshape(1, -1).astype(np.float32)})

        probs = None
        for out in outputs:
            arr = np.asarray(out)
            if arr.ndim == 2 and arr.shape[1] >= 2:
                probs = arr[0]
                break

        if probs is None:
            probs = self.model.predict_proba(x_vec.reshape(1, -1))[0]

        return float(probs[1] if probs.shape[0] == 2 else np.max(probs))

    def _risk_category(self, score: float) -> str:
        if score > 0.8:
            return "CRITICAL"
        if score > 0.6:
            return "HIGH"
        if score > 0.4:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _normalize_probs(raw: dict) -> dict:
        total = sum(raw.values())
        if total <= 0:
            return {k: 0.0 for k in raw.keys()}
        return {k: float(v / total) for k, v in raw.items()}

    def _risk_distribution(self, score: float) -> dict:
        low = max(0.0, 1.0 - (score * 2.0))
        medium = max(0.0, 1.0 - abs(score - 0.5) * 2.2)
        high = max(0.0, 1.0 - abs(score - 0.72) * 3.0)
        critical = max(0.0, (score - 0.68) / 0.32)
        return self._normalize_probs({
            "LOW": low,
            "MEDIUM": medium,
            "HIGH": high,
            "CRITICAL": critical,
        })

    def _build_gradcam(self, x_vec: np.ndarray) -> Image.Image:
        heat = np.abs(x_vec.reshape(8, 8) - self.mean_image)
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

        self.minio_client.put_object(
            self.minio_bucket,
            image_key,
            io.BytesIO(image_payload),
            length=len(image_payload),
            content_type="image/png",
        )
        self.minio_client.put_object(
            self.minio_bucket,
            gradcam_key,
            io.BytesIO(gradcam_payload),
            length=len(gradcam_payload),
            content_type="image/png",
        )
        self.minio_client.put_object(
            self.minio_bucket,
            compat_image_key,
            io.BytesIO(image_payload),
            length=len(image_payload),
            content_type="image/png",
        )
        self.minio_client.put_object(
            self.minio_bucket,
            compat_gradcam_key,
            io.BytesIO(gradcam_payload),
            length=len(gradcam_payload),
            content_type="image/png",
        )
        return image_key, gradcam_key

    def predict(self, patient_id: str, task_id: str, image: Image.Image) -> dict:
        x_vec = self._to_vector(image)
        risk_score = max(0.0, min(1.0, self._onnx_prob(x_vec)))
        risk_category = self._risk_category(risk_score)
        probs = self._risk_distribution(risk_score)
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
            "predicted_class": risk_category,
            "probabilities": probs,
            "is_critical": risk_category == "CRITICAL",
            "image_url": image_url,
            "gradcam_url": gradcam_url,
            "fhir_diagnostic_report": {
                "resourceType": "DiagnosticReport",
                "status": "final",
                "code": {
                    "coding": [{"system": "http://loinc.org", "code": "24627-2", "display": "Imaging study report"}],
                    "text": "DL image risk report",
                },
                "subject": {"reference": f"Patient/{patient_id}"},
                "conclusion": f"Predicted risk category: {risk_category}",
                "presentedForm": [
                    {"contentType": "image/png", "url": image_url, "title": "Input image"},
                    {"contentType": "image/png", "url": gradcam_url, "title": "Grad-CAM"},
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
        "model": "Digits-LogReg-Image",
        "framework": "ONNX Runtime",
        "quantization": "INT8",
        "metrics": service.metrics,
        "input_shape": [1, 64],
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
    }