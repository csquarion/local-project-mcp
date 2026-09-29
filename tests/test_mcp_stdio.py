"""Check the installed package's nine MCP tools over the actual stdio transport."""

import asyncio
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import pymupdf
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from local_project_mcp.config import save_config


class StdioPackageTest(unittest.TestCase):
    def test_mcp_tools(self) -> None:
        asyncio.run(self.check_tools())

    async def check_tools(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "home"
            project = Path(temporary) / "project"
            project.mkdir()
            (project / "notes.md").write_text("Distinctive marker: cedar-lamp\n", encoding="utf-8")
            (project / "script.ps1").write_text("Write-Output 'sample script'\n", encoding="utf-8")
            document = pymupdf.open()
            document.new_page().insert_text((72, 72), "PDF test sentence")
            document.save(project / "sample.pdf")
            document.close()
            pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20), False)
            pixmap.clear_with(0x336699)
            pixmap.save(project / "sample.png")

            old_home = os.environ.get("LOCAL_PROJECT_MCP_HOME")
            os.environ["LOCAL_PROJECT_MCP_HOME"] = str(home)
            try:
                save_config({"project_root": str(project), "tunnel_id": "test", "source": "test"})
            finally:
                if old_home is None:
                    os.environ.pop("LOCAL_PROJECT_MCP_HOME", None)
                else:
                    os.environ["LOCAL_PROJECT_MCP_HOME"] = old_home

            rg = shutil.which("rg")
            self.assertIsNotNone(rg)
            (home / "bin").mkdir()
            shutil.copyfile(rg, home / "bin" / "rg.exe")
            env = os.environ.copy()
            env["LOCAL_PROJECT_MCP_HOME"] = str(home)
            parameters = StdioServerParameters(
                command=sys.executable,
                args=["-m", "local_project_mcp.cli", "mcp-stdio"],
                cwd=str(project),
                env=env,
            )
            async with stdio_client(parameters) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    names = {tool.name for tool in (await session.list_tools()).tools}
                    self.assertEqual(names, {"project_status", "list_directory", "find_files", "search_files", "read_text", "read_image", "read_pdf_text", "read_pdf_page", "run_command"})

                    async def call(name: str, **arguments):
                        result = await session.call_tool(name, arguments=arguments)
                        self.assertFalse(result.isError, (name, result))
                        return result.content

                    self.assertIn(str(project), (await call("project_status"))[0].text)
                    self.assertIn("notes.md", (await call("list_directory"))[0].text)
                    self.assertIn("notes.md", (await call("find_files", name_fragment="notes"))[0].text)
                    self.assertIn("cedar-lamp", (await call("search_files", pattern="cedar-lamp"))[0].text)
                    self.assertIn("cedar-lamp", (await call("read_text", path="notes.md"))[0].text)
                    self.assertIn("sample script", (await call("read_text", path="script.ps1"))[0].text)
                    self.assertEqual((await call("read_image", path="sample.png"))[0].type, "image")
                    self.assertIn("PDF test sentence", (await call("read_pdf_text", path="sample.pdf"))[0].text)
                    self.assertEqual((await call("read_pdf_page", path="sample.pdf"))[0].type, "image")
                    self.assertIn("ok", (await call("run_command", command="Write-Output 'ok'"))[0].text)


if __name__ == "__main__":
    unittest.main()
