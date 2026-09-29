"""MCP tools for the configured local project."""

import subprocess
import sys
from pathlib import Path

import pymupdf
from mcp.server.fastmcp import FastMCP, Image

from .config import data_dir, project_root, resolve


def ripgrep() -> str:
    bundled = data_dir() / "bin" / "rg.exe"
    return str(bundled) if bundled.is_file() else "rg"


mcp = FastMCP(
    "Local Project",
    instructions="The active project folder is the default working directory, not an access boundary. Use project_status to see it. run_command executes Windows PowerShell as the current Windows user and may read or change accessible files or use the network.",
)


@mcp.tool()
def project_status() -> str:
    """Show the currently selected local project folder."""
    return str(project_root())


@mcp.tool()
def list_directory(path: str = ".") -> str:
    """List direct children of a directory. Relative paths start at the active project."""
    directory = resolve(path)
    return "\n".join(("DIR  " if p.is_dir() else "FILE ") + p.name for p in sorted(directory.iterdir(), key=lambda p: p.name.lower()))


@mcp.tool()
def find_files(name_fragment: str, path: str = ".") -> str:
    """Find files by part of their name when the exact path is unknown."""
    target = resolve(path)
    result = subprocess.run([ripgrep(), "--files", "--hidden", "--glob", "!.git", str(target)], capture_output=True, text=True, errors="replace", timeout=120)
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr)
    return "\n".join(line for line in result.stdout.splitlines() if name_fragment.lower() in Path(line).name.lower())[:100_000] or "No matches."


@mcp.tool()
def search_files(pattern: str, path: str = ".") -> str:
    """Search text contents with ripgrep. Relative paths start at the active project."""
    target = resolve(path)
    result = subprocess.run([ripgrep(), "-n", "--hidden", "--glob", "!.git", "--", pattern, str(target)], capture_output=True, text=True, errors="replace", timeout=120)
    return result.stdout[:100_000] or ("No matches." if result.returncode == 1 else result.stderr[:10_000])


@mcp.tool()
def read_text(path: str) -> str:
    """Read a UTF-8 text file such as Markdown or a script. Relative paths start at the active project."""
    return resolve(path).read_text(encoding="utf-8-sig")[:100_000]


@mcp.tool()
def read_image(path: str) -> Image:
    """Return a local PNG, JPEG, GIF, or WebP image for visual analysis."""
    target = resolve(path)
    if target.suffix.lower() not in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
        raise ValueError("Supported image types: PNG, JPEG, GIF, WebP")
    return Image(path=str(target))


@mcp.tool()
def read_pdf_text(path: str) -> str:
    """Extract the text of a local PDF. For diagrams or scanned pages, call read_pdf_page."""
    with pymupdf.open(resolve(path)) as document:
        return "\n\n".join(f"--- Page {i + 1} ---\n{page.get_text()}" for i, page in enumerate(document))[:100_000]


@mcp.tool()
def read_pdf_page(path: str, page: int = 1) -> Image:
    """Render one 1-based PDF page as an image for visual analysis."""
    with pymupdf.open(resolve(path)) as document:
        if page < 1 or page > len(document):
            raise ValueError(f"Page must be between 1 and {len(document)}")
        image = document[page - 1].get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False).tobytes("png")
    return Image(data=image, format="png")


@mcp.tool()
def run_command(command: str) -> str:
    """Run PowerShell as the current Windows user; the project is only its default working directory."""
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command], cwd=project_root(), capture_output=True, text=True, errors="replace", timeout=120)
    return f"Exit code: {result.returncode}\nSTDOUT:\n{result.stdout[:100_000]}\nSTDERR:\n{result.stderr[:20_000]}"


def main() -> None:
    print(f"Active project: {project_root()}", file=sys.stderr)
    mcp.run(transport="stdio")
