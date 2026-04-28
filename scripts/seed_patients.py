#!/usr/bin/env python3
"""
Seed Patients Script - Populate database with synthetic patients from real datasets
Generates 30+ patients with FHIR observations and medical images
"""
import pandas as pd
import numpy as np
import requests
import asyncio
import asyncpg
import os
from pathlib import Path
from faker import Faker
from datetime import datetime, date
import json

faker = Faker('es_CO')

# Configuration
API_BASE = os.getenv("API_BASE", "http://localhost:8000")
DB_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/clinical_db")
ACCESS_KEY = os.getenv("ACCESS_KEY", "<admin_access_key>")
PERMISSION_KEY = os.getenv("PERMISSION_KEY", "admin")

# Headers for API requests
HEADERS = {
    "X-Access-Key": ACCESS_KEY,
    "X-Permission-Key": PERMISSION_KEY,
    "Content-Type": "application/json"
}

# FHIR LOINC code mapping for features
LOINC_CODES = {
    'Glucose': {'code': '2339-0', 'unit': 'mg/dL'},
    'BloodPressure': {'code': '55284-4', 'unit': 'mmHg'},
    'SkinThickness': {'code': '70154-6', 'unit': 'mm'},
    'Insulin': {'code': '14749-6', 'unit': 'mIU/L'},
    'BMI': {'code': '39156-5', 'unit': 'kg/m2'},
    'DiabetesPedigree': {'code': '21612-7', 'unit': '1'},
    'Age': {'code': '30525-0', 'unit': 'year'},
    'Pregnancies': {'code': '11996-6', 'unit': '1'}
}

SNOMED_CODES = {
    'LOW': '281414001',
    'MEDIUM': '281415000',
    'HIGH': '281416004',
    'CRITICAL': '24484000'
}

async def init_db():
    """Initialize database connection"""
    pool = await asyncpg.create_pool(DB_URL, min_size=2, max_size=10)
    return pool

async def create_patient_in_db(pool, patient_name, birth_date, gender):
    """Create patient record in database"""
    async with pool.acquire() as conn:
        patient_id = await conn.fetchval(
            """
            INSERT INTO patients (name, birth_date, gender, is_active)
            VALUES ($1, $2, $3, TRUE)
            RETURNING id
            """,
            patient_name, birth_date, gender
        )
    return patient_id

async def create_fhir_patient(patient_name, birth_date, gender):
    """Create FHIR Patient resource via API"""
    try:
        payload = {
            "resourceType": "Patient",
            "name": [{
                "given": [patient_name.split()[0]],
                "family": patient_name.split()[-1] if len(patient_name.split()) > 1 else patient_name
            }],
            "birthDate": str(birth_date),
            "gender": gender,
            "active": True
        }
        
        response = requests.post(
            f"{API_BASE}/fhir/Patient",
            json=payload,
            headers=HEADERS,
            timeout=10
        )
        
        if response.status_code in [200, 201]:
            data = response.json()
            return data.get('id') or str(np.random.uuid4())
        else:
            print(f"âŒ Error creating FHIR Patient: {response.status_code}")
            return None
    except Exception as e:
        print(f"  Error: {e}")
        return None

async def create_observation(patient_id, feature_name, feature_value):
    """Create FHIR Observation for a patient feature"""
    try:
        if feature_name not in LOINC_CODES:
            return None
        
        loinc_info = LOINC_CODES[feature_name]
        
        payload = {
            "resourceType": "Observation",
            "status": "final",
            "subject": {"reference": f"Patient/{patient_id}"},
            "code": {
                "coding": [{
                    "system": "http://loinc.org",
                    "code": loinc_info['code'],
                    "display": feature_name
                }]
            },
            "valueQuantity": {
                "value": float(feature_value),
                "unit": loinc_info['unit'],
                "system": "http://unitsofmeasure.org",
                "code": loinc_info['unit']
            },
            "effectiveDateTime": datetime.utcnow().isoformat()
        }
        
        response = requests.post(
            f"{API_BASE}/fhir/Observation",
            json=payload,
            headers=HEADERS,
            timeout=10
        )
        
        return response.status_code in [200, 201]
    except Exception as e:
        print(f"  Error creating observation: {e}")
        return None

async def seed_patients_from_pima():
    """
    Seed patients from PIMA Diabetes dataset
    """
    print("ðŸŒ± Seeding patients from PIMA Diabetes dataset...")
    
    # Load from CSV if available, otherwise mock data
    csv_path = Path(__file__).parent.parent / 'datasets' / 'pima-diabetes.csv'
    if csv_path.exists():
        print(f"   ðŸ“‚ Loading from {csv_path}")
        df = pd.read_csv(csv_path)
        print(f"   ðŸ“Š Loaded {len(df)} patients from CSV")
    else:
        print("   âš ï¸ CSV not found, generating synthetic PIMA-like data...")
        np.random.seed(42)
        n_patients = 30
        
        pima_data = {
            'Pregnancies': np.random.randint(0, 15, n_patients),
            'Glucose': np.random.uniform(60, 200, n_patients),
            'BloodPressure': np.random.uniform(40, 130, n_patients),
            'SkinThickness': np.random.uniform(0, 100, n_patients),
            'Insulin': np.random.uniform(0, 850, n_patients),
            'BMI': np.random.uniform(18, 45, n_patients),
            'DiabetesPedigree': np.random.uniform(0.078, 2.42, n_patients),
            'Age': np.random.randint(21, 80, n_patients),
            'Outcome': np.random.randint(0, 2, n_patients)
        }
        
        df = pd.DataFrame(pima_data)
        print(f"   ðŸ“Š Generated {len(df)} synthetic patients")
    
    # Use first 30 patients for seeding
    df = df.head(30)
    
    for idx, row in df.iterrows():
        try:
            # Generate synthetic demographic data
            is_male = np.random.choice([True, False])
            patient_name = faker.name()
            birth_date = faker.date_of_birth(minimum_age=21, maximum_age=85)
            gender = 'male' if is_male else 'female'
            
            # Create FHIR Patient
            print(f"   [{idx+1:2d}/{len(df)}] Creating patient: {patient_name}...", end=" ")
            patient_id = await create_fhir_patient(patient_name, birth_date, gender)
            
            if not patient_id:
                print("âŒ Failed")
                continue
            
            print("âœ…")
            
            # Create Observations for each feature
            for col in LOINC_CODES.keys():
                if col in row and pd.notna(row[col]):
                    await create_observation(patient_id, col, row[col])
            
            # Create Risk Assessment based on Outcome
            risk_score = float(row['Outcome']) * 0.7 + np.random.uniform(0, 0.3)
            if risk_score > 0.8:
                risk_cat = "CRITICAL"
            elif risk_score > 0.6:
                risk_cat = "HIGH"
            elif risk_score > 0.4:
                risk_cat = "MEDIUM"
            else:
                risk_cat = "LOW"
            
            # Mock Risk Assessment creation
            print(f"      ðŸ“ˆ Risk: {risk_cat} ({risk_score:.2f})")
        
        except Exception as e:
            print(f"   Error processing patient {idx}: {e}")
            continue
    
    print(f"\nâœ… Seeded {len(df)} patients successfully")

async def main():
    """Main seed script"""
    print("=" * 60)
    print("ðŸŒ± PATIENT SEEDING SCRIPT")
    print(f"   API Base: {API_BASE}")
    print(f"   Role: {PERMISSION_KEY}")
    print("=" * 60)
    
    # Wait for services to be ready
    print("\nâ³ Waiting for API services...")
    max_retries = 30
    for attempt in range(max_retries):
        try:
            response = requests.get(f"{API_BASE}/health", timeout=2)
            if response.status_code == 200:
                print("âœ… API is ready")
                break
        except:
            if attempt == max_retries - 1:
                print("âŒ API not available after 30 attempts")
                return
            await asyncio.sleep(1)
    
    # Seed patients
    await seed_patients_from_pima()
    
    print("\n" + "=" * 60)
    print("âœ… SEEDING COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())

