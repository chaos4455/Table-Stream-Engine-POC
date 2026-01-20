# 🚀 Table Stream Query Engine (TSQE) PoC: Arquitetura de Dados de Próxima Geração

## Por Elias Andrade | Next-Gen System & Data Architect

[![LinkedIn](https://img.shields.io/badge/LinkedIn-Elias%20Andrade-0077B5?style=for-the-badge&logo=linkedin)](https://www.linkedin.com/in/itilmgf/)
[![GitHub](https://img.shields.io/badge/GitHub-chaos4455-181717?style=for-the-badge&logo=github)](https://github.com/chaos4455)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/Framework-FastAPI-009688?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)
[![DuckDB](https://img.shields.io/badge/DB%20Engine-DuckDB-075e81?style=for-the-badge&logo=data-ingestion)](https://duckdb.org/)
[![PyArrow](https://img.shields.io/badge/Format-PyArrow%2FParquet-e36611?style=for-the-badge&logo=apache-arrow)](https://arrow.apache.org/)

<img width="1536" height="1024" alt="ChatGPT Image 20 de jan  de 2026, 11_12_57" src="https://github.com/user-attachments/assets/1bef46b4-bfe4-4204-bdf5-4c608753354d" />


---

## I. 💡 Introdução Estratégica: O Conceito de Table Stream Query Engine

Esta Prova de Conceito (PoC) demonstra a construção de uma arquitetura de dados *Lean* e desacoplada, utilizando microsserviços customizados para resolver o desafio clássico de transformar **streams de dados de alta velocidade** em **insights em tempo real**, com latência ultrabaixa, sem a complexidade operacional de Data Lakes massivos ou clusters Kafka genéricos para casos de uso específicos.

### O que é o TSQE?

O **Table Stream Query Engine (TSQE)** é um motor de processamento híbrido que trata dados de streaming como uma tabela permanentemente materializada e instantaneamente consultável. Em vez de simplesmente enfileirar eventos (como o Kafka), ou armazenar em disco (como bancos de dados tradicionais), o TSQE **mantém o estado atual da realidade** em memória, permitindo consultas OLAP (Online Analytical Processing) complexas sobre o estado *atualizado* do sistema com latência de milissegundos.

**Caso de Uso Prático (Esta PoC):** Monitoramento de sensores de temperatura em supermercados. A cada 10 segundos, o estado de centenas de freezers é atualizado (UPSERT), permitindo que um Dashboard Analítico consulte o status de toda a rede usando SQL puro, em tempo real.

---

## II. 🏛️ Arquitetura de Microsserviços Desacoplados (Decoupled Architecture)

A solução é dividida em três microsserviços independentes, comunicando-se exclusivamente via APIs e formatos de dados padronizados (JSON, PyArrow). Este modelo garante escalabilidade, resiliência e a capacidade de trocar componentes sem afetar o sistema principal (Engine).

| Camada | Componente | Tecnologia Principal | Função Primária |
| :--- | :--- | :--- | :--- |
| **Data Producer** | 💉 **Data Injector (Simulador)** | Python, `requests`, `faker` | Simula um grande volume de sensores (Upserts). |
| **Data Engine/Store** | ⚙️ **TSQE (Engine Principal)** | FastAPI, DuckDB, PyArrow | Ingestão multi-formato, Armazenamento in-memory e Execução de Query SQL. |
| **Data Consumer** | 📊 **Dashboard & Metrics Collector** | FastAPI, HTML/JS, `requests` | Consulta a Engine, calcula KPIs em tempo real e renderiza a visualização Web. |

### Comunicação Assíncrona e Sincronizada

1. **Injector ➡️ TSQE:** Usa chamadas **POST `/ingest`** para realizar `UPSERTs` (Insert/Update) de forma transacional no estado da tabela em tempo real.
2. **Dashboard ➡️ TSQE:** Usa chamadas **POST `/query`** enviando consultas SQL complexas. A Engine retorna o resultado em um formato otimizado (JSON serializado por PyArrow) em menos de 100ms.

---

## III. 🧠 O Coração da Engine: DuckDB e PyArrow

A performance e o poder analítico do TSQE residem na escolha de ferramentas de próxima geração:

### 1. DuckDB: O Swiss Army Knife do OLAP

DuckDB é um **banco de dados analítico in-process** que se integra nativamente ao Python. Suas principais vantagens nesta arquitetura são:

*   **OLAP Power:** Permite executar o SQL analítico complexo (`GROUP BY`, `TRY_CAST`, `JSON_EXTRACT`) diretamente sobre o stream de dados em memória, algo impraticável em bancos de dados operacionais (OLTP).
*   **Performance In-Memory:** Utiliza o modelo de processamento vetorial (columnar) para consultas extremamente rápidas, essenciais para o requisito de baixa latência do Dashboard.
*   **Transações de Stream (`UPSERT`):** A lógica de ingestão utiliza comandos `INSERT... ON CONFLICT DO UPDATE...` para garantir que o estado do sensor seja sempre o mais recente, tratando o *stream* como uma tabela de fatos atualizável.

### 2. PyArrow: A Linguagem Universal de Dados

O Apache Arrow (implementado em Python via PyArrow) é fundamental para a interoperabilidade e eficiência:

*   **Ingestão Multi-Formato:** A Engine aceita dados via JSON, YAML ou até mesmo o formato Parquet (baseado em Arrow), demonstrando flexibilidade de ingestão.
*   **Performance na Query:** O DuckDB retorna os resultados no formato `Arrow Table`. Isso permite que a Engine converta os dados para JSON de saída de forma altamente eficiente, garantindo que a serialização não se torne o gargalo de latência. O uso da `json_converter` customizada na Engine resolve o desafio comum de serializar tipos de dados (como `datetime`) do PyArrow para JSON padrão.

---

## IV. 📊 Lógica de Processamento no Dashboard (Consumer Side Analytics)

O serviço **Dashboard Metrics Collector** atua como um microsserviço de *Analytics Edge*, onde a lógica de negócio mais leve e específica é executada, mantendo a Engine principal focada apenas na entrega de dados brutos e rápidos.

### Fluxo de Geração de KPIs:

1.  **Consulta SQL Eficiente:** O Consumer envia um `SELECT *` simples para obter o estado atual de *todos* os sensores na `real_time_stream_data`.
2.  **Processamento Python:** Uma vez que os dados brutos chegam como uma lista de dicionários, o Python (FastAPI) assume a carga analítica:
    *   **KPIs Globais:** Contagem total, contagem de alertas, e status de saúde da própria Engine (baseado na latência de consulta).
    *   **KPIs por Entidade (Filial/Branch):** Agregação e cálculo de métricas como:
        *   `Total de Sensores por Filial`
        *   `Média de Temperatura` (`avg_temperature`)
        *   `Percentual de Sensores em Alerta` (`percent_alert`)
3.  **Visualização:** O Consumer serve uma interface HTML/CSS/JS (altamente otimizada para performance) que chama sua própria API a cada 10 segundos, atualizando dinamicamente os cartões KPI e a tabela detalhada das filiais.

Esta separação (SQL rápido na Engine + Agregação customizada no Consumer) garante que o sistema seja **altamente customizável** e que o Dashboard possa facilmente adaptar suas métricas sem exigir alterações complexas na Engine.

---

## V. 🎯 Posicionamento Estratégico: Customização vs. Ferramentas COTS

Em meu papel como **Next-Gen System & Data Architect**, defendo a arquitetura *Lean* para desafios de dados específicos, conforme demonstrado por esta PoC:

### Por que Microsserviços Customizados Superam Ferramentas de Prateleira?

| Ferramenta de Prateleira (Ex: Kafka, Data Lake, DB Relacional) | Arquitetura TSQE Customizada (FastAPI + DuckDB) |
| :--- | :--- |
| **Overhead Operacional:** Exige clusters complexos (Kafka), ETL pipelines ou infraestrutura de armazenamento massiva. | **Lean Architecture:** Infraestrutura mínima (três aplicações Python leves). Custos operacionais e de manutenção baixíssimos. |
| **Latência Variável:** Consulta analítica em Data Lakes pode levar segundos; Kafka é ótimo para eventos, ruim para o estado atual agregado. | **Latência Determinística:** Consultas analíticas em memória (DuckDB) garantem performance de **sub-100ms** para relatórios em tempo real. |
| **Acoplamento:** Muitas vezes, o Consumer fica acoplado ao formato do Tópico (Kafka) ou do Schema (DB). | **Decoupled Architecture:** A Engine expõe um contrato de Query API (`/query`). Fontes e Consumidores podem ser trocados livremente, garantindo flexibilidade. |
| **Generalista:** Ferramentas são projetadas para o uso mais amplo, resultando em funcionalidades não utilizadas. | **Otimizado para a Missão:** Cada componente é especificamente otimizado para o caso de uso (Ingestão de Upsert e Query Analítica). |

Esta PoC é uma evidência prática da minha capacidade de projetar **soluções de dados robustas, customizáveis e sob controle total**, que entregam valor de negócio com a máxima eficiência técnica.

---

## VI. 🛠️ Stack Tecnológica (Resumo)

| Categoria | Tecnologia | Justificativa |
| :--- | :--- | :--- |
| **API & Service Layer** | Python 3.11+, FastAPI, Uvicorn | Framework moderno, assíncrono e de alta performance para construir APIs de microsserviços. |
| **Data Processing Core**| DuckDB (in-memory) | Banco de dados analítico in-process para consultas rápidas e manipulação eficiente de dados vetoriais. |
| **Data Interoperability**| PyArrow, Parquet, JSON | Padronização do formato de dados para transferência de alta velocidade entre serviços Python. |
| **Simulação/Testing** | `Faker`, `requests` | Geração de dados simulados realistas para provar a capacidade de ingestão contínua. |
| **Web UI** | HTML5, CSS3, Vanilla JS | Interface leve e auto-refreshing para demonstrar o consumo de dados em tempo real. |

---

## VII. ⚙️ Como Executar a PoC (Setup Simplificado)

Para replicar esta arquitetura:

1.  Clone o repositório.
2.  Instale as dependências: `pip install fastapi uvicorn duckdb pyarrow requests pydantic faker starlette pyyaml`
3.  Inicie os três microsserviços em terminais separados:
    *   **Engine (Porta 8888):** (Executar o arquivo Server Engine)
    *   **Dashboard (Porta 8080):** (Executar o arquivo Consumer Dashboard)
    *   **Injector:** (Executar o arquivo Data Injector)
4.  Acesse o Dashboard em `http://127.0.0.1:8080/` e observe as métricas globais e por filial atualizando a cada 10 segundos, provando a baixa latência da Engine.

---

## 👨‍💻 Contato

Este projeto é um exemplo de minhas habilidades em projetar e implementar arquiteturas de dados de ponta.

**Elias Andrade**
*   **Título:** Next-Gen System & Data Architect
*   **GitHub:** `chaos4455`
*   **LinkedIn:** [linkedin.com/in/itilmgf](https://www.linkedin.com/in/itilmgf/)
