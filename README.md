
Readme · MD
# SQL Helper Agent
 
A natural-language SQL assistant for MySQL, powered by the Gemini API. Ask questions in plain English — it writes, runs, debugs, and optimizes SQL queries against your own database, with a chat-based Streamlit UI.
 
## Features
 
- **Natural language → SQL** — describe what you want, get a working query
- **Query debugging** — feeds MySQL errors back to the model so it can self-correct
- **Query optimization** — uses `EXPLAIN` to spot full table scans and suggest indexes
- **Schema-aware** — reads your actual table/column names from `INFORMATION_SCHEMA`, so it doesn't hallucinate columns
- **Read-only by default** — blocks `INSERT` / `UPDATE` / `DELETE` / `DROP` / `ALTER` / `TRUNCATE` unless explicitly enabled
- **Chat UI with memory** — multi-turn conversation (e.g. "now filter that to last month") via Streamlit
## Architecture
 
```
User question (Streamlit chat)
        │
        ▼
Gemini model (gemini-2.5-flash) + system prompt containing live DB schema
        │
        ├─► run_query(sql)      → executes SELECT against MySQL, returns rows
        └─► explain_query(sql)  → runs EXPLAIN, returns execution plan
        │
        ▼
Result fed back to Gemini → formats final answer, shown in chat
```
 
| File | Purpose |
|---|---|
| `sql_agent.py` | Core agent logic: DB connection, schema introspection, query validation/execution, Gemini function-calling loop |
| `streamlit_app.py` | Chat UI wrapping the agent, with conversation memory and live result tables |
| `.env.example` | Template for required environment variables |
 
## Prerequisites
 
- Python 3.9+
- A running MySQL server you have credentials for
- A Gemini API key ([get one here](https://aistudio.google.com/apikey))
## Setup
 
1. **Clone/download this project** and open a terminal in its folder.
2. **Create and activate a virtual environment**
```bash
   python -m venv venv
 
   # macOS/Linux
   source venv/bin/activate
   # Windows (PowerShell)
   venv\Scripts\Activate.ps1
```
 
3. **Install dependencies**
```bash
   pip install streamlit google-generativeai mysql-connector-python python-dotenv sqlparse
```
 
4. **Configure environment variables**
```bash
   cp .env.example .env      # macOS/Linux
   copy .env.example .env    # Windows
```
   Edit `.env` with your real values:
```
   GEMINI_API_KEY=your-gemini-api-key
   DB_HOST=localhost
   DB_USER=your-mysql-user
   DB_PASSWORD=your-mysql-password
   DB_NAME=your-database-name
```
 
 
5. **Run the app**
```bash
   streamlit run streamlit_app.py
```
   Opens automatically at `http://localhost:8501`.
 

## Configuration
 
| Setting | Location | Default | Notes |
|---|---|---|---|
| `ALLOW_WRITES` | `sql_agent.py` | `False` | Set `True` to allow INSERT/UPDATE/DELETE (use with caution) |
| `MAX_ROWS_RETURNED` | `sql_agent.py` | `50` | Caps rows returned to the model per query, to control context size |
| Model | `sql_agent.py`, `streamlit_app.py` | `gemini-2.5-flash` | Swap to `gemini-2.5-flash-lite` for higher free-tier limits, or a paid Pro model for stronger reasoning |
 
## Safety notes
 
- The agent runs in **read-only mode by default**. Even if `ALLOW_WRITES` is left `False`, connect using a MySQL user that only has `SELECT` privileges as a second layer of protection — don't rely on the code check alone.
- The model is instructed never to invent table/column names, but always review generated SQL before trusting results in a production context.
