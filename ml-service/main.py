"""ML Service - real tabular ONNX INT8 inference with calibrated risk scores."""
import logging
import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import numpy as np
import onnxruntime as ort
import pandas as pd
from fastapi import FastAPI, HTTPException
from onnxruntime.quantization import QuantType, quantize_dynamic
from pydantic import BaseModel
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from skl2onnx import to_onnx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="ML Service", version="2.0.0")


class PredictionRequest(BaseModel):
    patient_id: str
    features: dict | None = None


class PredictionResponse(BaseModel):
    task_id: str
    patient_id: str
    risk_score: float
    risk_category: str
    is_critical: bool
    shap_values: dict
    timestamp: str


class TabularONNXService:
    def __init__(self):
        self.dataset_path = Path(os.getenv("DATASET_PATH", "/datasets/pima-diabetes.csv"))
        self.model_dir = Path("/app/models")
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.onnx_fp32 = self.model_dir / "tabular_fp32.onnx"
        self.onnx_int8 = self.model_dir / "tabular_int8.onnx"

        self.feature_names = []
        self.feature_means = None
        self.feature_medians = None
        self.label_encoder = LabelEncoder()

        self.model = None
        self.calibrator = None
        self.session = None
        self.x_test = None
        self.y_test = None
        self.metrics = {}

    def _load_dataset(self):
        if not self.dataset_path.exists():
            raise FileNotFoundError(f"Dataset not found: {self.dataset_path}")

        df = pd.read_csv(self.dataset_path)
        if df.empty:
            raise ValueError("Dataset is empty")

        target_col = None
        for candidate in ["Outcome", "Class", "target", "label"]:
            if candidate in df.columns:
                target_col = candidate
                break
        if target_col is None:
            target_col = df.columns[-1]

        y_raw = df[target_col]
        x_raw = df.drop(columns=[target_col])

        for col in x_raw.columns:
            x_raw[col] = pd.to_numeric(x_raw[col], errors="coerce")
        x_raw = x_raw.fillna(x_raw.median(numeric_only=True)).astype(np.float32)

        y = self.label_encoder.fit_transform(y_raw.astype(str))
        if len(np.unique(y)) != 2:
            raise ValueError("ML service currently expects binary target for risk scoring")

        self.feature_names = list(x_raw.columns)
        x = x_raw.to_numpy(dtype=np.float32)

        self.feature_means = x.mean(axis=0)
        self.feature_medians = np.median(x, axis=0)

        x_train, x_test, y_train, y_test = train_test_split(
            x, y, test_size=0.2, random_state=42, stratify=y
        )
        self.x_test = x_test
        self.y_test = y_test
        return x_train, x_test, y_train, y_test

    def _train_export_quantize(self):
        x_train, x_test, y_train, y_test = self._load_dataset()

        self.model = LogisticRegression(max_iter=500, solver="lbfgs")
        self.model.fit(x_train, y_train)

        # Calibrate predicted probabilities with isotonic regression.
        raw_train = self.model.predict_proba(x_train)[:, 1]
        self.calibrator = IsotonicRegression(out_of_bounds="clip")
        self.calibrator.fit(raw_train, y_train)

        raw_test = self.model.predict_proba(x_test)[:, 1]
        calibrated_test = np.asarray(self.calibrator.predict(raw_test), dtype=np.float32)
        y_pred = (calibrated_test >= 0.5).astype(np.int64)

        self.metrics = {
            "accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
            "auc_roc": round(float(roc_auc_score(y_test, calibrated_test)), 4),
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

    def initialize(self):
        self._train_export_quantize()
        logger.info("ML model initialized from %s with metrics=%s", self.dataset_path, self.metrics)

    def _sample_features(self, patient_id: str) -> np.ndarray:
        idx = abs(hash(patient_id)) % len(self.x_test)
        return self.x_test[idx]

    def _from_payload(self, features: dict | None, patient_id: str) -> np.ndarray:
        if not features:
            return self._sample_features(patient_id)
        vec = np.array([float(features.get(name, self.feature_medians[i])) for i, name in enumerate(self.feature_names)], dtype=np.float32)
        return vec

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

        # Positive class probability before calibration.
        if probs.shape[0] == 2:
            raw_prob = float(probs[1])
        else:
            raw_prob = float(np.max(probs))
        return raw_prob

    def _shap_like(self, x_vec: np.ndarray) -> dict:
        # For linear models, contribution around baseline mean is a practical SHAP approximation.
        coef = self.model.coef_[0]
        contrib = coef * (x_vec - self.feature_means)
        return {name: float(val) for name, val in zip(self.feature_names, contrib)}

    def predict(self, patient_id: str, features: dict | None) -> dict:
        x_vec = self._from_payload(features, patient_id)
        raw_prob = self._onnx_prob(x_vec)
        calibrated = float(np.asarray(self.calibrator.predict([raw_prob]))[0])
        calibrated = max(0.0, min(1.0, calibrated))

        if calibrated > 0.8:
            risk_category = "CRITICAL"
            is_critical = True
        elif calibrated > 0.6:
            risk_category = "HIGH"
            is_critical = False
        elif calibrated > 0.4:
            risk_category = "MEDIUM"
            is_critical = False
        else:
            risk_category = "LOW"
            is_critical = False

        shap_values = self._shap_like(x_vec)
        return {
            "risk_score": calibrated,
            "risk_category": risk_category,
            "is_critical": is_critical,
            "shap_values": shap_values,
        }


ml_service = TabularONNXService()


@app.on_event("startup")
async def startup_event():
    ml_service.initialize()


@app.post("/predict", response_model=PredictionResponse)
async def predict(req: PredictionRequest):
    try:
        task_id = str(uuid4())
        out = ml_service.predict(req.patient_id, req.features)

        logger.info(
            "ML prediction task=%s patient=%s risk=%.3f category=%s",
            task_id,
            req.patient_id,
            out["risk_score"],
            out["risk_category"],
        )

        return PredictionResponse(
            task_id=task_id,
            patient_id=req.patient_id,
            risk_score=out["risk_score"],
            risk_category=out["risk_category"],
            is_critical=out["is_critical"],
            shap_values=out["shap_values"],
            timestamp=datetime.utcnow().isoformat(),
        )
    except Exception as e:
        logger.exception("Prediction error")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/feedback")
async def provide_feedback(feedback: dict):
    logger.info("Feedback received: %s", feedback)
    return {"message": "Feedback recorded"}


@app.get("/version")
async def get_version():
    fp32_size = round(ml_service.onnx_fp32.stat().st_size / (1024 * 1024), 3) if ml_service.onnx_fp32.exists() else None
    int8_size = round(ml_service.onnx_int8.stat().st_size / (1024 * 1024), 3) if ml_service.onnx_int8.exists() else None

    return {
        "model": "LogisticRegression_v1",
        "framework": "ONNX Runtime",
        "quantization": "INT8",
        "calibration": "isotonic",
        "metrics": ml_service.metrics,
        "feature_count": len(ml_service.feature_names),
        "artifacts": {
            "onnx_fp32_mb": fp32_size,
            "onnx_int8_mb": int8_size,
            "dataset_path": str(ml_service.dataset_path),
        },
        "hardware": "CPU-only",
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "ml-service",
        "dataset_loaded": ml_service.x_test is not None,
        "onnx_session_ready": ml_service.session is not None,
    }
