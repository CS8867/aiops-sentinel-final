import asyncio
import json
import os
import re
from typing import TypedDict

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langgraph.graph import StateGraph, END
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


DEFAULT_MODEL = "gemini-flash-latest"
VECTOR_DB_PATH = "./chroma_db"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
_REPO_META_PATH = os.path.join(VECTOR_DB_PATH, "repo_meta.json")


def _load_repo_meta() -> dict:
    """Return the metadata written by index_codebase.py for the currently indexed repo."""
    try:
        with open(_REPO_META_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Fallback for the bundled sample data (test-python-code)
        return {"repo_dir": "./test-python-code", "repo_name": "test-python-code", "repo_url": ""}


class GraphState(TypedDict):
    csv_content: str
    log_content: str
    decision: str
    error_chunk: str
    context_text: str
    analysis_report: str
    target_file: str
    generated_fix: str
    github_result: str


def triage_node(state: GraphState):
    """Analyzes performance metrics to classify system health as INCIDENT or HEALTHY."""
    llm = ChatGoogleGenerativeAI(model=DEFAULT_MODEL, temperature=0)
    triage_prompt = PromptTemplate.from_template(
        "You are an SRE monitoring system. Analyze the following service metrics and determine if there is an active incident. "
        "Look for indicators such as: non-zero failure rates, elevated error counts, HTTP 5xx status codes, "
        "services reporting zero traffic when they should have traffic, significant latency spikes, or any error types present. "
        "Respond with only a single word: 'INCIDENT' or 'HEALTHY'.\n\nMetrics:\n{metrics}"
    )
    chain = triage_prompt | llm | StrOutputParser()
    decision = chain.invoke({"metrics": state["csv_content"]})
    return {"decision": decision.strip()}


def log_extraction_node(state: GraphState):
    """Extracts the relevant stack trace or error from application logs."""
    llm = ChatGoogleGenerativeAI(model=DEFAULT_MODEL, temperature=0)
    log_parser_prompt = PromptTemplate.from_template(
        "Review these logs and extract the specific stack trace/error causing the crash. Logs: {logs}"
    )
    chain = log_parser_prompt | llm | StrOutputParser()
    log_tail = "\n".join(state["log_content"].splitlines()[-100:])
    error_chunk = chain.invoke({"logs": log_tail})
    return {"error_chunk": error_chunk}


def rca_fixer_node(state: GraphState):
    """Retrieves relevant code from the vector store, performs root cause analysis,
    and generates a corrected version of the faulty file."""
    llm = ChatGoogleGenerativeAI(model=DEFAULT_MODEL, temperature=0)
    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    vectorstore = Chroma(persist_directory=VECTOR_DB_PATH, embedding_function=embeddings)
    retriever = vectorstore.as_retriever(search_kwargs={"k": 3})

    meta = _load_repo_meta()
    repo_name = meta.get("repo_name", "test-python-code")
    repo_dir = meta.get("repo_dir", "./test-python-code")

    # Extract individual frames from the traceback: (filename, "File..." + code line).
    # Match on the repo name as it appears in production paths (e.g. "/home/user/my-repo/services.py").
    frame_pattern = re.compile(rf'{re.escape(repo_name)}[\\/](.*?)", line \d+')
    lines = state["error_chunk"].splitlines()
    frames = []
    for i, line in enumerate(lines):
        match = frame_pattern.search(line)
        if match:
            filename = match.group(1).replace("\\", "/")
            code_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
            query = line.strip() + "\n" + code_line
            frames.append((filename, query))

    if frames:
        # Query the final traceback frame first because it usually points to the faulting code path.
        target_filename, crash_query = frames[-1]
        all_docs = retriever.invoke(crash_query)
        found_path = target_filename
    else:
        # Fallback: full error chunk query, derive path from ChromaDB document metadata.
        all_docs = retriever.invoke(state["error_chunk"])
        raw_path = (all_docs[0].metadata.get("source") or all_docs[0].metadata.get("file_path")) if all_docs else "Unknown"
        try:
            found_path = os.path.relpath(raw_path, repo_dir).replace("\\", "/")
        except (ValueError, TypeError):
            found_path = os.path.basename(raw_path) if raw_path else "Unknown"

    context_text = "\n\n".join(doc.page_content for doc in all_docs)

    rca_template = """
    You are a Senior Python SRE.
    1. Analyze the Error: {question}
    2. Read the Code: {context}
    3. Explain the Root Cause.
    4. Provide the COMPLETE corrected file content.
    IMPORTANT: Wrap code inside <FIX_CODE> tags.
    """
    prompt = PromptTemplate.from_template(rca_template)
    chain = prompt | llm | StrOutputParser()
    report = chain.invoke({"question": state["error_chunk"], "context": context_text})

    code_match = re.search(r"<FIX_CODE>(.*?)</FIX_CODE>", report, re.DOTALL)
    generated_fix = code_match.group(1).strip() if code_match else None

    return {
        "analysis_report": report,
        "generated_fix": generated_fix,
        "target_file": found_path
    }


async def github_action_node(state: GraphState):
    """Pushes the generated fix to GitHub via the MCP GitHub server."""
    if not state["generated_fix"]:
        return {"github_result": "No fix generated to push."}

    github_pat = os.getenv("GITHUB_PAT")
    owner = os.getenv("GITHUB_OWNER")
    repo = os.getenv("GITHUB_REPO")

    if not github_pat:
        return {"github_result": "GitHub push skipped: GITHUB_PAT is not configured."}

    if not owner or not repo:
        return {
            "github_result": "GitHub push skipped: set GITHUB_OWNER and GITHUB_REPO to enable remediation commits."
        }

    server_params = StdioServerParameters(
        command="npx.cmd",
        args=["-y", "@modelcontextprotocol/server-github"],
        env={**os.environ, "GITHUB_PERSONAL_ACCESS_TOKEN": github_pat}
    )

    try:
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                result = await session.call_tool("create_or_update_file", {
                    "owner": owner,
                    "repo": repo,
                    "path": state["target_file"],
                    "content": state["generated_fix"],
                    "message": f"AI-SRE: Automated fix for {state['target_file']}",
                    "branch": "ai-remediation"
                })
                return {"github_result": str(result)}
    except Exception as exc:
        return {"github_result": f"GitHub push failed: {exc}"}


def decide_to_analyze(state: GraphState):
    """Conditional edge: route to log extraction on INCIDENT, otherwise end."""
    if "INCIDENT" in state["decision"]:
        return "extract_logs"
    return "end"


workflow = StateGraph(GraphState)

workflow.add_node("triage", triage_node)
workflow.add_node("extract_logs", log_extraction_node)
workflow.add_node("rca_fixer", rca_fixer_node)
workflow.add_node("github_push", github_action_node)

workflow.set_entry_point("triage")

workflow.add_conditional_edges(
    "triage",
    decide_to_analyze,
    {
        "extract_logs": "extract_logs",
        "end": END
    }
)

workflow.add_edge("extract_logs", "rca_fixer")
workflow.add_edge("rca_fixer", "github_push")
workflow.add_edge("github_push", END)

app = workflow.compile()


def run_analysis_with_graph(csv_text, log_text):
    """Entry point: runs the full RCA pipeline and updates Streamlit session state."""
    inputs = {
        "csv_content": csv_text,
        "log_content": log_text,
        "decision": "",
        "error_chunk": "",
        "context_text": "",
        "analysis_report": "",
        "target_file": "",
        "generated_fix": "",
        "github_result": ""
    }

    return asyncio.run(app.ainvoke(inputs))