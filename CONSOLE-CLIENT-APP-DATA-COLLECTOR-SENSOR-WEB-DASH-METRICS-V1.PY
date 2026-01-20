import time
import requests
import json
from typing import Dict, Any, List, Optional
import os 

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from datetime import datetime, timezone

# --- Configurações e Constantes ---
TSQE_QUERY_URL = "http://127.0.0.1:8888/api/v1/query"
CONSUMER_PORT = 8080
UPDATE_INTERVAL_SECONDS = 10 
DASHBOARD_VERSION = "4.1.1" # Versão atualizada
MAX_REQUEST_TIMEOUT = 8

# --- Schemas Pydantic ---

class GlobalKPI(BaseModel):
    total_sensors: int = Field(0, description="Número total de sensores ativos.")
    alerts: int = Field(0, description="Número de sensores em estado de alerta.")
    normal: int = Field(0, description="Número de sensores em estado normal.")
    engine_status: str = Field(..., description="Status de saúde da Engine (ONLINE, LAG, OFFLINE, ERROR).")

class BranchKPI(BaseModel):
    filial: str
    total_sensors: int
    sensors_in_alert: int
    percent_alert: float
    avg_temperature: float

class DashboardMetrics(BaseModel):
    timestamp: str = Field(..., description="Timestamp da última atualização das métricas.")
    query_latency_ms: str = Field(..., description="Latência da consulta SQL na TSQE.")
    global_kpis: GlobalKPI
    branch_kpis: List[BranchKPI] = Field(..., min_length=0) 
    error: Optional[str] = Field(None, description="Mensagem de erro em caso de falha na comunicação.")


# --- Funções de Conexão e Processamento ---

def fetch_and_process_metrics() -> Dict[str, Any]:
    
    query_sql = """
        SELECT 
            id, 
            timestamp, 
            TRY_CAST(JSON(data_payload)->>'temperature_celsius' AS DOUBLE) AS temp,
            JSON(data_payload)->>'status' AS status,
            JSON(data_payload)->>'store_id' AS store_id
        FROM real_time_stream_data;
    """
    
    payload = {
        "sql": query_sql,
        "format": "json"
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer VALID_TOKEN_123"
    }
    
    response = None
    current_time = datetime.now(timezone.utc).isoformat()
    
    default_error_return = lambda status_tag, latency_str, err_msg: {
        "timestamp": current_time,
        "query_latency_ms": latency_str,
        "global_kpis": {"total_sensors": 0, "alerts": 0, "normal": 0, "engine_status": status_tag},
        "branch_kpis": [],
        "error": err_msg
    }
    
    try:
        start_time = time.time()
        
        response = requests.post(TSQE_QUERY_URL, json=payload, headers=headers, timeout=MAX_REQUEST_TIMEOUT)
        response.raise_for_status()
        
        try:
            raw_data: List[Dict[str, Any]] = response.json()
        except json.JSONDecodeError:
            return default_error_return("ERROR", "JSON_ERR", "Resposta da Engine não é JSON válido.")
        
        latency = (time.time() - start_time) * 1000
        
        if not raw_data or (isinstance(raw_data, dict) and raw_data.get("message")):
            return default_error_return("ONLINE", f"{latency:.2f}", None)

        # --- Processamento dos Dados Brutos para KPIs ---
        alerts_count = 0
        normal_count = 0
        total_sensors = len(raw_data)
        branch_kpis = {} 
        
        for record in raw_data:
            try:
                branch_id = record.get('store_id', 'UNKNOWN_STORE')
                current_temp = float(record.get('temp') if record.get('temp') is not None else 0.0)
                current_status = record.get('status', 'UNKNOWN')
                
                if current_status == "ALERT": alerts_count += 1
                else: normal_count += 1
                    
                if branch_id not in branch_kpis:
                    branch_kpis[branch_id] = {'total': 0, 'alerts': 0, 'sum_temp': 0.0}
                
                branch_kpis[branch_id]['total'] += 1
                branch_kpis[branch_id]['sum_temp'] += current_temp
                if current_status == "ALERT": branch_kpis[branch_id]['alerts'] += 1
            
            except Exception as processing_error:
                print(f"AVISO CRÍTICO: Falha ao processar registro individual: {processing_error}")
                continue

        final_kpis_list = []
        for branch, data in branch_kpis.items():
            if data['total'] > 0:
                final_kpis_list.append(BranchKPI(
                    filial=branch,
                    total_sensors=data['total'],
                    sensors_in_alert=data['alerts'],
                    percent_alert=round((data['alerts'] / data['total']) * 100, 2),
                    avg_temperature=round(data['sum_temp'] / data['total'], 2)
                ).dict())
        final_kpis_list.sort(key=lambda k: k['filial'])

        engine_status = "ONLINE"
        if latency > 1000:
            engine_status = "LAG"
        elif latency > 3000:
            engine_status = "CRITICAL_LAG"

        global_kpis = GlobalKPI(
            total_sensors=total_sensors, alerts=alerts_count, normal=normal_count,
            engine_status=engine_status
        ).dict()
        
        return {
            "timestamp": current_time,
            "query_latency_ms": f"{latency:.2f}",
            "global_kpis": global_kpis,
            "branch_kpis": final_kpis_list,
            "error": None
        }

    except requests.exceptions.Timeout:
        return default_error_return("LAG", "TIMEOUT", f"Timeout ao conectar com a TSQE (mais de {MAX_REQUEST_TIMEOUT}s).")
    except requests.exceptions.ConnectionError:
        return default_error_return("OFFLINE", "CON_ERR", f"Falha de conexão com a TSQE em {TSQE_QUERY_URL}. A engine está rodando?")
    except requests.exceptions.HTTPError as http_err:
        status_code = response.status_code if response is not None else 'N/A'
        response_text = response.text if response is not None else 'N/A'
        
        if status_code == 401: error_msg = "Acesso negado (JWT). Verifique o token."
        elif status_code == 403: error_msg = "Query SQL não permitida pela Engine."
        else: error_msg = f"Erro {status_code} na Engine. Detalhe: {response_text[:150]}..."
            
        print(f"ERRO DE CONEXÃO/QUERY: {status_code}. Detalhe: {error_msg}")
        return default_error_return("ERROR", f"{status_code} Error", error_msg)
    except Exception as e:
        print(f"ERRO INESPERADO no Consumer: {e}")
        return default_error_return("ERROR", "CRITICAL", f"Erro interno do Consumer: {type(e).__name__} - {e}")


# --- Inicialização do FastAPI (Consumer) ---
app = FastAPI(
    title=f"TSQE Consumer Dashboard (V{DASHBOARD_VERSION})",
    description="Dashboard que consome o stream de dados da Engine via POST e serve a UI/UX aprimorada.",
    version=DASHBOARD_VERSION
)

# --- Rotas de Serviço ---

@app.get("/api/v1/metrics", response_model=DashboardMetrics, tags=["Data API"])
async def get_stream_metrics():
    return fetch_and_process_metrics()

@app.get("/", response_class=HTMLResponse, tags=["Web UI"])
async def serve_dashboard():
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <title>TSQE Stream Dashboard</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            :root {{
                --primary-color: #007bff;
                --alert-color: #dc3545;
                --warning-color: #ffc107;
                --success-color: #28a745;
                --bg-color: #f4f7fa;
                --card-bg: #ffffff;
                --text-color: #343a40;
                --shadow: 0 4px 12px rgba(0,0,0,0.08);
            }}
            body {{ 
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
                margin: 0; 
                background-color: var(--bg-color); 
                color: var(--text-color);
                line-height: 1.6;
            }}
            .container {{ 
                max-width: 1400px; 
                margin: auto; 
                padding: 20px; 
            }}
            header {{
                background-color: var(--primary-color);
                color: white;
                padding: 15px 20px;
                box-shadow: var(--shadow);
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 20px;
            }}
            header h1 {{ margin: 0; font-size: 1.8em; }}
            .status-badge {{ 
                padding: 5px 10px; 
                border-radius: 5px; 
                font-weight: bold; 
                color: white; 
            }}
            .status-online {{ background-color: var(--success-color); }}
            .status-offline {{ background-color: var(--alert-color); }}
            .status-lag {{ background-color: var(--warning-color); color: #333; }}
            .status-critical-lag {{ background-color: #ff8800; color: white; }}
            .status-error {{ background-color: #990000; }}

            .dashboard-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }}
            .kpi-card {{
                background: var(--card-bg);
                padding: 25px;
                border-radius: 10px;
                box-shadow: var(--shadow);
                display: flex;
                flex-direction: column;
                min-height: 100px;
                transition: transform 0.2s;
            }}
            .kpi-card:hover {{ transform: translateY(-3px); }}
            
            .kpi-title {{ font-size: 1em; color: #6c757d; margin-bottom: 5px; }}
            .kpi-value {{ font-size: 2.5em; font-weight: 700; }}
            .kpi-indicator {{ font-size: 1.5em; margin-right: 10px; }}

            .kpi-alerts {{ border-left: 5px solid var(--alert-color); }}
            .kpi-total {{ border-left: 5px solid var(--primary-color); }}
            .kpi-normal-count {{ border-left: 5px solid var(--success-color); }}

            table {{ 
                width: 100%; 
                border-collapse: separate; 
                border-spacing: 0; 
                background: var(--card-bg);
                border-radius: 10px;
                overflow: hidden;
                box-shadow: var(--shadow);
            }}
            th, td {{ 
                padding: 15px; 
                text-align: left; 
                border-bottom: 1px solid #e9ecef; 
            }}
            th {{ 
                background-color: #e9ecef; 
                color: var(--text-color); 
                font-weight: 600;
                text-transform: uppercase;
                font-size: 0.9em;
            }}
            tr:last-child td {{ border-bottom: none; }}
            
            .alert-row {{ background-color: #fff3f4; }}
            .alert-row td {{ color: var(--alert-color); }}
            
            footer {{
                text-align: center;
                padding: 10px;
                margin-top: 30px;
                font-size: 0.8em;
                color: #6c757d;
                border-top: 1px solid #e9ecef;
            }}
            .footer-info {{ display: inline-block; margin: 0 15px; }}
            
            .flex-row {{ display: flex; align-items: center; }}
            #error-message {{ color: var(--alert-color); margin-top: 15px; padding: 10px; border: 1px solid var(--alert-color); background: #fee; border-radius: 5px; font-weight: bold; display: none; }}
            
            @media (max-width: 768px) {{
                .container {{ padding: 10px; }}
                header {{ flex-direction: column; align-items: flex-start; }}
                .header-info {{ margin-top: 10px; }}
                th, td {{ padding: 10px; font-size: 0.9em; }}
            }}
        </style>
    </head>
    <body>
        <header>
            <h1>TSQE Stream Monitor</h1>
            <div class="header-info flex-row">
                Engine Status: <span id="engine-status-badge" class="status-badge status-offline">...</span>
                <span style="margin-left: 20px;">Latência de Consulta: <span id="latency">...</span></span>
            </div>
        </header>

        <div class="container">
            <div class="header-info" style="margin-top: 0; font-size: 0.9em; color: #6c757d;">
                <span>Última Atualização dos Dados (Local): <span id="last-update">...</span></span>
            </div>
            
            <div id="error-message"></div>

            <h2>Indicadores Globais de Sensores</h2>
            <div id="global-kpis-grid" class="dashboard-grid">
                <div class="kpi-card kpi-total"><span class="kpi-title">Carregando...</span></div>
            </div>
            
            <h2>Status Detalhado por Filial</h2>
            <table id="branch-table">
                <thead>
                    <tr>
                        <th>Filial</th>
                        <th>Total Sensores</th>
                        <th>Alertas (🔥)</th>
                        <th>% Alerta</th>
                        <th>Temp. Média (°C)</th>
                    </tr>
                </thead>
                <tbody>
                    <tr><td colspan="5" style="text-align: center; color: #666;">Aguardando dados...</td></tr>
                </tbody>
            </table>
        </div>
        
        <footer>
            <div class="footer-info">TSQE Dashboard V{DASHBOARD_VERSION}</div>
            <div class="footer-info">Consulta via POST em: {TSQE_QUERY_URL}</div>
        </footer>

        <script>
            const METRICS_URL = "/api/v1/metrics";
            const tableBody = document.getElementById('branch-table').getElementsByTagName('tbody')[0];
            const globalKpisGrid = document.getElementById('global-kpis-grid');
            const lastUpdateSpan = document.getElementById('last-update');
            const latencySpan = document.getElementById('latency');
            const engineStatusBadge = document.getElementById('engine-status-badge');
            const errorMessageDiv = document.getElementById('error-message');
            const UPDATE_INTERVAL_SECONDS = {UPDATE_INTERVAL_SECONDS};
            const REFRIGERATION_THRESHOLD = -15.0; 


            function handleFatalError(message) {{
                console.error("ERRO FATAL NA ENGINE:", message);
                
                errorMessageDiv.textContent = '🚨 ERRO: ' + message;
                errorMessageDiv.style.display = 'block';
                
                engineStatusBadge.textContent = 'ERROR';
                engineStatusBadge.className = 'status-badge status-error';
                
                // Limpa e exibe estado de erro nos cards
                globalKpisGrid.innerHTML = `
                    <div class="kpi-card kpi-total"><span class="kpi-title">Sensores</span><span class="kpi-value">---</span></div>
                    <div class="kpi-card kpi-alerts"><span class="kpi-title">Alertas</span><span class="kpi-value">---</span></div>
                    <div class="kpi-card kpi-normal-count"><span class="kpi-title">Normal</span><span class="kpi-value">---</span></div>
                `;
                tableBody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--alert-color);">Dados Indisponíveis.</td></tr>';
                lastUpdateSpan.textContent = new Date().toLocaleTimeString();
                latencySpan.textContent = '---';
            }}


            async function fetchData() {{
                try {{
                    errorMessageDiv.style.display = 'none';
                    
                    const response = await fetch(METRICS_URL);
                    
                    if (!response.ok) {{
                        throw new Error(`Consumer API HTTP Error: ${{response.status}}`);
                    }}
                    
                    const data = await response.json();
                    
                    if (data.error) {{
                         // Erro vindo do Python (fetch_and_process_metrics)
                         handleFatalError(data.error);
                         return;
                    }}
                    
                    updateDashboard(data);
                    
                }} catch (error) {{
                    // Erro de rede ou erro na comunicação inicial do Consumer
                    handleFatalError("Erro de comunicação com o Consumer local: " + error.message);
                }}
            }}

            function updateDashboard(data) {{
                // 1. Atualizar Header Info
                const engineStatus = data.global_kpis.engine_status;
                engineStatusBadge.textContent = engineStatus;
                engineStatusBadge.className = 'status-badge status-' + engineStatus.toLowerCase().replace('_', '-');

                // Garante que a data seja formatada para o local
                lastUpdateSpan.textContent = new Date().toLocaleTimeString();
                latencySpan.textContent = data.query_latency_ms;
                
                // 2. Atualizar KPIs Globais
                const global = data.global_kpis;
                globalKpisGrid.innerHTML = `
                    <div class="kpi-card kpi-total">
                        <span class="kpi-title">Total de Sensores</span>
                        <div class="flex-row">
                            <span class="kpi-indicator">📊</span>
                            <span class="kpi-value">${{global.total_sensors}}</span>
                        </div>
                    </div>
                    <div class="kpi-card kpi-alerts">
                        <span class="kpi-title">Sensores em ALERTA</span>
                        <div class="flex-row">
                            <span class="kpi-indicator" style="color: var(--alert-color);">🔥</span>
                            <span class="kpi-value">${{global.alerts}}</span>
                        </div>
                    </div>
                    <div class="kpi-card kpi-normal-count">
                        <span class="kpi-title">Sensores OK</span>
                        <div class="flex-row">
                            <span class="kpi-indicator" style="color: var(--success-color);">✅</span>
                            <span class="kpi-value">${{global.normal}}</span>
                        </div>
                    </div>
                `;

                // 3. Atualizar Tabela de Filiais
                tableBody.innerHTML = '';
                if (data.branch_kpis.length === 0) {{
                     tableBody.innerHTML = '<tr><td colspan="5" style="text-align: center; color: #666;">Nenhuma filial com dados ativos (tabela vazia).</td></tr>';
                     return;
                }}
                
                data.branch_kpis.forEach(kpi => {{
                    const row = tableBody.insertRow();
                    
                    let isCritical = (kpi.sensors_in_alert > 0) || (kpi.avg_temperature > REFRIGERATION_THRESHOLD);

                    if (isCritical) {{
                        row.className = 'alert-row';
                    }}
                    
                    row.insertCell().textContent = kpi.filial;
                    row.insertCell().textContent = kpi.total_sensors;
                    
                    const alertCell = row.insertCell();
                    alertCell.textContent = kpi.sensors_in_alert;
                    if (kpi.sensors_in_alert > 0) {{
                        alertCell.innerHTML += ' ⚠️';
                    }}

                    row.insertCell().textContent = kpi.percent_alert + "%";
                    
                    const tempCell = row.insertCell();
                    tempCell.textContent = kpi.avg_temperature.toFixed(2) + " °C"; 
                    
                    if (kpi.avg_temperature > REFRIGERATION_THRESHOLD) {{ 
                        tempCell.style.color = 'var(--alert-color)';
                        tempCell.style.fontWeight = 'bold';
                    }}
                }});
            }}

            // Inicia o loop de atualização
            fetchData(); 
            setInterval(fetchData, UPDATE_INTERVAL_SECONDS * 1000); 

        </script>
    </body>
    </html>
    """
    return html_content


# --- Execução do Consumer ---

if __name__ == "__main__":
    import uvicorn
    
    app_module_name = os.path.splitext(os.path.basename(__file__))[0]
    app_import_string = f"{app_module_name}:app"
    
    print(f"\n--- INICIANDO CONSUMER DASHBOARD V{DASHBOARD_VERSION} ---")
    print(f"O Dashboard estará em http://127.0.0.1:{CONSUMER_PORT}/")
    print("-------------------------------------------------------")
    
    uvicorn.run(app_import_string, host="0.0.0.0", port=CONSUMER_PORT, workers=1)