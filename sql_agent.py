"""
SQL Query Helper Agent — Gemini API + MySQL
--------------------------------------------
Capabilities:
  - Natural language -> SQL
  - Debug broken queries (feeds MySQL errors back to the model)
  - Optimize slow queries (via EXPLAIN)
  - Schema-aware (reads real table/column names from your DB)
  - Read-only by default (blocks writes/DDL unless ALLOW_WRITES=True)

Install:
    pip install google-generativeai mysql-connector-python sqlparse python-dotenv

Create a .env file in the same folder with:
    GEMINI_API_KEY=your-gemini-api-key
    DB_HOST=localhost
    DB_USER=your-mysql-user
    DB_PASSWORD=your-mysql-password
    DB_NAME=your-database-name
"""

import os
import json
import re
import mysql.connector
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()  


ALLOW_WRITES = False  
MAX_ROWS_RETURNED = 50 

genai.configure(api_key=os.environ["GEMINI_API_KEY"])

DB_CONFIG = {
    "host": os.environ["DB_HOST"],
    "user": os.environ["DB_USER"],
    "password": os.environ["DB_PASSWORD"],
    "database": os.environ["DB_NAME"],
}

WRITE_KEYWORDS = re.compile(
    r"^\s*(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|REPLACE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)


def get_connection():
    return mysql.connector.connect(**DB_CONFIG)


def get_schema_summary() -> str:
    """Introspect MySQL and return a compact schema description."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_KEY
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = %s
        ORDER BY TABLE_NAME, ORDINAL_POSITION
        """,
        (DB_CONFIG["database"],),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    tables = {}
    for table, col, dtype, nullable, key in rows:
        tables.setdefault(table, []).append(f"{col} {dtype}{' PK' if key == 'PRI' else ''}")

    lines = []
    for table, cols in tables.items():
        lines.append(f"TABLE {table}(\n  " + ",\n  ".join(cols) + "\n)")
    return "\n\n".join(lines)


def validate_query(sql: str) -> str | None:
    """Return an error string if the query is disallowed, else None."""
    if not ALLOW_WRITES and WRITE_KEYWORDS.match(sql.strip()):
        return "Blocked: this agent is read-only. Only SELECT/EXPLAIN/SHOW queries are permitted."
    return None


def run_query(sql: str) -> dict:
    err = validate_query(sql)
    if err:
        return {"error": err}
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchmany(MAX_ROWS_RETURNED)
        cur.close()
        conn.close()
        return {"columns": cols, "rows": rows, "row_count_returned": len(rows)}
    except mysql.connector.Error as e:
        return {"error": str(e)}


def explain_query(sql: str) -> dict:
    return run_query(f"EXPLAIN {sql}")




tools = [
    {
        "function_declarations": [
            {
                "name": "run_query",
                "description": "Execute a SQL query against the MySQL database and return rows.",
                "parameters": {
                    "type": "object",
                    "properties": {"sql": {"type": "string", "description": "The SQL query to run."}},
                    "required": ["sql"],
                },
            },
            {
                "name": "explain_query",
                "description": "Run EXPLAIN on a SQL query to inspect its execution plan (use for optimization).",
                "parameters": {
                    "type": "object",
                    "properties": {"sql": {"type": "string", "description": "The SQL query to explain."}},
                    "required": ["sql"],
                },
            },
        ]
    }
]

TOOL_IMPL = {"run_query": run_query, "explain_query": explain_query}



def build_system_prompt(schema: str) -> str:
    return f"""You are a MySQL query assistant. You can write, debug, and optimize SQL queries.

Database schema:
{schema}

Rules:
- Only write MySQL-compatible SQL.
- Never invent table or column names that aren't in the schema above.
- Prefer to call run_query to test a query before presenting it as final, when practical.
- If a query is slow or you're asked to optimize it, use explain_query and look for full table scans (type=ALL) or missing index usage, then suggest concrete fixes (e.g., "add an index on orders(customer_id)").
- If run_query returns an error, read the error message and fix the query, then retry.
- If ALLOW_WRITES is False and the user asks for an INSERT/UPDATE/DELETE, explain that you're running in read-only mode and show them the query without executing it.
- Keep explanations concise. Show the final SQL clearly.
"""


def chat(user_message: str, schema_cache: str):
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=build_system_prompt(schema_cache),
        tools=tools,
    )
    convo = model.start_chat()
    response = convo.send_message(user_message)

  
    while True:
        function_calls = [
            part.function_call
            for part in response.candidates[0].content.parts
            if part.function_call
        ]
        if not function_calls:
            break

        tool_outputs = []
        for fc in function_calls:
            impl = TOOL_IMPL[fc.name]
            result = impl(**{k: v for k, v in fc.args.items()})
            tool_outputs.append(
                genai.protos.Part(
                    function_response=genai.protos.FunctionResponse(
                        name=fc.name, response={"result": json.dumps(result, default=str)}
                    )
                )
            )
        response = convo.send_message(tool_outputs)

    return response.text


if __name__ == "__main__":
    print("Loading schema...")
    schema = get_schema_summary()
    print("Ready. Ask a question (Ctrl+C to exit).\n")

    while True:
        try:
            q = input("> ")
        except KeyboardInterrupt:
            break
        answer = chat(q, schema)
        print("\n" + answer + "\n")
