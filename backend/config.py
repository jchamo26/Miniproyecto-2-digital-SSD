"""Configuration module for FastAPI backend"""
import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Application settings from environment variables"""
    
    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://user:password@localhost/clinical_db"
    )
    
    # API Keys
    DEFAULT_ACCESS_KEY: str = os.getenv("DEFAULT_ACCESS_KEY", "CHANGE_ME_ADMIN_ACCESS_KEY")
    DEFAULT_PERMISSION_KEY: str = os.getenv("DEFAULT_PERMISSION_KEY", "admin")
    DEFAULT_MEDICO_ACCESS_KEY_1: str = os.getenv("DEFAULT_MEDICO_ACCESS_KEY_1", "CHANGE_ME_MEDICO_KEY_1")
    DEFAULT_MEDICO_ACCESS_KEY_2: str = os.getenv("DEFAULT_MEDICO_ACCESS_KEY_2", "CHANGE_ME_MEDICO_KEY_2")
    DEFAULT_PACIENTE_ACCESS_KEY_1: str = os.getenv("DEFAULT_PACIENTE_ACCESS_KEY_1", "CHANGE_ME_PACIENTE_KEY_1")
    
    # JWT
    JWT_SECRET: str = os.getenv("JWT_SECRET", "CHANGE_ME_JWT_SECRET")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = 8
    
    # MinIO
    MINIO_ENDPOINT: str = os.getenv("MINIO_ENDPOINT", "minio:9000")
    MINIO_ACCESS_KEY: str = os.getenv("MINIO_ACCESS_KEY", "CHANGE_ME_MINIO_ACCESS_KEY")
    MINIO_SECRET_KEY: str = os.getenv("MINIO_SECRET_KEY", "CHANGE_ME_MINIO_SECRET_KEY")
    MINIO_BUCKET: str = "clinical-images"
    MINIO_SECURE: bool = False
    
    # Mailhog
    MAILHOG_HOST: str = os.getenv("MAILHOG_HOST", "mailhog")
    MAILHOG_PORT: int = int(os.getenv("MAILHOG_PORT", 1025))
    
    # FHIR Server
    FHIR_SERVER_URL: str = os.getenv("FHIR_SERVER_URL", "http://fhir-server:8080/fhir")
    
    # Rate limiting
    RATE_LIMIT_ENABLED: bool = True
    INFERENCE_RATE_LIMIT: int = 10  # per minute per key
    
    # CORS
    ALLOWED_ORIGINS: str = os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost,http://localhost:3000,http://localhost:5173,https://localhost,https://localhost:3000,http://frontend:3000"
    )
    
    # Environment
    ENV: str = os.getenv("ENV", "development")

    # Dataset bootstrap
    DATASET_PATH: str = os.getenv("DATASET_PATH", "/datasets/heart-disease.csv")
    AUTO_SEED_HEART_DATASET: bool = os.getenv("AUTO_SEED_HEART_DATASET", "true").lower() in ("1", "true", "yes")
    
    class Config:
        env_file = ".env"

settings = Settings()
