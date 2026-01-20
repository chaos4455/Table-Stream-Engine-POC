import time
import requests
import json
import random
from datetime import datetime, timezone
from faker import Faker
from typing import List, Dict, Any

# --- Configurações do Stream ---
# Nota: O endereço 127.0.0.1 (localhost) é usado. Mude se o Engine estiver em Docker/rede diferente.
ENGINE_INGEST_URL = "http://127.0.0.1:8888/api/v1/ingest"
NUM_STORES = 5                 
SENSORS_PER_STORE = 40         
NUM_SENSORS = NUM_STORES * SENSORS_PER_STORE

UPDATE_INTERVAL_SECONDS = 10
SENSOR_TYPE = "Freezer_Temp"

# Inicialização do Faker
fake = Faker('pt_BR')

# Lista de IDs das filiais
STORE_IDS = [f"STORE_{chr(65 + i)}" for i in range(NUM_STORES)]

# Estrutura para manter o estado atual de cada sensor
SENSORS_METADATA: List[Dict[str, Any]] = []

# --- Funções de Geração de Dados ---

def generate_sensor_metadata():
    """Cria os metadados iniciais para todos os sensores, distribuídos por filiais."""
    print(f"Gerando metadados para {NUM_SENSORS} sensores em {NUM_STORES} filiais...")
    
    sensor_counter = 0
    for store_id in STORE_IDS:
        for i in range(SENSORS_PER_STORE):
            sensor_id = f"{store_id}_{SENSOR_TYPE}_{i:03d}"
            
            location = f"Aisle {random.randint(1, 10)} - Zone {random.choice(['Dairy', 'Meat', 'Frozen'])}"
            
            # Define um valor base de temperatura (e.g., -18°C para freezer)
            base_temp = random.uniform(-25.0, -15.0) 
            
            SENSORS_METADATA.append({
                "id": sensor_id,
                "store_id": store_id,
                "location": location,
                "base_temp": base_temp,
                "manufacturer": fake.company(),
            })
            sensor_counter += 1
    
    print(f"Total de {sensor_counter} metadados gerados com sucesso.")

def generate_sensor_reading(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Gera uma leitura de temperatura realista com simulação de anomalias."""
    
    base_temp = metadata['base_temp']
    
    # Ruído normal
    current_temp = base_temp + random.uniform(-0.5, 0.5)
    
    # Simulação de Anomalia (probabilidade de 1 em 50)
    status = "NORMAL"
    if random.randint(1, 50) == 1:
        current_temp += random.uniform(2.0, 5.0)
        status = "ALERT"
        
    current_time_iso = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    
    record = {
        "id": metadata['id'],
        "timestamp": current_time_iso,
        "data_payload": {
            "sensor_location": metadata['location'],
            "temperature_celsius": round(current_temp, 2),
            "humidity_percent": random.randint(60, 85),
            "status": status,
            "store_id": metadata['store_id'],
            "last_maintenance": fake.date_this_year().isoformat()
        }
    }
    
    return record

# --- Funções de Ingestão e Loop Principal ---

def ingest_data_to_engine(records: List[Dict[str, Any]]):
    """Envia o lote de dados para o endpoint de ingestão da Engine."""
    
    payload = {"records": records}
    headers = {"Content-Type": "application/json"}
    
    try:
        start_time = time.time()
        
        response = requests.post(ENGINE_INGEST_URL, json=payload, headers=headers, timeout=5)
        response.raise_for_status()
        
        latency = (time.time() - start_time) * 1000
        response_data = response.json()
        
        print(f"| Lote Ingerido: {response_data.get('count', len(records))} registros. | Latência Ingestão: {latency:.2f} ms")
        
    except requests.exceptions.HTTPError as errh:
        status_code = response.status_code if 'response' in locals() else 'N/A'
        detail = response.text if 'response' in locals() else 'N/A'
        print(f"ERRO HTTP ({status_code}): Falha na Ingestão. Detalhe: {detail[:100]}...")
    except requests.exceptions.ConnectionError:
        print(f"ERRO CONEXÃO: Certifique-se de que a Engine está rodando em {ENGINE_INGEST_URL} (Porta 8888).")
    except requests.exceptions.Timeout:
        print("ERRO TIMEOUT: A Engine não respondeu a tempo.")
    except Exception as e:
        print(f"ERRO DESCONHECIDO DURANTE INGESTÃO: {type(e).__name__} - {e}")

def main_injector_loop():
    """Loop principal que gera e injeta os dados de forma contínua."""
    
    generate_sensor_metadata()
    
    print("\n=======================================================")
    print(f"TSQE DATA INJECTOR V2: Ativo.")
    print(f"Total de sensores: {NUM_SENSORS} | Atualização: {UPDATE_INTERVAL_SECONDS}s")
    print(f"Filiais Simuladas: {', '.join(STORE_IDS)}")
    print("=======================================================")
    
    cycle = 1
    while True:
        start_loop_time = time.time()
        
        print(f"\n--- Ciclo #{cycle} (TSQE Time: {datetime.now(timezone.utc).isoformat()}) ---")
        
        # 1. Geração do Lote de Dados
        new_records = []
        for metadata in SENSORS_METADATA:
            record = generate_sensor_reading(metadata)
            new_records.append(record)
            
        # 2. Ingestão
        ingest_data_to_engine(new_records)
        
        # 3. Gerenciamento do Tempo
        end_loop_time = time.time()
        elapsed_time = end_loop_time - start_loop_time
        
        wait_time = UPDATE_INTERVAL_SECONDS - elapsed_time
        
        if wait_time > 0:
            time.sleep(wait_time)
            print(f"Loop concluído em {elapsed_time:.2f}s. Aguardando {wait_time:.2f}s.")
        else:
            print(f"AVISO: Loop demorou {elapsed_time:.2f}s (excedeu o intervalo). Sem pausa.")
            
        cycle += 1

if __name__ == "__main__":
    try:
        main_injector_loop()
    except KeyboardInterrupt:
        print("\n[INJECTOR] Encerrado pelo usuário.")
    except Exception as e:
        print(f"\n[INJECTOR] Um erro crítico ocorreu: {e}")