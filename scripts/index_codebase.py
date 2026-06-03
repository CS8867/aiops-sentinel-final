"""
Clones a target GitHub repository and indexes its Python source files into ChromaDB.

Usage:
    python scripts/index_codebase.py --repo-url https://github.com/owner/repo
    python scripts/index_codebase.py --repo-path ./path/to/local/repo

The script writes chroma_db/repo_meta.json so that app.py knows which repo
is currently indexed and can match its name against traceback paths at runtime.
"""
import argparse
import json
import os
import re
import shutil
import subprocess

from langchain_community.document_loaders.generic import GenericLoader
from langchain_community.document_loaders.parsers import LanguageParser
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_text_splitters import Language, RecursiveCharacterTextSplitter

INDEXED_REPO_DIR = "./indexed_repo"
CHROMA_DIR = "./chroma_db"
REPO_META_PATH = os.path.join(CHROMA_DIR, "repo_meta.json")


def _repo_name_from_url(url: str) -> str:
    """Extract the repository name from a GitHub URL."""
    name = url.rstrip("/").split("/")[-1]
    return re.sub(r"\.git$", "", name)


def clone_repo(repo_url: str, branch: str | None = None, github_pat: str | None = None) -> str:
    """Clone a GitHub repository to INDEXED_REPO_DIR and return its path."""
    if os.path.exists(INDEXED_REPO_DIR):
        shutil.rmtree(INDEXED_REPO_DIR)

    clone_url = repo_url
    if github_pat and "github.com" in repo_url:
        clone_url = repo_url.replace("https://", f"https://{github_pat}@")

    cmd = ["git", "clone", "--depth=1"]
    if branch:
        cmd += ["--branch", branch]
    cmd += [clone_url, INDEXED_REPO_DIR]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"git clone failed:\n{result.stderr.strip()}")

    print(f"   Cloned to {INDEXED_REPO_DIR}/")
    return INDEXED_REPO_DIR


def index_repo(repo_path: str, repo_url: str = "") -> int:
    """
    Index Python files from repo_path into ChromaDB and write repo_meta.json.
    Returns the number of chunks stored.
    """
    if not os.path.exists(repo_path):
        raise FileNotFoundError(f"Repository not found at '{repo_path}'")

    if os.path.exists(CHROMA_DIR):
        shutil.rmtree(CHROMA_DIR)
        print("   Cleared existing vector store.")

    print("1. Loading Python files...")
    loader = GenericLoader.from_filesystem(
        repo_path,
        glob="**/*.py",
        suffixes=[".py"],
        parser=LanguageParser(language=Language.PYTHON, parser_threshold=500),
    )
    documents = loader.load()
    print(f"   Loaded {len(documents)} documents.")

    # AST parser keeps functions and classes atomic, but individual units can still
    # exceed a comfortable embedding window — split further at Python-aware boundaries.
    print("2. Splitting code into chunks...")
    splitter = RecursiveCharacterTextSplitter.from_language(
        language=Language.PYTHON,
        chunk_size=1500,
        chunk_overlap=150,
    )
    texts = splitter.split_documents(documents)
    print(f"   Created {len(texts)} chunks.")

    print("3. Building vector database...")
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    Chroma.from_documents(texts, embeddings, persist_directory=CHROMA_DIR)

    repo_name = _repo_name_from_url(repo_url) if repo_url else os.path.basename(os.path.abspath(repo_path))
    meta = {
        "repo_dir": repo_path,
        "repo_name": repo_name,
        "repo_url": repo_url,
    }
    with open(REPO_META_PATH, "w") as f:
        json.dump(meta, f, indent=2)

    print(f"Done. {len(texts)} chunks indexed for repo '{repo_name}'.")
    return len(texts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Index a Python codebase into ChromaDB.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--repo-url", help="GitHub HTTPS URL to clone and index")
    source.add_argument("--repo-path", help="Path to an already-cloned local repository")
    parser.add_argument("--branch", help="Branch to clone (defaults to the repo default branch)")
    parser.add_argument(
        "--github-pat",
        default=os.getenv("GITHUB_PAT"),
        help="Personal access token for private repositories (defaults to $GITHUB_PAT)",
    )
    args = parser.parse_args()

    if args.repo_url:
        # Expand owner/repo shorthand
        url = args.repo_url
        if "/" in url and not url.startswith("http"):
            url = f"https://github.com/{url}"
        print(f"Cloning {url}...")
        repo_path = clone_repo(url, branch=args.branch, github_pat=args.github_pat)
        index_repo(repo_path, repo_url=url)
    else:
        index_repo(args.repo_path)
