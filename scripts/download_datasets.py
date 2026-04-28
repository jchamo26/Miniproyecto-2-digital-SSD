#!/usr/bin/env python3
"""
Script to download datasets for Miniproyecto2_SSD
- PIMA Indians Diabetes from UCI ML Repository
- APTOS 2019 from Kaggle (requires kaggle API)
"""

import os
import sys
import pandas as pd
from ucimlrepo import fetch_ucirepo

def download_pima():
    """Download PIMA Indians Diabetes dataset"""
    print("📥 Descargando PIMA Indians Diabetes dataset...")

    try:
        # Fetch dataset
        pima = fetch_ucirepo(id=52)  # PIMA Indians Diabetes ID

        # Get data
        X = pima.data.features
        y = pima.data.targets

        # Combine features and target
        df = pd.concat([X, y], axis=1)

        # Save to CSV
        output_path = os.path.join(os.path.dirname(__file__), '..', 'datasets', 'pima-diabetes.csv')
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        df.to_csv(output_path, index=False)

        print(f"✅ PIMA Diabetes: {len(df)} casos guardados en {output_path}")

    except Exception as e:
        print(f"❌ Error descargando PIMA: {e}")
        return False

    return True

def download_aptos():
    """Download APTOS 2019 dataset from Kaggle"""
    print("📥 Descargando APTOS 2019 dataset...")

    try:
        import kaggle

        # Download competition data
        kaggle.api.competition_download_files('aptos2019-blindness-detection',
                                            path=os.path.join(os.path.dirname(__file__), '..', 'datasets'),
                                            quiet=False)

        # Unzip
        import zipfile
        zip_path = os.path.join(os.path.dirname(__file__), '..', 'datasets', 'aptos2019-blindness-detection.zip')
        extract_path = os.path.join(os.path.dirname(__file__), '..', 'datasets', 'aptos2019')

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_path)

        print(f"✅ APTOS 2019: Dataset descargado en {extract_path}")

    except ImportError:
        print("❌ Kaggle API no instalada. Instala con: pip install kaggle")
        print("   También necesitas configurar ~/.kaggle/kaggle.json con tus credenciales")
        return False
    except Exception as e:
        print(f"❌ Error descargando APTOS: {e}")
        return False

    return True

def main():
    print("🚀 Iniciando descarga de datasets...\n")

    success_count = 0

    if download_pima():
        success_count += 1

    if download_aptos():
        success_count += 1

    print(f"\n🎯 Descargas completadas: {success_count}/2")

    if success_count == 2:
        print("🎉 Todos los datasets listos para seed_patients.py")
    else:
        print("⚠️ Algunos datasets fallaron. Revisa los errores arriba.")

if __name__ == "__main__":
    main()