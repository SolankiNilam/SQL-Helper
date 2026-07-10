"""
Streamlit UI for the SQL Query Helper Agent (Gemini + MySQL)
--------------------------------------------------------------
Install:
    pip install streamlit google-generativeai mysql-connector-python

Run:
    streamlit run streamlit_app.py

Requires sql_agent.py in the same directory, and the same env vars:
    GEMINI_API_KEY, DB_HOST, DB_USER, DB_PASSWORD, DB_NAME
"""

import json
import streamlit as st
import google.generativeai as genai

from sql_agent import (
    get_schema_summary,
    build_system_prompt,
    tools,
    TOOL_IMPL,
    genai as agent_genai,  
)

st.set_page_config(page_title="SQL Query Helper", page_icon="🗄️", layout="wide")
st.title("🗄️ SQL Query Helper Agent")
st.caption("Ask in plain English. The agent writes, runs, debugs, and optimizes MySQL queries.")


@st.cache_resource(show_spinner="Reading database schema...")
def load_schema():
    return get_schema_summary()

if "chat_session" not in st.session_state:
    schema = load_schema()
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=build_system_prompt(schema),
        tools=tools,
    )
    st.session_state.chat_session = model.start_chat()
    st.session_state.display_history = []  

with st.sidebar:
    st.subheader("Schema")
    st.code(load_schema(), language="sql")
    if st.button("Reset conversation"):
        del st.session_state.chat_session
        st.session_state.display_history = []
        st.rerun()


for role, content in st.session_state.display_history:
    with st.chat_message(role):
        if isinstance(content, dict) and "columns" in content:
            st.dataframe(content["rows"], column_config=None)
        else:
            st.markdown(content)


user_input = st.chat_input("e.g. show me the top 5 customers by total order value")

if user_input:
    st.session_state.display_history.append(("user", user_input))
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        status = st.empty()
        status.markdown("_thinking..._")

        convo = st.session_state.chat_session
        response = convo.send_message(user_input)

       
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
                sql_preview = fc.args.get("sql", "")
                status.markdown(f"_running `{fc.name}`..._\n```sql\n{sql_preview}\n```")

                impl = TOOL_IMPL[fc.name]
                result = impl(**{k: v for k, v in fc.args.items()})

                if "rows" in result:
                    st.session_state.display_history.append(("assistant", result))
                    st.dataframe(result["rows"])
                elif "error" in result:
                    st.warning(f"Query error: {result['error']}")

                tool_outputs.append(
                    agent_genai.protos.Part(
                        function_response=agent_genai.protos.FunctionResponse(
                            name=fc.name, response={"result": json.dumps(result, default=str)}
                        )
                    )
                )
            response = convo.send_message(tool_outputs)

        status.empty()
        final_text = response.text
        st.markdown(final_text)
        st.session_state.display_history.append(("assistant", final_text))
