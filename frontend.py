import json
import re
import subprocess
import sys

import streamlit as st
import os
import dotenv
from app import run_analysis_with_graph

dotenv.load_dotenv(override=True)

GOOGLE_API_KEY_ENV = "GOOGLE_API_KEY"
GITHUB_PAT_ENV = "GITHUB_PAT"
GITHUB_OWNER_ENV = "GITHUB_OWNER"
GITHUB_REPO_ENV = "GITHUB_REPO"


def _parse_github_url(url: str) -> tuple[str, str] | tuple[None, None]:
    """Extract (owner, repo) from a GitHub URL or owner/repo shorthand."""
    url = url.strip().rstrip("/")
    match = re.search(r"github\.com[/:]([^/]+)/([^/]+?)(?:\.git)?$", url)
    if match:
        return match.group(1), match.group(2)
    parts = url.split("/")
    if len(parts) == 2 and parts[0] and parts[1]:
        return parts[0], parts[1]
    return None, None


def _load_repo_meta() -> dict | None:
    meta_path = os.path.join("chroma_db", "repo_meta.json")
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            return json.load(f)
    return None


st.set_page_config(page_title="Sentinel RCA Agent", layout="wide")
st.title("Sentinel RCA Agent")
st.caption("Autonomous Root Cause Analysis powered by LangGraph + Gemini")

# --- SIDEBAR ---
with st.sidebar:
    st.header("Configuration")

    env_api_key = os.getenv(GOOGLE_API_KEY_ENV, "")
    api_key = st.text_input("Google API Key", type="password", value=env_api_key)
    if api_key:
        os.environ[GOOGLE_API_KEY_ENV] = api_key

    env_pat = os.getenv(GITHUB_PAT_ENV, "")
    github_pat = st.text_input("GitHub PAT", type="password", value=env_pat)
    if github_pat:
        os.environ[GITHUB_PAT_ENV] = github_pat

    st.divider()
    st.subheader("Target Repository")

    meta = _load_repo_meta()
    if meta:
        indexed_label = meta.get("repo_url") or meta.get("repo_name") or meta.get("repo_dir")
        st.caption(f"Indexed: `{indexed_label}`")
        # Keep GITHUB_OWNER / GITHUB_REPO in sync with whatever is indexed
        owner, repo = _parse_github_url(meta.get("repo_url", ""))
        if owner and not os.environ.get(GITHUB_OWNER_ENV):
            os.environ[GITHUB_OWNER_ENV] = owner
        if repo and not os.environ.get(GITHUB_REPO_ENV):
            os.environ[GITHUB_REPO_ENV] = repo
    else:
        st.caption("No repository indexed yet. Using bundled sample data.")

    repo_url_input = st.text_input(
        "GitHub Repo URL",
        placeholder="https://github.com/owner/repo  or  owner/repo",
    )
    if st.button("Index Repository"):
        if not repo_url_input.strip():
            st.error("Enter a GitHub URL or owner/repo shorthand.")
        else:
            with st.spinner(f"Cloning and indexing {repo_url_input.strip()}…"):
                result = subprocess.run(
                    [sys.executable, "scripts/index_codebase.py", "--repo-url", repo_url_input.strip()],
                    capture_output=True,
                    text=True,
                )
            if result.returncode == 0:
                owner, repo = _parse_github_url(repo_url_input.strip())
                if owner:
                    os.environ[GITHUB_OWNER_ENV] = owner
                if repo:
                    os.environ[GITHUB_REPO_ENV] = repo
                st.success("Repository indexed successfully.")
                st.rerun()
            else:
                st.error(f"Indexing failed:\n\n```\n{result.stderr or result.stdout}\n```")

    st.divider()
    uploaded_csv = st.file_uploader("Upload Metrics (CSV)", type=["csv"])
    uploaded_log = st.file_uploader("Upload Application Logs", type=["log", "txt"])

# --- SESSION STATE ---
for key in ["decision", "analysis_report", "generated_fix", "target_file", "github_status"]:
    if key not in st.session_state:
        st.session_state[key] = None

# --- TRIGGER ---
if st.button("Run AI Analysis", type="primary"):
    if not os.environ.get(GOOGLE_API_KEY_ENV):
        st.error("Please enter a Google API Key in the sidebar.")
    elif not uploaded_csv or not uploaded_log:
        st.error("Please upload both a CSV metrics file and a log file.")
    else:
        csv_text = uploaded_csv.getvalue().decode("utf-8")
        log_text = uploaded_log.getvalue().decode("utf-8")

        with st.spinner("Running RCA pipeline..."):
            final_state = run_analysis_with_graph(csv_text, log_text)

        st.session_state.decision = final_state.get("decision", "")
        st.session_state.analysis_report = final_state.get("analysis_report")
        st.session_state.generated_fix = final_state.get("generated_fix")
        st.session_state.target_file = final_state.get("target_file")
        st.session_state.github_status = final_state.get("github_result")

# --- RESULTS ---
if st.session_state.decision:
    if "INCIDENT" in st.session_state.decision:
        st.error("Incident detected!")
    else:
        st.success(f"System status: **{st.session_state.decision}** — No action required.")

if st.session_state.analysis_report:
    st.markdown("### Root Cause Analysis Report")
    clean_report = (
        st.session_state.analysis_report
        .replace("<FIX_CODE>", "```python")
        .replace("</FIX_CODE>", "```")
    )
    st.markdown(clean_report)

if st.session_state.generated_fix:
    st.divider()
    st.subheader("Automated Remediation")
    col1, col2 = st.columns([3, 1])
    with col1:
        st.info(f"Target file: `{st.session_state.target_file}`")
        with st.expander("Preview generated fix"):
            st.code(st.session_state.generated_fix, language="python")
    with col2:
        st.markdown("**GitHub push status:**")
        if st.session_state.github_status:
            github_status = str(st.session_state.github_status)
            if github_status.startswith("GitHub push failed"):
                st.error(github_status[:300])
            elif github_status.startswith("GitHub push skipped"):
                st.info(github_status[:300])
            else:
                st.success(github_status[:300])
        else:
            st.warning("Not pushed yet.")
