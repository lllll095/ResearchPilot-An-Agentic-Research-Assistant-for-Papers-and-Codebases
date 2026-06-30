# ResearchPilot Visual Demo
import streamlit as st
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

st.set_page_config(page_title="ResearchPilot", page_icon="U+1F9EA", layout="wide")
st.title("ResearchPilot Demo")

tab_chat, tab_paper, tab_about = st.tabs(["Chat", "Paper", "About"])

with tab_chat:
    st.subheader("Multi-Agent Chat")
    if "messages" not in st.session_state:
        st.session_state.messages = []
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
    if prompt := st.chat_input("Ask the multi-agent..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            try:
                from research_pilot.cli import build_multiagent_graph_workflow_runner
                runner = build_multiagent_graph_workflow_runner(verbose=False)
                state = runner.answer(user_request=prompt, session=None)
                st.markdown(state.final_answer or "")
                st.session_state.messages.append({"role": "assistant", "content": state.final_answer or ""})
            except Exception as e:
                st.error(f"Error: {e}")

with tab_paper:
    st.subheader("Paper Research")
    q = st.text_input("Question")
    if st.button("Research", type="primary") and q:
        with st.spinner("Working..."):
            from research_pilot.cli import build_paper_workflow_runner
            runner = build_paper_workflow_runner(verbose=False)
            state = runner.paper_research(question=q)
            st.markdown(state.final_answer or "")

with tab_about:
    st.markdown("### ResearchPilot 0.1.0")
    st.markdown("Multi-agent research assistant with paper RAG.")
    st.markdown("Run: streamlit run demo_app.py")

