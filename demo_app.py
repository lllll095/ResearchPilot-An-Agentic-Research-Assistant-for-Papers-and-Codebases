"""ResearchPilot Visual Demo — Streamlit UI"""
import streamlit as st
import sys
from pathlib import Path
import time

HERE = Path(__file__).resolve().parent
SRC = HERE / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

st.set_page_config(page_title="ResearchPilot", page_icon="\U0001f9ea", layout="wide")
st.title("\U0001f9ea ResearchPilot Demo")

# ---- helpers ----
def show_step_trace(state):
    """Display step-by-step trace from AgentState."""
    steps = getattr(state, "steps", None) or []
    if not steps:
        st.caption("No execution trace available.")
        return
    for step in steps:
        action = step.action
        obs = step.observation
        tool = action.tool_name or "—"
        success = obs.success if obs else None
        icon = "\u2705" if success else "\u274c" if success is False else "\u23f3"
        with st.expander(f"Step {step.step_id}: {icon} {tool}", expanded=False):
            if action.tool_input:
                st.code(str(action.tool_input)[:500])
            if obs and obs.content:
                st.markdown(obs.content[:800])
            if obs and obs.error:
                st.error(obs.error)

def show_graph_mermaid(state):
    mermaid = (state.metadata or {}).get("graph_mermaid", "")
    if mermaid:
        with st.expander("\U0001f4ca Graph Path", expanded=False):
            st.code(mermaid)

def show_multiagent_trace(state):
    """Show multi-agent specific metadata."""
    meta = state.metadata or {}
    planner = meta.get("planner_output", {})
    if isinstance(planner, dict) and planner.get("content"):
        with st.expander("\U0001f9e9 Planner Decision", expanded=False):
            st.markdown(planner.get("content", "")[:600])
    show_step_trace(state)
    show_graph_mermaid(state)

# ---- tabs ----
tab_chat, tab_paper, tab_about = st.tabs(["\U0001f4ac Chat", "\U0001f4d6 Paper Research", "\u2139\ufe0f About"])

# ===================== CHAT TAB =====================
with tab_chat:
    st.subheader("\U0001f4ac Multi-Agent Chat")
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []
    for msg in st.session_state.chat_messages:
        if isinstance(msg, dict):
            with st.chat_message(msg.get("role", "assistant")):
                st.markdown(msg.get("content", ""))
                if msg.get("trace"):
                    show_multiagent_trace(msg["trace"])

    if prompt := st.chat_input("Ask the multi-agent..."):
        st.session_state.chat_messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            status = st.status("Running multi-agent workflow...", expanded=False)
            status.write("\u23f3 Planning...")
            try:
                from research_pilot.cli import build_multiagent_graph_workflow_runner
                status.write("\U0001f6e9\ufe0f Building runner...")
                t0 = time.time()
                runner = build_multiagent_graph_workflow_runner(verbose=False)
                status.write("\U0001f504 Running graph workflow...")
                state = runner.answer(user_request=prompt, session=None)
                elapsed = time.time() - t0
                answer = state.final_answer or ""
                status.update(label=f"Completed in {elapsed:.1f}s", state="complete", expanded=False)
                st.markdown(answer)
                st.session_state.chat_messages.append({
                    "role": "assistant", "content": answer,
                    "trace": state,
                })
            except Exception as e:
                status.update(label="Error", state="error")
                st.error(f"Multi-agent error: {e}")

# ===================== PAPER TAB =====================
with tab_paper:
    st.subheader("\U0001f4d6 Paper Research Workflow")
    col1, col2 = st.columns([3, 1])
    with col1:
        question = st.text_input("Research question", placeholder="e.g. What is Agentic RAG?",
                                  key="paper_q", label_visibility="collapsed")
    with col2:
        max_p = st.number_input("Max papers", 1, 10, 3)

    col3, col4, col5 = st.columns(3)
    with col3:
        min_s = st.number_input("Min sources", 1, 20, 3)
    with col4:
        force = st.checkbox("Force download")
    with col5:
        save = st.checkbox("Save report", value=True)

    if st.button("\U0001f50d Run Research", type="primary", use_container_width=True) and question:
        status = st.status("Running paper research workflow...", expanded=True)
        status.write("\u23f3 Phase 1: Checking local evidence...")
        try:
            from research_pilot.cli import build_paper_workflow_runner
            status.write("\U0001f6e9\ufe0f Building paper runner...")
            t0 = time.time()
            runner = build_paper_workflow_runner(verbose=False)
            status.write("\U0001f50d Searching indexed papers...")
            state = runner.paper_research(
                question=question, max_papers=max_p,
                min_sources=min_s, force_download=force, save_report=save,
            )
            elapsed = time.time() - t0
            answer = state.final_answer or ""
            status.update(label=f"Research complete in {elapsed:.1f}s", state="complete", expanded=False)
            st.markdown(answer)
            show_step_trace(state)
        except Exception as e:
            status.update(label="Research failed", state="error")
            st.error(f"Paper research error: {e}")

# ===================== ABOUT TAB =====================
with tab_about:
    st.markdown("""
    ### \U0001f9ea ResearchPilot 0.1.0
    Lightweight multi-agent research assistant with paper RAG.
    
    **Features:**
    - Multi-agent graph workflow (Planner \u2192 Specialist \u2192 Reviewer \u2192 Writer)
    - arXiv paper search, download, and RAG indexing
    - Deterministic paper research with automatic fallback
    - Codebase search and code answer generation
    
    **Run:** `streamlit run demo_app.py`
    """
    )


