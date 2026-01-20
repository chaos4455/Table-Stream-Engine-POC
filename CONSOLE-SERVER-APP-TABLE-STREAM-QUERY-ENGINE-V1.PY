import os
import io
import json
import yaml
import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import time
from typing import List, Optional, Union, Dict, Any, Tuple
from datetime import datetime, timezone

from fastapi import (
    FastAPI, HTTPException, status, Header, Request, Body, 
    Depends, UploadFile
)
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ValidationError

from starlette.responses import Response as StarletteResponse
from starlette.middleware.base import BaseHTTPMiddleware
from uvicorn.config import LOGGING_CONFIG

# --- 0. Configurações Globais ---
MAIN_PORT = 8888
LOGICAL_INGEST_PORT = 8888
LOGICAL_QUERY_PORT = 8999

DB_CONN: Optional[duckdb.DuckDBPyConnection] = None
TABLE_NAME = "real_time_stream_data"
ENGINE_VERSION = "4.0.0"
MAX_QUERY_TIMEOUT_SECONDS = 10 

# --- 1. Inicialização do DuckDB ---
def create_and_initialize_connection() -> duckdb.DuckDBPyConnection:
    conn = duckdb.connect(database=':memory:', read_only=False)
    
    print(f"--- Inicializando DuckDB para TSQE V{ENGINE_VERSION} em worker {os.getpid()} ---")
    
    try:
        print("Tentando instalar e carregar extensão JSON...")
        try:
            conn.execute("INSTALL json;")
            conn.execute("LOAD json;")
            print("Extensão JSON carregada com sucesso.")
        except duckdb.DuckDBError as e:
            print(f"AVISO: INSTALL falhou ({e}). Tentando apenas LOAD...")
            conn.execute("LOAD json;") 
            
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                id VARCHAR PRIMARY KEY,
                timestamp TIMESTAMP,
                data_payload JSON
            );
        """)
        
        conn.execute("SELECT 1;").fetchone()
        print(f"DuckDB pronto. Tabela '{TABLE_NAME}' configurada no worker {os.getpid()}.")
        
        return conn
        
    except Exception as e:
        print(f"ERRO CRÍTICO: Falha na inicialização do DB. Detalhe: {e}")
        raise RuntimeError(f"Falha na inicialização do DB: {e}")

# --- 2. Schemas Pydantic ---
class Record(BaseModel):
    id: str = Field(..., max_length=128)
    timestamp: str = Field(...)
    data_payload: Dict[str, Any] = Field(...)

class IngestionRequest(BaseModel):
    records: List[Record] = Field(..., min_items=1)

class QueryRequest(BaseModel):
    query_sql: str = Field(..., alias="sql")
    format: str = Field("json")
    cache_ttl: Optional[int] = Field(None)

# --- 3. Componentes Customizados ---
class YAMLResponse(StarletteResponse):
    media_type = "application/x-yaml"
    def render(self, content: any) -> bytes:
        try:
            return yaml.dump(content, default_flow_style=False, sort_keys=False).encode("utf-8")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Erro de serialização YAML: {e}")

def verify_jwt_token(authorization: Optional[str] = Header(None, alias="Authorization")) -> Dict[str, Any]:
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ")[1]
        if token == "VALID_TOKEN_123":
            return {"user": "monitor", "access": "full_read", "is_admin": False}
        if token == "ADMIN_TOKEN_456":
            return {"user": "admin_sys", "access": "full_control", "is_admin": True}
        return {"user": "unauthorized", "access": "none", "is_admin": False}
    return {"user": "guest", "access": "read_only", "is_admin": False}

# --- 4. Funções de I/O de Dados ---

def json_converter(obj):
    """Helper para serializar objetos datetime que PyArrow retorna."""
    if isinstance(obj, datetime):
        return obj.isoformat().replace('+00:00', 'Z')
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


async def parse_input_data(request: Request) -> List[Record]:
    content_type = request.headers.get("Content-Type", "").lower()
    body_bytes = b''
    
    if "multipart/form-data" in content_type:
        try:
            form = await request.form()
            file: UploadFile = form.get("file")
            if not file: raise ValueError("Arquivo 'file' não encontrado no formulário.")
            body_bytes = await file.read()
        except Exception as e: raise HTTPException(status_code=400, detail=f"Erro ao ler arquivo multipart: {e}")
    else:
        body_bytes = await request.body()

    if not body_bytes: raise HTTPException(status_code=400, detail="Corpo da requisição vazio.")

    try:
        if "application/json" in content_type:
            data = json.loads(body_bytes)
            return IngestionRequest(**data).records
        
        elif "application/x-yaml" in content_type:
            data = yaml.safe_load(body_bytes)
            return IngestionRequest(**data).records
        
        elif "application/octet-stream" in content_type or "application/x-parquet" in content_type:
            buffer = pa.BufferReader(body_bytes)
            table = pq.read_table(buffer)
            
            raw_list = table.to_pylist()
            records_list = []
            for row in raw_list:
                payload_data = row.get('data_payload')
                if isinstance(payload_data, str): 
                    payload_data = json.loads(payload_data)
                
                timestamp_str = row.get('timestamp')
                if hasattr(timestamp_str, 'isoformat'): 
                    timestamp_str = timestamp_str.isoformat()
                
                records_list.append(Record(
                    id=str(row.get('id')), timestamp=timestamp_str, data_payload=payload_data
                ))
            
            IngestionRequest(records=records_list) 
            return records_list
        else:
            raise HTTPException(status_code=415, detail=f"Tipo de mídia não suportado: {content_type}.")
    
    except ValidationError as e:
        raise HTTPException(status_code=422, detail={"message": "Erro de validação Pydantic", "errors": e.errors()})
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro no processamento da estrutura: {type(e).__name__} - {e}")


def format_output_data(data: pa.Table, response_format: str) -> Union[JSONResponse, YAMLResponse, StreamingResponse]:
    """Formata a tabela Arrow de saída no formato solicitado, tratando a serialização JSON."""
    
    if data.num_rows == 0:
        return JSONResponse(content={"message": "Nenhum resultado encontrado."}, status_code=200)

    try:
        if response_format == 'json':
            list_of_dicts = data.to_pylist()
            
            # --- CORREÇÃO DO ERRO DE SERIALIZAÇÃO DE DATETIME ---
            # Usamos json.dumps manual com o conversor e retornamos StarletteResponse,
            # para forçar a serialização correta de objetos datetime vindos do PyArrow.
            json_string = json.dumps(list_of_dicts, default=json_converter)
            return StarletteResponse(content=json_string, media_type="application/json")
            # ----------------------------------------------------
        
        elif response_format == 'yaml':
            list_of_dicts = data.to_pylist()
            return YAMLResponse(content=list_of_dicts)
        
        elif response_format == 'parquet':
            buffer = io.BytesIO()
            pq.write_table(data, buffer)
            buffer.seek(0)
            
            return StreamingResponse(
                content=buffer, media_type="application/x-parquet",
                headers={"Content-Disposition": "attachment; filename=query_data.parquet"}
            )
        
        raise HTTPException(status_code=400, detail="Formato de saída não suportado.")
        
    except Exception as e:
        # Este é o ponto onde o erro original ocorreu
        raise HTTPException(status_code=500, detail=f"Erro na serialização ou conversão de saída: {e}")


# --- 5. Definição da Aplicação FastAPI ---
app = FastAPI(
    title=f"TSQE {ENGINE_VERSION}: Table Stream Query Engine (Monolith)",
    description="Engine de Alta Performance para Streaming de Dados e Query em Tempo Real.",
    version=ENGINE_VERSION
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    global DB_CONN
    DB_CONN = create_and_initialize_connection()
    if DB_CONN is None:
        raise RuntimeError("Falha na inicialização da conexão DuckDB no worker.")


# --- 6. Rotas de Ingestão (8888) ---
@app.post("/api/v1/ingest", status_code=status.HTTP_201_CREATED, tags=[f"Ingestion (Lógica {LOGICAL_INGEST_PORT})"])
async def ingest_data_stream(request: Request):
    try:
        records = await parse_input_data(request)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro de parsing ou formato inesperado: {e}")
    
    data_to_insert: List[Tuple] = [(r.id, r.timestamp, json.dumps(r.data_payload)) for r in records]
    
    global DB_CONN
    if DB_CONN is None:
        raise HTTPException(status_code=503, detail="DuckDB não inicializado ou worker não configurado.")

    try:
        insert_query = f"""
            INSERT INTO {TABLE_NAME} (id, timestamp, data_payload) VALUES (?, ?, ?)
            ON CONFLICT (id) 
            DO UPDATE SET 
                timestamp = excluded.timestamp, 
                data_payload = excluded.data_payload;
        """
        DB_CONN.executemany(insert_query, data_to_insert)
        DB_CONN.commit() 
        
        return {"status": "success", "count": len(data_to_insert), "message": "Dados ingeridos e stream atualizado."}
    
    except duckdb.DuckDBError as e:
        DB_CONN.rollback()
        print(f"ERRO DUCKDB: Falha na Ingestão: {e}")
        raise HTTPException(status_code=500, detail=f"Erro de Banco de Dados durante a ingestão: {e}")
    except Exception as e:
        DB_CONN.rollback()
        raise HTTPException(status_code=500, detail=f"Erro interno: {e}")


# --- 7. Rotas de Query/Serviço (8999) ---
@app.post("/api/v1/query", tags=[f"Query & Stream (Lógica {LOGICAL_QUERY_PORT})"])
async def query_data_stream_post(
    auth_data: Dict[str, Any] = Depends(verify_jwt_token),
    query_body: QueryRequest = Body(...),
):
    
    query_sql = query_body.query_sql
    output_format = query_body.format.lower()
    
    if auth_data.get('access') == 'none':
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Acesso negado. Token JWT inválido.")

    normalized_sql = query_sql.strip().upper()
    
    if not normalized_sql.startswith("SELECT") or any(cmd in normalized_sql for cmd in ["DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "CREATE", "ATTACH", "DETACH"]):
         raise HTTPException(status_code=403, detail="Apenas consultas SELECT puras e não destrutivas são permitidas.")
         
    global DB_CONN
    if DB_CONN is None:
        raise HTTPException(status_code=503, detail="DuckDB não inicializado ou worker não configurado.")
         
    try:
        start_time = time.time()
        
        arrow_table = DB_CONN.execute(query_sql).arrow()
        latency = (time.time() - start_time) * 1000
        
        print(f"[QUERY] User: {auth_data.get('user')}. Execução: {latency:.2f} ms. Linhas: {arrow_table.num_rows}")
        
    except duckdb.DuckDBError as e:
        raise HTTPException(status_code=400, detail=f"Erro DuckDB na Query: {e}")
    except Exception as e:
        print(f"ERRO CRÍTICO NA QUERY: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno ao processar a query: {e}")
    
    return format_output_data(arrow_table, output_format)


@app.get("/api/v1/status", tags=["Status e Healthcheck"])
async def get_status():
    
    global DB_CONN
    if DB_CONN is None:
        raise HTTPException(status_code=503, detail="DuckDB não inicializado ou worker não configurado.")

    try:
        start_time = time.time()
        count = DB_CONN.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0]
        DB_CONN.execute("SELECT 1;").fetchone()
        latency = (time.time() - start_time) * 1000
        
        return {
            "engine_status": "ONLINE",
            "version": ENGINE_VERSION,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "database": "DuckDB In-Memory",
            "record_count": count,
            "db_latency_ms": f"{latency:.3f}",
            "logical_ports": {"ingest": LOGICAL_INGEST_PORT, "query": LOGICAL_QUERY_PORT},
            "security_active": True
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Serviço indisponível. Erro no DuckDB: {str(e)}")


# --- 8. Execução da Aplicação ---

if __name__ == "__main__":
    import uvicorn
    
    # Obtém o nome do arquivo atual para a string de importação (ex: "app_engine:app")
    app_module_name = os.path.splitext(os.path.basename(__file__))[0]
    app_import_string = f"{app_module_name}:app"
    
    print(f"\n--- INICIANDO TABLE STREAM QUERY ENGINE V{ENGINE_VERSION} ---")
    print(f"API rodando em http://0.0.0.0:{MAIN_PORT}")
    
    uvicorn.run(
        app_import_string, 
        host="0.0.0.0", 
        port=MAIN_PORT, 
        log_config=LOGGING_CONFIG,
        workers=os.cpu_count() or 1 
    )