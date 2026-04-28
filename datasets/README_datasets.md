# 📊 Datasets - Instrucciones de Descarga

Esta carpeta debe contener los datasets para generar pacientes sintéticos. **NO incluya archivos de datos en el repositorio** (ver `.gitignore`).

## 🌾 PIMA Indians Diabetes - UCI ML

### Descripción
- **Casos:** 768 observaciones
- **Features:** 8 variables clínicas (Glucose, BloodPressure, BMI, Insulin, Age, Pregnancies, etc.)
- **Target:** Binario (0/1) - Diabetes presente/ausente
- **Licencia:** Public domain (UCI Machine Learning Repository)

### Descarga

**Opción 1: Manualmente desde UCI ML Repository**
```bash
cd datasets
wget https://archive.ics.uci.edu/ml/machine-learning-databases/pima-indians-diabetes/pima-indians-diabetes.data
# Renombrar a pima-diabetes.csv y agregar headers
```

**Opción 2: Desde Kaggle**
```bash
kaggle datasets download -d uciml/pima-indians-diabetes-database
unzip pima-indians-diabetes-database.zip
```

**Opción 3: Script automatizado**
```bash
python download_datasets.py
```

### Estructura esperada
```csv
Pregnancies,Glucose,BloodPressure,SkinThickness,Insulin,BMI,DiabetesPedigree,Age,Outcome
6,148,72,35,0,33.6,0.627,50,1
1,85,66,29,0,26.6,0.351,31,0
...
```

---

## 🖼️ APTOS 2019 - Kaggle Diabetic Retinopathy

### Descripción
- **Imágenes:** 3662 fundus (retina) images
- **Clases:** 5 (0=Normal, 1=Mild, 2=Moderate, 3=Severe, 4=Proliferative)
- **Formato:** JPG color 224×224 recomendado
- **Licencia:** CC Available for use under CC0/Public Domain

### Descarga

**Opción 1: Desde Kaggle (requiere cuenta)**
```bash
kaggle competitions download -c aptos2019-blindness-detection
cd aptos2019-blindness-detection
unzip train_images.zip
unzip test_images.zip
```

**Opción 2: Google Drive (alternativa)**
- Acceso limitado en algunas regiones
- Script disponible en `download_datasets.py`

### Estructura esperada
```
datasets/
├── aptos2019/
│   ├── train_images/
│   │   ├── 000c1434d8d7_left.jpeg
│   │   ├── 000f6bfdd236_right.jpeg
│   │   └── ...
│   └── train.csv
```

**CSV con labels:**
```csv
id_code,diagnosis
000c1434d8d7_left,2
000f6bfdd236_right,4
...
```

---

## 🫀 ECG Images Dataset (DL principal en este proyecto)

### Objetivo en este repo
- Cargar imagenes ECG por carpeta a MinIO automaticamente para que el `dl-service` las use cuando no se envia `image_base64`.
- Estructura esperada: una carpeta por clase, por ejemplo `normal/`, `abnormal/`, `afib/`.

### Estructura esperada local
Copie imagenes JPG/PNG (una muestra pequena para demo) en:

```text
datasets/
└── ecg-images/
    ├── normal/
    │   ├── 00000001.png
    │   └── ...
    ├── abnormal/
    │   └── ...
    └── afib/
        └── ...
```

### Comportamiento automatico
- `dl-service` revisa `/datasets/ecg-images` al iniciar.
- Si MinIO no tiene objetos bajo `seed/ecg/`, sube hasta `DL_SEED_MAX_UPLOAD` imagenes.
- Luego, en inferencia DL sin imagen cargada por usuario, selecciona una imagen seed desde MinIO (deterministica por `patient_id`).
- Si no hay seeds disponibles, usa fallback sintetico ECG.

### Variables relevantes (docker-compose)
- `ECG_DATASET_PATH=/datasets/ecg-images`
- `DL_LOCAL_IMAGE_DIR=/datasets/ecg-images`
- `DL_MINIO_SEED_PREFIX=seed/ecg`
- `DL_SEED_MAX_UPLOAD=300`

### Script recomendado
```bash
python scripts/prepare_ecg_dataset.py
```

Si ya tiene un dataset ECG con carpetas por clase, puede copiarlo con:
```bash
python scripts/prepare_ecg_dataset.py --source /ruta/a/su/ecg-dataset
```

---

## 📥 Script Automatizado (Recomendado)

```bash
# Solo necesita internet y credenciales Kaggle
python scripts/download_datasets.py

# Output esperado:
# ✅ PIMA Diabetes: 768 casos
# ✅ APTOS 2019: 3662 imágenes descargadas
# 🎯 Listo para seed_patients.py
```

---

## ⚙️ Alternativas para Testing

Si no puede descargar los datasets reales:

### Mock Data (Testing Local)
```python
# En seed_patients.py, generar datos sintéticos
import numpy as np
n_samples = 50
mock_pima = {
    'Glucose': np.random.uniform(60, 200, n_samples),
    'BloodPressure': np.random.uniform(40, 130, n_samples),
    'BMI': np.random.uniform(18, 45, n_samples),
    # ...
}
```

### Imágenes Sintéticas
```python
from PIL import Image
import numpy as np

for i in range(20):
    img_array = np.random.randint(0, 256, (224, 224, 3), dtype=np.uint8)
    img = Image.fromarray(img_array)
    img.save(f'datasets/aptos2019/train_images/{i:06d}_left.jpeg')
```

---

## 🔗 Licencias

| Dataset | Origen | Licencia | Atribución |
|---|---|---|---|
| PIMA Diabetes | UCI ML | Public Domain | Smith, J. et al. (1988) |
| APTOS 2019 | Kaggle | CC0 | Aravind Eye Hospital |

---

## ❓ FAQs

### P: ¿Puedo usar otros datasets?
**R:** Sí, siempre que sean:
- Públicos o con licencia permisiva
- PIMA: 🔴 tabular, 8+ features, binario o multiclase
- APTOS: 🔴 imágenes médicas, 224×224+, 5+ clases

### P: ¿Qué pasa si descargo imágenes pero no datos tabulares?
**R:** El sistema genera datos sintéticos PIMA automáticamente si no encuentra `pima-diabetes.csv`.

### P: ¿Cuánto espacio necesito?
**R:** 
- PIMA: ~5 KB (CSV)
- APTOS: ~3 GB (3662 imágenes)
- **Total:** ~3 GB

### P: ¿Puedo usar datos del dispositivo local?
**R:** Sí, copie los CSVs a `datasets/` y las imágenes a `datasets/aptos2019/train_images/`.

---

**Última actualización:** 09/04/2026  
**Versión:** 2.0.0
