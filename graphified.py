#!/usr/bin/env python3
from __future__ import annotations
"""
graphified - Knowledge Graph Generator
Platform-independent CLI to generate knowledge graphs from code repositories

Usage:
    python graphified.py [path] [options]
    
    path    - Target directory to analyze (default: current directory)
    options - Additional options (--ast-only for AST-only extraction)

Outputs:
    graphify-out/
    ├── graph.json       - Persistent knowledge graph (queryable JSON)
    ├── graph.html       - Interactive visualization (open in browser)
    ├── GRAPH_REPORT.md  - Human-readable analysis report
    └── cache/           - SHA256 cache for incremental updates

Features:
    - Auto-installs Python 3.10+ if not found
    - Creates isolated virtual environment
    - Cross-platform support (Windows, Linux, macOS)
"""

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


# ── Minimum version guard (must run before any `list[str]` annotations) ──────
if sys.version_info < (3, 10):
    print("=" * 60)
    print("  PYTHON 3.10+ REQUIRED")
    print("=" * 60)
    print()
    print(f"You are running Python {sys.version_info.major}.{sys.version_info.minor}")
    print("graphified requires Python 3.10 or newer.")
    print()
    if platform.system() == "Windows":
        print("Install options:")
        print("  1. Microsoft Store:  ms-windows-store://search/?query=python")
        print("  2. Winget:           winget install Python.Python.3.12")
        print("  3. Chocolatey:       choco install python312")
        print("  4. Manual:           https://www.python.org/downloads/")
    elif platform.system() == "Darwin":
        print("Install options:")
        print("  1. Homebrew:         brew install python@3.12")
        print("  2. MacPorts:         sudo port install python312")
        print("  3. Manual:           https://www.python.org/downloads/macos/")
    else:
        print("Install options:")
        print("  Ubuntu/Debian:       sudo apt-get install python3.12 python3.12-venv")
        print("  Fedora/RHEL:         sudo dnf install python3.12")
        print("  Arch:                sudo pacman -S python")
        print("  openSUSE:            sudo zypper install python312")
        print("  Manual:              https://www.python.org/downloads/source/")
    print()
    print("After installing, re-run this script.")
    print("=" * 60)
    sys.exit(1)


try:
    import yaml
except ImportError:
    yaml = None


MIN_PYTHON_VERSION = (3, 10)
VENV_NAME = "graphified-venv"
SCRIPT_DIR = Path(__file__).parent.resolve()
VIS_NETWORK_URL = "https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"
STATIC_DIR = SCRIPT_DIR / "static"


class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    CYAN = '\033[0;36m'
    NC = '\033[0m'


def print_info(msg: str) -> None:
    print(f"{Colors.BLUE}[INFO]{Colors.NC} {msg}")


def print_success(msg: str) -> None:
    print(f"{Colors.GREEN}[SUCCESS]{Colors.NC} {msg}")


def print_warning(msg: str) -> None:
    print(f"{Colors.YELLOW}[WARNING]{Colors.NC} {msg}")


def print_error(msg: str) -> None:
    print(f"{Colors.RED}[ERROR]{Colors.NC} {msg}")


def print_step(msg: str) -> None:
    print(f"{Colors.CYAN}[STEP]{Colors.NC} {msg}")


def is_windows() -> bool:
    return platform.system() == "Windows"


def is_linux() -> bool:
    return platform.system() == "Linux"


def is_macos() -> bool:
    return platform.system() == "Darwin"


def check_python_version(python_path: str = None) -> bool:
    executable = python_path or sys.executable
    try:
        result = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True
        )
        version_str = result.stdout.strip() or result.stderr.strip()
        parts = version_str.split()
        if len(parts) >= 2:
            version_parts = parts[1].split(".")
            major = int(version_parts[0])
            minor = int(version_parts[1]) if len(version_parts) > 1 else 0
            return (major, minor) >= MIN_PYTHON_VERSION
    except Exception:
        pass
    return False


def find_python310_plus() -> str:
    if check_python_version(sys.executable):
        return sys.executable
    
    candidates = []
    
    if is_windows():
        for ver in ["3.12", "3.11", "3.10"]:
            ver_nodot = ver.replace(".", "")
            for path in [
                f"C:\\Python{ver_nodot}\\python.exe",
                os.path.expandvars(f"%LOCALAPPDATA%\\Programs\\Python\\Python{ver_nodot}\\python.exe"),
            ]:
                if Path(path).exists():
                    candidates.append(path)
        candidates.extend(["python3.12", "python3.11", "python3.10", "python", "py"])
    elif is_macos():
        candidates = [
            "/opt/homebrew/bin/python3", "/usr/local/bin/python3",
            "python3.12", "python3.11", "python3.10", "python3", "python"
        ]
    else:
        candidates = [
            "/usr/bin/python3", "/usr/local/bin/python3",
            "python3.12", "python3.11", "python3.10", "python3", "python"
        ]
    
    for candidate in candidates:
        if not candidate:
            continue
        try:
            cmd = candidate.split() if " " in candidate else [candidate]
            cmd.append("--version")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=5
            )
            version_str = result.stdout.strip() or result.stderr.strip()
            if version_str:
                parts = version_str.split()
                if len(parts) >= 2:
                    version_parts = parts[1].split(".")
                    major = int(version_parts[0])
                    minor = int(version_parts[1]) if len(version_parts) > 1 else 0
                    if (major, minor) >= MIN_PYTHON_VERSION:
                        return candidate
        except Exception:
            continue
    
    return None


def install_python_windows() -> str:
    print_step("Attempting to install Python 3.12 on Windows...")
    
    if shutil.which("winget"):
        print_info("Using winget to install Python...")
        try:
            subprocess.run(
                ["winget", "install", "Python.Python.3.12", "--accept-source-agreements", "--accept-package-agreements"],
                check=True
            )
            os.environ["PATH"] = os.path.expandvars(r"C:\Users\$USERNAME\AppData\Local\Programs\Python\Python312;C:\Users\$USERNAME\AppData\Local\Programs\Python\Python312\Scripts") + ";" + os.environ.get("PATH", "")
            return find_python310_plus()
        except subprocess.CalledProcessError:
            pass
    
    if shutil.which("choco"):
        print_info("Using Chocolatey to install Python...")
        try:
            subprocess.run(["choco", "install", "python312", "-y"], check=True)
            return find_python310_plus()
        except subprocess.CalledProcessError:
            pass
    
    print_warning("Could not auto-install Python. Please install manually:")
    print("  1. Download from https://www.python.org/downloads/")
    print("  2. Or run: winget install Python.Python.3.12")
    print("  3. Or run: choco install python312")
    return None


def install_python_linux() -> str:
    print_step("Attempting to install Python 3.12 on Linux...")
    
    install_commands = [
        (["apt-get", "update", "&&", "apt-get", "install", "-y", "python3.12", "python3.12-venv", "python3.12-pip"], "apt (Debian/Ubuntu)"),
        (["dnf", "install", "-y", "python3.12", "python3.12-pip"], "dnf (Fedora/RHEL)"),
        (["yum", "install", "-y", "python3.12", "python3.12-pip"], "yum (CentOS)"),
        (["pacman", "-S", "--noconfirm", "python"], "pacman (Arch)"),
        (["zypper", "install", "-y", "python312"], "zypper (openSUSE)"),
    ]
    
    for cmd, name in install_commands:
        if shutil.which(cmd[0]):
            print_info(f"Using {name} to install Python...")
            try:
                subprocess.run(" ".join(cmd), shell=True, check=True)
                return find_python310_plus()
            except subprocess.CalledProcessError:
                continue
    
    print_warning("Could not auto-install Python. Please install manually:")
    print("  Ubuntu/Debian: sudo apt-get install python3.12 python3.12-venv")
    print("  Fedora: sudo dnf install python3.12")
    print("  Arch: sudo pacman -S python")
    return None


def install_python_macos() -> str:
    print_step("Attempting to install Python 3.12 on macOS...")
    
    if shutil.which("brew"):
        print_info("Using Homebrew to install Python...")
        try:
            subprocess.run(["brew", "install", "python@3.12"], check=True)
            return find_python310_plus()
        except subprocess.CalledProcessError:
            pass
    
    print_warning("Could not auto-install Python. Please install manually:")
    print("  1. Install Homebrew: /bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"")
    print("  2. Then run: brew install python@3.12")
    print("  Or download from: https://www.python.org/downloads/")
    return None


def install_python() -> str:
    if is_windows():
        return install_python_windows()
    elif is_linux():
        return install_python_linux()
    elif is_macos():
        return install_python_macos()
    else:
        print_error(f"Unsupported platform: {platform.system()}")
        return None


def get_venv_path() -> Path:
    return SCRIPT_DIR / VENV_NAME


def get_venv_python() -> Path:
    venv_path = get_venv_path()
    if is_windows():
        return venv_path / "Scripts" / "python.exe"
    return venv_path / "bin" / "python"


def venv_exists() -> bool:
    python_path = get_venv_python()
    return python_path.exists() and check_python_version(str(python_path))


def create_venv(python_path: str) -> bool:
    print_step(f"Creating virtual environment with {python_path}...")
    venv_path = get_venv_path()
    
    try:
        subprocess.run(
            [python_path, "-m", "venv", str(venv_path)],
            check=True
        )
        print_success(f"Virtual environment created at {venv_path}")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"Failed to create venv: {e}")
        return False


def install_graphify(python_path: str = None) -> bool:
    executable = python_path or sys.executable
    print_info("Installing graphify...")
    
    install_methods = [
        [executable, "-m", "pip", "install", "--upgrade", "pip"],
        [executable, "-m", "pip", "install", "graphifyy", "-q"],
    ]
    
    for method in install_methods:
        try:
            subprocess.run(method, check=True, capture_output=True)
        except subprocess.CalledProcessError:
            pass
    
    try:
        result = subprocess.run(
            [executable, "-m", "pip", "show", "graphifyy"],
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            return True
    except Exception:
        pass
    
    return False


def check_graphify_installed(python_path: str = None) -> bool:
    executable = python_path or sys.executable
    try:
        result = subprocess.run(
            [executable, "-c", "import graphify; print('OK')"],
            capture_output=True,
            text=True
        )
        return "OK" in result.stdout
    except Exception:
        return False


def relaunch_in_venv() -> None:
    venv_python = get_venv_python()
    script_path = Path(__file__).resolve()
    
    print_info(f"Relaunching in virtual environment...")
    
    args = [str(venv_python), str(script_path)] + sys.argv[1:]
    result = subprocess.run(args)
    sys.exit(result.returncode)


def ensure_environment() -> str:
    if venv_exists():
        venv_python = str(get_venv_python())
        if check_graphify_installed(venv_python):
            print_success("Using existing virtual environment")
            return venv_python
        else:
            print_info("Installing graphify in existing venv...")
            if install_graphify(venv_python):
                return venv_python
            else:
                print_error("Failed to install graphify in venv")
                sys.exit(1)
    
    print_info(f"Python {MIN_PYTHON_VERSION[0]}.{MIN_PYTHON_VERSION[1]}+ required")
    print_info(f"Current Python: {sys.version}")
    
    python_path = find_python310_plus()
    
    if not python_path:
        print_warning("Python 3.10+ not found on system")
        python_path = install_python()
        
        if not python_path:
            print_error("Could not find or install Python 3.10+")
            print()
            print("=" * 60)
            print("  PYTHON 3.10+ REQUIRED")
            print("=" * 60)
            print()
            print("graphified needs Python 3.10 or newer to run.")
            print()
            if is_windows():
                print("Install options:")
                print("  1. Microsoft Store:  ms-windows-store://search/?query=python")
                print("  2. Winget:           winget install Python.Python.3.12")
                print("  3. Chocolatey:       choco install python312")
                print("  4. Manual:           https://www.python.org/downloads/")
            elif is_macos():
                print("Install options:")
                print("  1. Homebrew:         brew install python@3.12")
                print("  2. MacPorts:         sudo port install python312")
                print("  3. Manual:           https://www.python.org/downloads/macos/")
            else:
                print("Install options:")
                print("  Ubuntu/Debian:       sudo apt-get install python3.12 python3.12-venv")
                print("  Fedora/RHEL:         sudo dnf install python3.12")
                print("  Arch:                sudo pacman -S python")
                print("  openSUSE:            sudo zypper install python312")
                print("  Manual:              https://www.python.org/downloads/source/")
            print()
            print("After installing, re-run this script.")
            print("=" * 60)
            sys.exit(1)
    
    print_success(f"Found Python: {python_path}")
    
    if not create_venv(python_path):
        print_error("Failed to create virtual environment")
        sys.exit(1)
    
    venv_python = str(get_venv_python())
    
    if not install_graphify(venv_python):
        print_error("Failed to install graphify in venv")
        sys.exit(1)
    
    print_success("Environment setup complete!")
    return venv_python


def _ensure_tree_sitter_works() -> bool:
    """Detect and auto-fix tree-sitter ABI mismatches (e.g. Language version 15 vs 14)."""
    try:
        from tree_sitter import Language, Parser
        import tree_sitter_python as tsp
        lang = Language(tsp.language())
        parser = Parser(lang)
        return True
    except Exception as exc:
        msg = str(exc)
        if "incompatible language version" in msg.lower() or "incompatible" in msg.lower():
            print_warning(f"tree-sitter ABI mismatch detected: {exc}")
            print_info("Attempting to upgrade tree-sitter to resolve ABI mismatch...")
            try:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "--upgrade", "tree-sitter"],
                    check=True,
                    capture_output=True,
                )
                print_success("tree-sitter upgraded successfully")
            except subprocess.CalledProcessError as pip_err:
                print_error(f"Failed to upgrade tree-sitter: {pip_err}")
                return False

            # Verify in a *fresh* subprocess (old process still has old module loaded)
            test_script = (
                "from tree_sitter import Language, Parser\n"
                "import tree_sitter_python as tsp\n"
                "lang = Language(tsp.language())\n"
                "parser = Parser(lang)\n"
                "print('OK')\n"
            )
            try:
                result = subprocess.run(
                    [sys.executable, "-c", test_script],
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0 and "OK" in result.stdout:
                    print_success("tree-sitter ABI mismatch resolved — restarting...")
                    os.execv(sys.executable, [sys.executable] + sys.argv)
                else:
                    err = result.stderr.strip() or result.stdout.strip()
                    print_warning(f"tree-sitter still incompatible after upgrade: {err}")
                    return False
            except Exception as exc2:
                print_warning(f"tree-sitter verification failed after upgrade: {exc2}")
                return False
        # Some other error (missing package, etc.) — not an ABI mismatch
        return True


def _ensure_vis_network_js() -> Optional[Path]:
    """Download vis-network.min.js to graphified/static/ if missing."""
    STATIC_DIR.mkdir(exist_ok=True)
    local_js = STATIC_DIR / "vis-network.min.js"
    if local_js.exists():
        return local_js
    print_info("Downloading vis-network.min.js for offline HTML support...")
    try:
        urllib.request.urlretrieve(VIS_NETWORK_URL, str(local_js))
        print_success(f"Saved offline JS: {local_js}")
        return local_js
    except Exception as e:
        print_warning(f"Could not download vis-network JS: {e}")
        return None


def _patch_html_for_offline(html_path: str, local_js: Optional[Path]) -> None:
    """Replace CDN script tag with local-first + CDN fallback."""
    if not local_js or not local_js.exists():
        return
    try:
        content = Path(html_path).read_text(encoding="utf-8")
        cdn_tag = '<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>'
        if cdn_tag not in content:
            return
        # relative path from output dir to local js
        output_dir = Path(html_path).parent
        try:
            rel = os.path.relpath(local_js, output_dir).replace("\\", "/")
        except ValueError:
            rel = str(local_js).replace("\\", "/")
        fallback_tag = (
            f'<script src="{rel}"></script>\n'
            f'<script>window.vis || document.write(\'<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"><\\/script>\')</script>'
        )
        content = content.replace(cdn_tag, fallback_tag)
        Path(html_path).write_text(content, encoding="utf-8")
        print_success("HTML patched for offline fallback")
    except Exception as e:
        print_warning(f"Could not patch HTML for offline: {e}")


def _resolve_target_path(args: List[str]) -> str:
    """Reconstruct target path from argv, handling spaces and flags.

    PowerShell / cmd.exe split unquoted paths on spaces, and PowerShell
    additionally evaluates expressions like ``(1)`` → ``1``.  We try a
    few heuristics to recover the original path.
    """
    path_parts = [a for a in args if not a.startswith("--")]

    if not path_parts:
        return "."

    candidates: List[str] = []

    # 1. Straight join (spaces were the only separator)
    candidates.append(" ".join(path_parts))

    # 2. Progressive shorter joins from the end
    for i in range(len(path_parts) - 1, 0, -1):
        candidates.append(" ".join(path_parts[:i]))

    # 3. PowerShell expression heuristic: wrap isolated numeric tokens
    #    e.g.  ['meva', '1', '\ceva']  →  'meva (1)\ceva'
    if len(path_parts) >= 3:
        rebuilt = []
        for p in path_parts:
            if p.isdigit():
                rebuilt.append(f"({p})")
            else:
                rebuilt.append(p)

        def _smart_join(parts: List[str]) -> str:
            """Join path parts, omitting spaces before leading separators."""
            result = parts[0]
            for p in parts[1:]:
                if p.startswith("\\") or p.startswith("/"):
                    result += p
                else:
                    result += " " + p
            return result

        candidates.append(_smart_join(rebuilt))
        # Also try merging the parenthesised token with its predecessor
        for idx in range(1, len(rebuilt)):
            if rebuilt[idx].startswith("(") and rebuilt[idx].endswith(")"):
                merged = (
                    rebuilt[:idx - 1]
                    + [rebuilt[idx - 1] + " " + rebuilt[idx]]
                    + rebuilt[idx + 1:]
                )
                candidates.append(_smart_join(merged))

    # 4. Try every candidate; prefer the longest existing path
    existing = [c for c in candidates if Path(c).exists()]
    if existing:
        # longest path is usually the most specific / correct one
        return max(existing, key=len)

    # Fallback: return the full straight join so the caller can report the error
    return candidates[0]


def run_in_current_python():
    print_info("graphified - Knowledge Graph Generator")
    print_info("=====================================")

    target_path = _resolve_target_path(sys.argv[1:])
    ast_only = "--ast-only" in sys.argv
    
    target = Path(target_path).resolve()
    
    if not target.exists():
        print_error(f"Target path does not exist: {target_path}")
        sys.exit(1)
    
    if not check_graphify_installed():
        if not install_graphify():
            print_error("Failed to install graphify")
            sys.exit(1)
        print_success("graphify installed successfully")
    else:
        print_success("graphify is already installed")
    
    # Auto-fix tree-sitter ABI mismatches before extraction
    if not _ensure_tree_sitter_works():
        print_warning("tree-sitter is not functional; AST extraction may fail")
    
    output_dir = target / "graphify-out"
    output_dir.mkdir(exist_ok=True)
    
    python_path_file = output_dir / ".graphify_python"
    python_path_file.write_text(sys.executable)
    
    print_info(f"Target: {target}")
    
    try:
        from graphify.detect import detect
        from graphify.extract import extract
        from graphify.build import build_from_json
        from graphify.cluster import cluster
        from graphify.export import to_json, to_html
        from graphify.analyze import god_nodes, surprising_connections
    except ImportError as e:
        print_error(f"Failed to import graphify modules: {e}")
        sys.exit(1)
    
    print_info("Detecting files...")
    detection = detect(target)
    
    total_files = detection.get("total_files", 0)
    total_words = detection.get("total_words", 0)
    files_by_type = detection.get("files", {})
    
    print_info(f"Found {total_files} files (~{total_words} words)")
    
    if total_files == 0:
        print_warning(f"No supported files found in {target_path}")
        sys.exit(0)
    
    code_files = files_by_type.get("code", [])
    doc_files = files_by_type.get("document", [])
    paper_files = files_by_type.get("paper", [])
    image_files = files_by_type.get("image", [])
    
    print_info(f"  Code: {len(code_files)} files")
    print_info(f"  Docs: {len(doc_files)} files")
    print_info(f"  Papers: {len(paper_files)} files")
    print_info(f"  Images: {len(image_files)} files")
    
    if total_files > 200 or total_words > 2000000:
        print_warning("Large codebase detected. Consider running on a subdirectory.")
    
    def _extract_skills_from_docs(doc_paths: List[Path]) -> Dict:
        """Parse SKILL.md YAML frontmatter and build nodes+edges from categories."""
        nodes: List[Dict] = []
        edges: List[Dict] = []
        seen_ids: Set[str] = set()

        def _make_id(*parts: str) -> str:
            combined = "_".join(p.strip("_.") for p in parts if p)
            cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", combined)
            return cleaned.strip("_").lower()

        def _parse_frontmatter(text: str) -> Optional[Dict]:
            """Parse simple YAML frontmatter; fallback to regex if PyYAML missing."""
            if not text.startswith("---"):
                return None
            try:
                _, rest = text.split("---", 1)
                frontmatter, _ = rest.split("---", 1)
            except ValueError:
                return None
            if yaml is not None:
                try:
                    return yaml.safe_load(frontmatter) or {}
                except Exception:
                    pass
            # Fallback regex parser for simple key: value pairs
            meta: Dict[str, Any] = {}
            for line in frontmatter.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if ":" in line:
                    key, val = line.split(":", 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    # Try numeric / float
                    if val.replace(".", "", 1).isdigit():
                        meta[key] = float(val) if "." in val else int(val)
                    else:
                        meta[key] = val
            return meta

        for p in doc_paths:
            if not p.name.lower().endswith("skill.md"):
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
                meta = _parse_frontmatter(text)
                if not meta:
                    continue
                name = meta.get("name", p.stem)
                category = meta.get("category", "Uncategorized")
                confidence = meta.get("confidence", 0.5)
                source_file = meta.get("source_file", "")

                skill_nid = _make_id(str(p), name)
                if skill_nid not in seen_ids:
                    seen_ids.add(skill_nid)
                    nodes.append({
                        "id": skill_nid,
                        "label": name,
                        "file_type": "skill",
                        "source_file": str(p),
                        "source_location": "L1",
                        "confidence": confidence,
                    })

                # Category node
                cat_nid = _make_id("category", category)
                if cat_nid not in seen_ids:
                    seen_ids.add(cat_nid)
                    nodes.append({
                        "id": cat_nid,
                        "label": category,
                        "file_type": "category",
                        "source_file": "",
                        "source_location": "",
                    })

                edges.append({
                    "source": skill_nid,
                    "target": cat_nid,
                    "relation": "belongs_to",
                    "confidence": "EXTRACTED",
                    "source_file": str(p),
                    "source_location": "L1",
                    "weight": float(confidence),
                })

                # Cross-link skills that share the same source_file
                if source_file:
                    src_nid = _make_id("source", source_file)
                    if src_nid not in seen_ids:
                        seen_ids.add(src_nid)
                        nodes.append({
                            "id": src_nid,
                            "label": Path(source_file).name,
                            "file_type": "source",
                            "source_file": source_file,
                            "source_location": "",
                        })
                    edges.append({
                        "source": skill_nid,
                        "target": src_nid,
                        "relation": "derived_from",
                        "confidence": "EXTRACTED",
                        "source_file": str(p),
                        "source_location": "L1",
                        "weight": 1.0,
                    })

            except Exception:
                continue

        # Skip related_skill edges for doc-based graphs — they cause O(n²)
        # blow-up (e.g. 1,300 skills in one category → 800k edges) which
        # produces HTML files too large for browsers to open.
        # The belongs_to + derived_from edges are sufficient for navigation.
        return {"nodes": nodes, "edges": edges}

    extraction: dict = {"nodes": [], "edges": []}

    if code_files:
        print_info("Extracting AST structure...")
        code_paths = [Path(f) for f in code_files]
        try:
            extraction = extract(code_paths, cache_root=target)
            nodes = extraction.get("nodes", [])
            edges = extraction.get("edges", [])
            print_info(f"Extracted {len(nodes)} nodes and {len(edges)} edges")
        except Exception as e:
            print_error(f"Extraction failed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

    if doc_files and not extraction.get("nodes"):
        print_info("No code found; building graph from SKILL.md documents...")
        doc_paths = [Path(f) for f in doc_files]
        extraction = _extract_skills_from_docs(doc_paths)
        nodes = extraction.get("nodes", [])
        edges = extraction.get("edges", [])
        print_info(f"Extracted {len(nodes)} nodes and {len(edges)} edges from docs")

    if not extraction.get("nodes"):
        print_warning("No extractable structure found")
        sys.exit(0)
    
    print_info("Building knowledge graph...")
    graph = build_from_json(extraction)
    
    print_info(f"Graph built: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")
    
    if graph.number_of_nodes() == 0:
        print_warning("Empty graph - no structure extracted")
        sys.exit(0)
    
    print_info("Clustering communities...")
    try:
        communities = cluster(graph)
        print_success(f"Found {len(communities)} communities")
    except Exception as e:
        print_warning(f"Clustering failed: {e}")
        communities = {}
    
    print_info("Exporting graph...")
    
    json_path = str(output_dir / "graph.json")
    to_json(graph, communities, json_path)
    print_success(f"Saved: {json_path}")
    
    try:
        html_path = str(output_dir / "graph.html")
        to_html(graph, communities, html_path)
        print_success(f"Saved: {html_path}")
        local_js = _ensure_vis_network_js()
        if local_js:
            _patch_html_for_offline(html_path, local_js)
    except Exception as e:
        print_warning(f"HTML export failed: {e}")
    
    print_info("Generating report...")
    try:
        god_nodes_result = god_nodes(graph, top_n=10)
        surprising = surprising_connections(graph, top_n=5)
        
        community_labels = {cid: f"Community {cid}" for cid in communities.keys()}
        
        report_lines = [
            "# Knowledge Graph Report",
            "",
            f"**Generated from:** {target_path}",
            f"**Nodes:** {graph.number_of_nodes()}",
            f"**Edges:** {graph.number_of_edges()}",
            f"**Communities:** {len(communities)}",
            "",
            "## God Nodes (Most Connected)",
            "",
        ]
        
        for item in god_nodes_result:
            if isinstance(item, (list, tuple)):
                if len(item) >= 2:
                    node_id = item[0]
                    degree = item[1]
                    report_lines.append(f"- **{node_id}** (degree: {degree})")
                else:
                    report_lines.append(f"- {item[0] if item else 'unknown'}")
            else:
                report_lines.append(f"- {item}")
        
        report_lines.extend([
            "",
            "## Surprising Connections",
            "",
        ])
        
        for conn in surprising:
            if isinstance(conn, (list, tuple)):
                report_lines.append(f"- {' -> '.join(str(c) for c in conn)}")
            else:
                report_lines.append(f"- {conn}")
        
        report_lines.extend([
            "",
            "## Top Communities",
            "",
        ])
        
        for cid, nodes in sorted(communities.items(), key=lambda x: -len(x[1]))[:10]:
            report_lines.append(f"- **{community_labels[cid]}** ({len(nodes)} nodes)")
        
        report_path = output_dir / "GRAPH_REPORT.md"
        report_path.write_text("\n".join(report_lines))
        print_success(f"Saved: {report_path}")
    except Exception as e:
        print_warning(f"Report generation failed: {e}")
    
    print()
    print_success("Knowledge graph generated successfully!")
    print()
    print("Generated files:")
    print(f"  {output_dir}/")
    print(f"  ├── graph.json       ({graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges)")
    print(f"  ├── graph.html       (open in browser)")
    print(f"  └── GRAPH_REPORT.md  (analysis report)")
    print()
    print("Usage:")
    print("  - Open graph.html in your browser for interactive visualization")
    print("  - Read GRAPH_REPORT.md for god nodes and community structure")
    print("  - Query graph.json programmatically for GraphRAG")


def main():
    IN_VENV = os.environ.get("VIRTUAL_ENV") is not None or hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
    
    if IN_VENV and check_python_version():
        run_in_current_python()
        return
    
    if check_python_version():
        if venv_exists():
            venv_python = str(get_venv_python())
            if check_python_version(venv_python):
                relaunch_in_venv()
                return
        run_in_current_python()
        return
    
    python_path = ensure_environment()
    
    if python_path and python_path != sys.executable:
        script_path = Path(__file__).resolve()
        args = [python_path, str(script_path)] + sys.argv[1:]
        result = subprocess.run(args)
        sys.exit(result.returncode)
    else:
        run_in_current_python()


if __name__ == "__main__":
    main()
##