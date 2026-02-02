# 🚀 Table Stream Query Engine (TSQE) PoC: Arquitetura de Dados de Próxima Geração 

## Por Elias Andrade | Next-Gen System & Data Architect

[![LinkedIn Badge](https://img.shields.io/badge/LinkedIn-Elias%20Andrade-0077B5?style=for-the-badge&logo=linkedin&logoColor=white&labelColor=0077B5)](https://www.linkedin.com/in/itilmgf/)
[![GitHub Badge](https://img.shields.io/badge/GitHub-chaos4455-181717?style=for-the-badge&logo=github&logoColor=white&labelColor=181717)](https://github.com/chaos4455)
[![Python Version](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI Framework](https://img.shields.io/badge/Framework-FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![DuckDB Core](https://img.shields.io/badge/DB%20Engine-DuckDB%20(OLAP)-FFD700?style=for-the-badge&logo=data-ingestion&logoColor=333333&labelColor=B8860B)](https://duckdb.org/)
[![PyArrow Format](https://img.shields.io/badge/Format%20Interop-PyArrow%2FParquet-C29CF5?style=for-the-badge&logo=apache-arrow&logoColor=FFFFFF&labelColor=5A3EBE)](https://arrow.apache.org/)
[![Architecture Type](https://img.shields.io/badge/Architecture-Decoupled%20Microservices-5A3EBE?style=for-the-badge&logo=microservices&logoColor=white)](https://www.fastapi.tiangolo.com/)

<img width="1536" height="1024" alt="ChatGPT Image 20 de jan  de 2026, 11_12_57" src="https://github.com/user-attachments/assets/18126dbc-310d-4ebb-97fa-4a7a75334658" />


---

## I. 💡 Introdução Estratégica: O Paradigma *State-as-a-Table*

Esta Prova de Conceito (PoC) transcende a simples demonstração de código. Ela estabelece um **novo paradigma de arquitetura de dados**: o **Table Stream Query Engine (TSQE)**, focado em resolver o desafio de latência analítica em tempo real com máxima eficiência.

### O que é o TSQE e por que ele é Next-Gen?

Enquanto sistemas legados (como o Kafka) são otimizados para o *fluxo de eventos* (o que aconteceu), o TSQE é otimizado para o **estado da realidade** (qual é o status **agora**). Ele trata o fluxo contínuo de dados de alta velocidade (e.g., 400 sensores a cada 10s) como uma **tabela analítica materializada em memória** que está sujeita a **UPSERTs** (Update-or-Insert) ultrarrápidos.

O resultado é a capacidade de executar **consultas OLAP complexas (Analytical Queries)** sobre o *estado atual* do sistema, atingindo a meta de **latência analítica zero** – uma exigência crítica para sistemas de monitoramento industrial, financeiro e de varejo.

**Caso de Uso Central (PoC):** Monitoramento de *Freezers* em Supermercados. O sistema garante que qualquer analista possa consultar o status de Alerta, a Média de Temperatura e o Total de Sensores por Filial em **tempo real** usando apenas SQL via API.

<img width="1366" height="796" alt="screencapture-127-0-0-1-8080-2026-01-19-17_50_34" src="https://github.com/user-attachments/assets/c61d6bc3-0475-45eb-8173-5569e2e2e94f" />


## II. 🏛️ Arquitetura *Decoupled* e *Lean* em Microsserviços

A solução é um *monorepo* de três microsserviços Python, minimalistas e desacoplados, promovendo resiliência, manutenibilidade e escalabilidade horizontal.

| Camada | Componente | 📦 Tecnologia Principal | 🔑 Contrato API | Função Primária e Valor Estratégico |
| :--- | :--- | :--- | :--- | :--- |
| **Data Producer** | 💉 **Sensor Data Injector** | `Python`, `requests`, `Faker` | **POST /ingest** | Simula a fonte de dados (IoT/Edge) e executa o *Stream UPSERT* (Update or Insert) na Engine. |
| **Data Engine/Store** | ⚙️ **TSQE Engine Principal** | `FastAPI`, **DuckDB**, **PyArrow** | **POST /query** | O Motor central. Recebe o stream, mantém o estado em *In-Memory Table* e executa consultas SQL em modo OLAP. |
| **Data Consumer** | 📊 **Dashboard Metrics Collector** | `FastAPI`, HTML/JS, `Pydantic` | **GET /metrics** | Orquestrador. Consulta a Engine, realiza a **Analytics Edge** (cálculo de KPIs em Python) e serve o painel Web UX. |

### 🌐 Fluxo de Comunicação e Desacoplamento

1.  **Ingestão (Stream):** O Injector envia o Lote de Dados (JSON) via **HTTP POST /ingest** (Porta 8888). O DuckDB processa o UPSERT, atualizando a tabela `real_time_stream_data`.
2.  **Consulta (Insight):** O Dashboard envia a Query SQL (ex: Agregação de Temperatura) via **HTTP POST /query** (Porta 8888). A Engine processa e retorna o resultado em milissegundos.

Este modelo garante que a Engine (o coração da performance) não seja afetada pelas regras de negócio ou pela renderização da UI/UX.

---

## III. 🧠 O Coração da Engine: DuckDB e PyArrow — Aceleradores de Performance

A escolha da Stack é o ponto-chave que posiciona esta arquitetura como **Next-Gen**.

### 1. 🥇 DuckDB: A Força do OLAP In-Process

*   **Processamento Colunar Vetorizado:** Ao contrário de bancos de dados OLTP linha a linha, o DuckDB utiliza vetorização nativa e armazenamento colunar em memória. Isso é crucial, pois as consultas do Dashboard são analíticas (`AVG`, `GROUP BY`, `COUNT`) – o ambiente onde o DuckDB brilha com performance superior.
*   **Capacidade de JSON e Estrutura:** O uso de `TRY_CAST(JSON(data_payload)->>'...')` no SQL da Engine demonstra a capacidade de **consultar dados semi-estruturados** (JSON) como se fossem colunas, tudo em tempo real, sem a necessidade de um ETL complexo para normalização.
*   **Transações de Estado (`UPSERT`):** O `INSERT INTO ... ON CONFLICT DO UPDATE` é a fundação da arquitetura **State-as-a-Table**. Garante que cada nova leitura do sensor substitua o estado anterior, mantendo a tabela sempre com o *Last Known State* de toda a frota de sensores.

### 2. 🟣 PyArrow: O Formato Zênite para Interoperabilidade

*   **O Formato Universal:** PyArrow implementa o Apache Arrow, o padrão *de facto* para transferência de dados colunares em memória.
*   **Zero-Copy Serialization:** Quando o DuckDB executa a Query, ele retorna um `Arrow Table`. Esta é a representação mais eficiente de dados estruturados.
*   **Desafio Superado (JSON Serialization):** A função `format_output_data` na Engine utiliza PyArrow, mas, crucialmente, implementa uma função `json_converter` customizada para forçar a serialização correta de objetos complexos (como `datetime` com timezone) que vêm do PyArrow, garantindo que o JSON final seja *perfeito* para o Consumer, sem *bottlenecks* de I/O. Isso demonstra proficiência em lidar com a interoperabilidade em nível de formato binário.

---

## IV. 📊 Lógica de Processamento: O Poder do *Analytics Edge*

A Engine entrega dados brutos (`Arrow Table`), mas o microsserviço Consumer faz a agregação final – esta é a filosofia *Analytics Edge*.

### Fluxo de Geração de KPIs:

1.  **A Engine responde:** Retorna todos os 400 registros atuais de sensores em milissegundos.
2.  **Lógica do Consumer (`fetch_and_process_metrics`):** O código Python do Dashboard itera sobre os dados:
    *   **Agregação de Negócio:** Calcula KPIs específicos (Ex: Média de Temperatura por `store_id`, % de Alerta).
    *   **Healthcheck Inteligente:** A Engine retorna o status de latência. O Consumer aprimora isso, definindo o status de saúde (`ONLINE`, `LAG` > 1000ms, `CRITICAL_LAG` > 3000ms) para refletir a experiência do usuário, não apenas a saúde da API.
    *   **Regra de Alerta UI/UX:** A lógica JavaScript no frontend aplica a regra `(kpi.avg_temperature > REFRIGERATION_THRESHOLD)` para destacar linhas de filiais críticas, adicionando uma camada de visualização de negócio que é *desacoplada* da Engine.

Esta arquitetura demonstra a capacidade de **dividir a carga analítica** (Heavy SQL na Engine, Light Business Logic no Consumer), otimizando a latência de ponta a ponta.

---

## V. 🎯 Posicionamento Estratégico: O Arquiteto como Otimizador de Valor

Esta PoC é um manifesto prático contra a **Fadiga Operacional** e o **Overhead de Custo** de soluções genéricas.

### Por que Customização *Lean* Vence o Excesso de Ferramentas (COTS)?

| Cenário Genérico (Kafka/Databricks/DB Relacional) | 🛠️ Arquitetura TSQE Customizada (Elias Andrade) |
| :--- | :--- |
| **Fadiga Operacional:** Exige gerenciamento de *clusters* complexos, tópicos, *brokers*, *schemas*, *connectors* e pipelines ETL. | **Eficiência Operacional:** Três serviços Python leves. A arquitetura é a própria solução, resultando em TCO (Custo Total de Propriedade) extremamente baixo. |
| **Latência Inconsistente:** Consultas OLAP em *Data Lakes* ou DBs transacionais levam segundos ou dezenas de segundos. | **Latência Ultra-Baixa:** O uso do DuckDB *in-memory* garante que a latência de **query** seja a variável de controle, tipicamente **sub-100ms**. |
| **Acoplamento Inflexível:** A solução é refém da sintaxe SQL, do formato de dados ou da tecnologia específica do Data Lake. | **Máximo Controle:** Componentes são plugáveis. Se a Engine precisar de um banco de dados de tempo (ex: TimescaleDB), apenas a camada de E/S na Engine é trocada. |
| **Excesso de Capacidade:** A maior parte da infraestrutura de um *Data Lake* é subutilizada para este caso de uso simples e de alto valor. | **Otimizado para a Missão:** Arquitetura *just-in-time* e *fit-for-purpose*, entregando o resultado de negócio com a mínima infraestrutura possível. |

**Meu Perfil:** Minha experiência como **Next-Gen System & Data Architect** reside em fazer escolhas de tecnologia que maximizem o valor de negócio através da eficiência técnica e da redução de complexidade.

---

## VI. 🛠️ Stack Tecnológica (Resumo e Justificativa)

| Categoria | Tecnologia | Justificativa |
| :--- | :--- | :--- |
| **API & Service Layer** | 🐍 **Python 3.11+, FastAPI, Uvicorn** | Alta velocidade, assíncrono e padrão da indústria para microsserviços modernos. |
| **Data Processing Core**| 🥇 **DuckDB (in-memory)** | A escolha estratégica para performance OLAP e vetorização de dados. Acelerador analítico. |
| **Data Interoperability**| 🟣 **PyArrow, Parquet, JSON** | Garante que o gargalo não seja a serialização de dados, mas sim a execução da query. |
| **Stream Transaction** | `requests`, `INSERT ON CONFLICT` | Implementação do *Stream UPSERT* para manter o estado da realidade atualizado. |
| **UI/UX Layer** | **HTML5/JS (Vanilla)** | Leve, auto-refreshing, prova de conceito de consumo em tempo real com lógica *Edge*. |

---

## VII. ⚙️ Próximos Passos & Setup Rápido

Para iniciar a replicação deste ambiente de dados de alta performance:

1.  **Instalação:** Use o `requirements.txt` fornecido: `pip install -r requirements.txt`
2.  **Execução (3 Terminais):**
    *   **Engine (TSQE):** Inicia o motor de processamento (Porta 8888).
    *   **Dashboard (Consumer):** Inicia a API de métricas e a UI (Porta 8080).
    *   **Injector (Producer):** Inicia o fluxo de dados em **UPSERT** a cada 10 segundos.
3.  **Acesso:** Navegue até `http://127.0.0.1:8080/` para ver as métricas atualizarem dinamicamente.

---

## 👨‍💻 Contato: Elias Andrade

Construção de arquiteturas de dados resilientes, customizadas e de alto impacto é a minha especialidade.

**Elias Andrade**
*   **Título:** Next-Gen System & Data Architect
*   **GitHub:** `chaos4455`
*   **LinkedIn:** [linkedin.com/in/itilmgf](https://www.linkedin.com/in/itilmgf/)
