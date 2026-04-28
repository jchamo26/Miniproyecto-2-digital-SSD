"""DL Service - ECG image ONNX inference with MinIO-backed explanations."""
import base64
import io
import logging
import os
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import List
from uuid import uuid4

import numpy as np
import onnxruntime as ort
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from minio import Minio
from onnxruntime.quantization import QuantType, quantize_dynamic
from PIL import Image, ImageDraw, ImageOps
from pydantic import BaseModel
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from skl2onnx import to_onnx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="DL Service", version="5.0.0")

SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}
DEFAULT_SYNTHETIC_CLASSES = ("normal", "abnormal", "afib")


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


class ECGImageONNXService:
    def __init__(self):
        self.dataset_path = Path(os.getenv("ECG_DATASET_PATH", "/datasets/ecg-images"))
        self.dataset_mode = "uninitialized"
        self.dataset_loaded = False
        self.image_size = int(os.getenv("ECG_IMAGE_SIZE", "96"))
        self.display_size = int(os.getenv("DL_DISPLAY_IMAGE_SIZE", "256"))

        self.model_dir = Path("/app/models")
        self.model_dir.mkdir(parents=True, exist_ok=True)

        self.onnx_fp32 = self.model_dir / "ecg_image_classifier_fp32.onnx"
        self.onnx_int8 = self.model_dir / "ecg_image_classifier_int8.onnx"
        self.active_onnx_path: Path | None = None

        self.scaler: StandardScaler | None = None
        self.pca: PCA | None = None
        self.model: LogisticRegression | None = None
        self.session: ort.InferenceSession | None = None
        self.metrics: dict = {}

        self.class_names: list[str] = []
        self.class_counts: dict[str, int] = {}
        self.class_severity: dict[str, float] = {}
        self.training_samples = 0
        self.validation_samples = 0
        self.onnx_feature_size = 0
        self.feature_size = self.image_size * self.image_size

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

        self.seed_prefix = os.getenv("DL_MINIO_SEED_PREFIX", "seed/ecg")
        self.local_seed_dir = Path(os.getenv("DL_LOCAL_IMAGE_DIR", str(self.dataset_path)))
        self.seed_max_upload = int(os.getenv("DL_SEED_MAX_UPLOAD", "300"))
        self.seed_image_keys: List[str] = []

    @staticmethod
    def _normalize_label(raw: str) -> str:
        normalized = raw.strip().lower().replace("_", " ").replace("-", " ")
        return " ".join(normalized.split())

    @staticmethod
    def _image_content_type(path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix in {".jpg", ".jpeg"}:
            return "image/jpeg"
        if suffix == ".png":
            return "image/png"
        if suffix == ".webp":
            return "image/webp"
        if suffix in {".tif", ".tiff"}:
            return "image/tiff"
        return "application/octet-stream"

    def _collect_image_files(self, root: Path) -> list[Path]:
        if not root.exists() or not root.is_dir():
            return []
        files: list[Path] = []
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES:
                files.append(path)
        return sorted(files)

    def _load_image(self, source: Path | bytes | Image.Image) -> Image.Image:
        if isinstance(source, Image.Image):
            return source.copy()
        if isinstance(source, Path):
            with Image.open(source) as img:
                return img.copy()
        with Image.open(io.BytesIO(source)) as img:
            return img.copy()

    def _preprocess_image(self, image: Image.Image) -> Image.Image:
        grayscale = image.convert("L")
        grayscale = ImageOps.autocontrast(grayscale)
        return ImageOps.pad(
            grayscale,
            (self.image_size, self.image_size),
            method=Image.Resampling.BILINEAR,
            color=255,
        )

    def _vectorize_image(self, image: Image.Image) -> np.ndarray:
        prepared = self._preprocess_image(image)
        array = np.asarray(prepared, dtype=np.float32) / 255.0
        return array.reshape(-1)

    def _load_seed_image(self, patient_id: str) -> Image.Image | None:
        if not self.seed_image_keys:
            return None
        index = abs(hash(patient_id)) % len(self.seed_image_keys)
        key = self.seed_image_keys[index]
        try:
            obj = self.minio_client.get_object(self.minio_bucket, key)
            payload = obj.read()
            obj.close()
            obj.release_conn()
            return self._load_image(payload).convert("L")
        except Exception as exc:
            logger.warning("Failed to load ECG seed image %s from MinIO: %s", key, exc)
            return None

    def _build_synthetic_ecg_signal(self, class_name: str, rng: np.random.Generator, width: int, height: int) -> np.ndarray:
        x = np.linspace(0.0, 1.0, width, dtype=np.float32)
        baseline = height * 0.52
        signal = np.full(width, baseline, dtype=np.float32)
        phase = float(rng.uniform(0.0, 2.0 * np.pi))
        cls = class_name.lower()

        if "normal" in cls:
            centers = np.linspace(0.08, 0.92, 7)
            for center in centers:
                signal += 74.0 * np.exp(-((x - center) / 0.0065) ** 2)
                signal -= 22.0 * np.exp(-((x - (center - 0.018)) / 0.013) ** 2)
            signal += 14.0 * np.sin(2.0 * np.pi * 3.0 * x + phase)
        elif "afib" in cls or "fibrill" in cls:
            centers = np.sort(rng.uniform(0.05, 0.95, size=10))
            for center in centers:
                amplitude = float(rng.uniform(34.0, 96.0))
                width_scale = float(rng.uniform(0.004, 0.012))
                signal += amplitude * np.exp(-((x - center) / width_scale) ** 2)
            signal += 18.0 * np.sin(2.0 * np.pi * (10.0 + rng.uniform(0.0, 3.5)) * x + phase)
            signal += 30.0 * np.cumsum(rng.normal(0.0, 0.15, size=width))
        else:
            centers = np.linspace(0.1, 0.9, 6)
            centers = np.clip(centers + rng.normal(0.0, 0.03, size=centers.shape[0]), 0.05, 0.95)
            centers = np.sort(centers)
            for center in centers:
                signal += 62.0 * np.exp(-((x - center) / 0.008) ** 2)
                signal -= 20.0 * np.exp(-((x - (center - 0.02)) / 0.014) ** 2)
            signal += 26.0 * np.sin(2.0 * np.pi * 5.0 * x + phase)
            signal += 16.0 * np.sin(2.0 * np.pi * 13.0 * x + phase * 1.4)
            signal += 20.0 * rng.normal(0.0, 1.0, size=width)

        return signal

    def _render_synthetic_ecg(self, class_name: str, seed: int) -> Image.Image:
        width = 512
        height = 512
        rng = np.random.default_rng(seed)
        canvas = Image.new("L", (width, height), 255)
        draw = ImageDraw.Draw(canvas)

        for x in range(0, width, 64):
            draw.line((x, 0, x, height), fill=232, width=1)
        for y in range(0, height, 64):
            draw.line((0, y, width, y), fill=232, width=1)

        signal = self._build_synthetic_ecg_signal(class_name, rng, width - 40, height - 40)
        y_values = np.clip(signal, 20.0, height - 20.0)
        x_values = np.linspace(20, width - 20, num=y_values.shape[0], dtype=np.float32)
        points = list(zip(x_values.tolist(), y_values.tolist()))
        draw.line(points, fill=32, width=4, joint="curve")

        return canvas

    def _build_class_severity(self, class_names: list[str]) -> dict[str, float]:
        severity: dict[str, float] = {}
        total = max(len(class_names), 1)
        for index, class_name in enumerate(class_names):
            label = class_name.lower()
            if "normal" in label or "healthy" in label or "sinus" in label:
                score = 0.05
            elif "afib" in label or "fibrill" in label:
                score = 0.97
            elif "flutter" in label:
                score = 0.92
            elif "tachy" in label or "vt" in label or "arrhythm" in label:
                score = 0.86
            elif "block" in label or "stemi" in label or "mi" in label:
                score = 0.78
            elif "abnormal" in label or "other" in label:
                score = 0.62
            else:
                score = min(0.2 + (0.6 * index / max(total - 1, 1)), 0.9)
            severity[class_name] = score
        return severity

    def _load_real_dataset(self) -> tuple[list[np.ndarray], list[int], list[str]] | None:
        if not self.dataset_path.exists() or not self.dataset_path.is_dir():
            return None

        class_dirs = [path for path in sorted(self.dataset_path.iterdir()) if path.is_dir()]
        samples: list[np.ndarray] = []
        labels: list[int] = []
        class_names: list[str] = []

        for class_dir in class_dirs:
            class_name = self._normalize_label(class_dir.name)
            image_files = self._collect_image_files(class_dir)
            if not image_files:
                continue

            class_index = len(class_names)
            class_names.append(class_name)
            for image_path in image_files:
                try:
                    image = self._load_image(image_path)
                    samples.append(self._vectorize_image(image))
                    labels.append(class_index)
                except Exception as exc:
                    logger.warning("Skipping ECG image %s: %s", image_path, exc)

        if len(samples) < 2 or len(class_names) < 2:
            return None

        return samples, labels, class_names

    def _build_synthetic_dataset(self) -> tuple[list[np.ndarray], list[int], list[str]]:
        samples: list[np.ndarray] = []
        labels: list[int] = []
        class_names = list(DEFAULT_SYNTHETIC_CLASSES)

        for class_index, class_name in enumerate(class_names):
            for sample_index in range(48):
                synthetic_image = self._render_synthetic_ecg(class_name, seed=class_index * 1000 + sample_index)
                samples.append(self._vectorize_image(synthetic_image))
                labels.append(class_index)

        return samples, labels, class_names

    def _load_dataset(self):
        real_dataset = self._load_real_dataset()
        if real_dataset is None:
            samples, labels, class_names = self._build_synthetic_dataset()
            self.dataset_mode = "synthetic-fallback"
            logger.info("ECG dataset not found at %s; using synthetic fallback", self.dataset_path)
        else:
            samples, labels, class_names = real_dataset
            self.dataset_mode = "real"

        x = np.asarray(samples, dtype=np.float32)
        y = np.asarray(labels, dtype=np.int64)
        self.class_names = class_names
        self.class_counts = {class_names[index]: int(count) for index, count in Counter(labels).items()}
        self.class_severity = self._build_class_severity(class_names)
        self.dataset_loaded = True

        stratify = y if len(class_names) > 1 and min(self.class_counts.values(), default=0) >= 2 else None
        test_size = 0.2 if len(x) >= 10 else 0.5

        x_train, x_test, y_train, y_test = train_test_split(
            x,
            y,
            test_size=test_size,
            random_state=42,
            stratify=stratify,
        )

        self.training_samples = int(x_train.shape[0])
        self.validation_samples = int(x_test.shape[0])
        self.onnx_feature_size = 0

        return x_train, x_test, y_train, y_test

    def _ensure_bucket(self):
        try:
            if not self.minio_client.bucket_exists(self.minio_bucket):
                self.minio_client.make_bucket(self.minio_bucket)
        except Exception as exc:
            logger.warning("MinIO bucket check failed for %s: %s", self.minio_bucket, exc)

    def _list_seed_keys(self) -> List[str]:
        keys: list[str] = []
        try:
            for obj in self.minio_client.list_objects(self.minio_bucket, prefix=self.seed_prefix, recursive=True):
                object_name = str(obj.object_name or "")
                if Path(object_name).suffix.lower() in SUPPORTED_IMAGE_SUFFIXES:
                    keys.append(object_name)
        except Exception as exc:
            logger.warning("Failed to list MinIO seed images: %s", exc)
            return []
        return sorted(keys)

    def _seed_minio_from_local(self):
        existing = self._list_seed_keys()
        if existing:
            self.seed_image_keys = existing
            logger.info("ECG seed images already present in MinIO: %s", len(existing))
            return

        if not self.local_seed_dir.exists():
            logger.info("ECG local seed folder not found at %s", self.local_seed_dir)
            self.seed_image_keys = []
            return

        candidates = self._collect_image_files(self.local_seed_dir)[: self.seed_max_upload]
        uploaded = 0
        for image_path in candidates:
            object_name = f"{self.seed_prefix}/{image_path.name}"
            try:
                payload = image_path.read_bytes()
                self.minio_client.put_object(
                    self.minio_bucket,
                    object_name,
                    io.BytesIO(payload),
                    length=len(payload),
                    content_type=self._image_content_type(image_path),
                )
                uploaded += 1
            except Exception as exc:
                logger.warning("Skipping seed image %s due to upload error: %s", image_path, exc)

        self.seed_image_keys = self._list_seed_keys()
        logger.info(
            "ECG seeds uploaded from %s: uploaded=%s available=%s",
            self.local_seed_dir,
            uploaded,
            len(self.seed_image_keys),
        )

    def _train_export_quantize(self):
        x_train, x_test, y_train, y_test = self._load_dataset()

        self.scaler = StandardScaler()
        x_train_scaled = self.scaler.fit_transform(x_train)
        x_test_scaled = self.scaler.transform(x_test)

        n_components = max(2, min(64, x_train_scaled.shape[0] - 1, x_train_scaled.shape[1]))
        self.pca = PCA(n_components=n_components, random_state=42)
        x_train_features = self.pca.fit_transform(x_train_scaled)
        x_test_features = self.pca.transform(x_test_scaled)
        self.onnx_feature_size = int(x_train_features.shape[1])

        self.model = LogisticRegression(
            max_iter=1200,
            solver="lbfgs",
            class_weight="balanced",
            multi_class="auto",
        )
        self.model.fit(x_train_features, y_train)

        probs_test = self.model.predict_proba(x_test_features)
        y_pred = np.argmax(probs_test, axis=1)

        self.metrics = {
            "accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
            "balanced_accuracy": round(float(balanced_accuracy_score(y_test, y_pred)), 4),
            "f1_macro": round(float(f1_score(y_test, y_pred, average="macro")), 4),
        }

        if self.onnx_fp32.exists():
            self.onnx_fp32.unlink()
        if self.onnx_int8.exists():
            self.onnx_int8.unlink()

        onx = to_onnx(
            self.model,
            x_train_features[:1].astype(np.float32),
            options={id(self.model): {"zipmap": False}},
            target_opset=13,
        )
        self.onnx_fp32.write_bytes(onx.SerializeToString())

        try:
            quantize_dynamic(
                model_input=str(self.onnx_fp32),
                model_output=str(self.onnx_int8),
                weight_type=QuantType.QInt8,
            )
            self.active_onnx_path = self.onnx_int8
        except Exception as exc:
            logger.warning("ECG ONNX quantization failed, falling back to FP32: %s", exc)
            self.active_onnx_path = self.onnx_fp32

        self.session = ort.InferenceSession(str(self.active_onnx_path), providers=["CPUExecutionProvider"])

    def initialize(self):
        self._train_export_quantize()
        self._ensure_bucket()
        self._seed_minio_from_local()
        logger.info(
            "ECG DL service initialized: mode=%s classes=%s metrics=%s",
            self.dataset_mode,
            self.class_names,
            self.metrics,
        )

    def _decode_image_b64(self, image_base64: str) -> Image.Image:
        payload = image_base64.split(",", 1)[-1]
        raw = base64.b64decode(payload)
        return self._load_image(raw).convert("L")

    def _synthetic_image(self, patient_id: str) -> Image.Image:
        classes = self.class_names or list(DEFAULT_SYNTHETIC_CLASSES)
        index = abs(hash(patient_id)) % len(classes)
        class_name = classes[index]
        seed = abs(hash((patient_id, class_name))) % (2**32)
        return self._render_synthetic_ecg(class_name, seed)

    def _transform_features(self, image: Image.Image) -> np.ndarray:
        if self.scaler is None or self.pca is None:
            raise RuntimeError("ECG model not initialized")
        vector = self._vectorize_image(image)
        scaled = self.scaler.transform(vector.reshape(1, -1))
        return self.pca.transform(scaled)[0].astype(np.float32)

    def _session_probabilities(self, features: np.ndarray) -> np.ndarray:
        if self.session is None or self.model is None:
            raise RuntimeError("ECG session not initialized")

        input_name = self.session.get_inputs()[0].name
        outputs = self.session.run(None, {input_name: features.reshape(1, -1).astype(np.float32)})

        probabilities: np.ndarray | None = None
        for output in outputs:
            candidate = np.asarray(output)
            if candidate.ndim == 2 and candidate.shape[1] == len(self.class_names):
                probabilities = candidate[0].astype(np.float32)
                break

        if probabilities is None:
            probabilities = self.model.predict_proba(features.reshape(1, -1))[0].astype(np.float32)

        if probabilities.shape[0] != len(self.class_names):
            probabilities = self.model.predict_proba(features.reshape(1, -1))[0].astype(np.float32)

        return probabilities

    def _risk_category(self, score: float) -> str:
        if score >= 0.85:
            return "CRITICAL"
        if score >= 0.65:
            return "HIGH"
        if score >= 0.4:
            return "MEDIUM"
        return "LOW"

    def _risk_distribution(self, score: float) -> dict:
        low = max(0.0, 1.0 - (score * 2.0))
        medium = max(0.0, 1.0 - abs(score - 0.5) * 2.2)
        high = max(0.0, 1.0 - abs(score - 0.72) * 3.0)
        critical = max(0.0, (score - 0.68) / 0.32)
        raw = {
            "LOW": low,
            "MEDIUM": medium,
            "HIGH": high,
            "CRITICAL": critical,
        }
        total = sum(raw.values())
        if total <= 0:
            return {key: 0.0 for key in raw}
        return {key: float(value / total) for key, value in raw.items()}

    def _probabilities_to_dict(self, probabilities: np.ndarray) -> dict[str, float]:
        return {
            class_name: float(probabilities[index])
            for index, class_name in enumerate(self.class_names)
        }

    def _compute_risk_score(self, probabilities: np.ndarray) -> float:
        total = 0.0
        for class_name, probability in zip(self.class_names, probabilities):
            total += float(probability) * float(self.class_severity.get(class_name, 0.5))
        return float(max(0.0, min(1.0, total)))

    def _importance_map(self, prepared_vector: np.ndarray, class_index: int) -> np.ndarray:
        if self.model is None or self.pca is None or self.scaler is None:
            raise RuntimeError("ECG model not initialized")

        coefficients = self.model.coef_
        if coefficients.ndim == 1 or coefficients.shape[0] == 1:
            class_coefficients = coefficients
        else:
            class_coefficients = coefficients[class_index]

        pixel_weights = self.pca.components_.T @ class_coefficients
        pixel_weights = pixel_weights / np.where(self.scaler.scale_ == 0, 1.0, self.scaler.scale_)
        importance = np.abs(pixel_weights * prepared_vector)
        return importance.reshape(self.image_size, self.image_size)

    def _build_heatmap(self, image: Image.Image, probabilities: np.ndarray) -> Image.Image:
        predicted_index = int(np.argmax(probabilities))
        prepared = self._vectorize_image(image)
        importance = self._importance_map(prepared, predicted_index)
        importance = importance / (importance.max() + 1e-8)

        heatmap = Image.fromarray(np.uint8(importance * 255), mode="L")
        heatmap = heatmap.resize((self.display_size, self.display_size), Image.Resampling.BILINEAR)
        heatmap = ImageOps.colorize(heatmap, black="#07111f", white="#ffb347")

        base = self._preprocess_image(image).resize((self.display_size, self.display_size), Image.Resampling.BILINEAR)
        base = base.convert("RGB")
        return Image.blend(base, heatmap, alpha=0.45)

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
        original_image = image.copy()
        features = self._transform_features(image)
        probabilities = self._session_probabilities(features)
        predicted_index = int(np.argmax(probabilities))
        predicted_class = self.class_names[predicted_index]

        risk_score = self._compute_risk_score(probabilities)
        risk_category = self._risk_category(risk_score)
        probs = self._probabilities_to_dict(probabilities)
        gradcam = self._build_heatmap(original_image, probabilities)

        image_url = None
        gradcam_url = None
        try:
            image_key, gradcam_key = self._upload_to_minio(patient_id, task_id, original_image, gradcam)
            image_url = f"minio://{self.minio_bucket}/{image_key}"
            gradcam_url = f"minio://{self.minio_bucket}/{gradcam_key}"
        except Exception as exc:
            logger.warning("MinIO upload failed: %s", exc)

        return {
            "risk_score": risk_score,
            "risk_category": risk_category,
            "predicted_class": predicted_class,
            "probabilities": probs,
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
                            "code": "25074-8",
                            "display": "Electrocardiogram narrative report",
                        }
                    ],
                    "text": "ECG image model report",
                },
                "subject": {"reference": f"Patient/{patient_id}"},
                "conclusion": (
                    f"ECG class {predicted_class} with risk {risk_category} "
                    f"(score={risk_score:.3f})"
                ),
                "presentedForm": [
                    {"contentType": "image/png", "url": image_url, "title": "Input ECG image"},
                    {"contentType": "image/png", "url": gradcam_url, "title": "ECG explanation heatmap"},
                ],
            },
        }


service = ECGImageONNXService()


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
            "ECG prediction task=%s patient=%s class=%s risk=%.3f category=%s",
            task_id,
            req.patient_id,
            out["predicted_class"],
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
    except Exception as exc:
        logger.exception("ECG DL prediction error")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/predict-image", response_model=PredictionResponse)
async def predict_image(patient_id: str = Form(...), image: UploadFile = File(...)):
    try:
        task_id = str(uuid4())
        payload = await image.read()
        pil = service._load_image(payload).convert("L")
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
    except Exception as exc:
        logger.exception("ECG DL image prediction error")
        raise HTTPException(status_code=500, detail=str(exc))


def _artifact_size_mb(path: Path) -> float | None:
    if not path.exists():
        return None
    return round(path.stat().st_size / (1024 * 1024), 3)


@app.get("/version")
async def get_version():
    return {
        "model": "ECG-Image-PCA-LogReg-ONNX",
        "task": "ECG image classification",
        "framework": "scikit-learn + ONNX Runtime",
        "quantization": "INT8" if service.active_onnx_path == service.onnx_int8 else "FP32 fallback",
        "metrics": service.metrics,
        "dataset": {
            "path": str(service.dataset_path),
            "mode": service.dataset_mode,
            "loaded": service.dataset_loaded,
            "classes": service.class_names,
            "class_counts": service.class_counts,
        },
        "input_shape": [1, service.image_size, service.image_size, 1],
        "onnx_input_shape": [1, service.onnx_feature_size],
        "artifacts": {
            "onnx_fp32_mb": _artifact_size_mb(service.onnx_fp32),
            "onnx_int8_mb": _artifact_size_mb(service.onnx_int8),
        },
        "hardware": "CPU-only",
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "dl-service",
        "dataset_loaded": service.dataset_loaded,
        "dataset_path": str(service.dataset_path),
        "dataset_mode": service.dataset_mode,
        "onnx_session_ready": service.session is not None,
        "onnx_model_path": str(service.active_onnx_path) if service.active_onnx_path else None,
        "minio_bucket": service.minio_bucket,
        "seed_images_count": len(service.seed_image_keys),
        "seed_local_dir": str(service.local_seed_dir),
        "class_count": len(service.class_names),
        "training_samples": service.training_samples,
        "validation_samples": service.validation_samples,
    }
