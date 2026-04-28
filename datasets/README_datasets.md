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

## 🫀 ECG Images Dataset (para DL service)

### Objetivo en este repo
- Clasificación de imágenes de ECG con 4 clases clínicas.
- El `dl-service` puede usar imágenes reales del dataset **o generar trazados sintéticos** cuando el directorio no está disponible.

### Clases esperadas
| Carpeta | Descripción clínica | Riesgo |
|---|---|---|
| `Normal` | Ritmo sinusal normal | LOW |
| `Atrial Fibrillation` | Fibrilación auricular | HIGH |
| `ST-Elevation MI` | Infarto agudo con elevación del ST (STEMI) | CRITICAL |
| `Other Arrhythmia` | Otras arritmias / bloqueos | MEDIUM |

### Estructura esperada local
```text
datasets/
└── ecg-images/
    └── images/
        ├── Normal/
        │   ├── ecg_001.png
        │   └── ...
        ├── Atrial Fibrillation/
        │   ├── ecg_af_001.png
        │   └── ...
        ├── ST-Elevation MI/
        │   ├── ecg_stemi_001.png
        │   └── ...
        └── Other Arrhythmia/
            ├── ecg_other_001.png
            └── ...
```

### Fuentes de datos recomendadas
- **PhysioNet / MIT-BIH** (acceso libre): https://physionet.org/content/mitdb/1.0.0/
- **PTB-XL ECG Image Dataset** (Kaggle): buscar "ECG Images Dataset" en Kaggle
- Cualquier dataset de imágenes ECG con al menos una carpeta por clase

### Comportamiento automático del servicio
1. Al iniciar, el `dl-service` revisa `DL_LOCAL_IMAGE_DIR` (`/datasets/ecg-images/images`).
2. Si no hay imágenes reales, **genera automáticamente datos sintéticos** (trazados ECG procedurales) para entrenar el modelo demo.
3. Si hay imágenes reales, las usa para entrenamiento y las sube a MinIO como seeds.
4. En inferencia sin imagen del usuario, elige una seed de MinIO (determinística por `patient_id`) o genera un trazado sintético.

### Variables de entorno relevantes (docker-compose)
```yaml
DL_LOCAL_IMAGE_DIR=/datasets/ecg-images/images
DL_MINIO_SEED_PREFIX=seed/ecg-images
DL_SEED_MAX_UPLOAD=300
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
