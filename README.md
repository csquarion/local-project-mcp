# Local Project MCP

Use a folder on your Windows computer from ChatGPT through OpenAI Secure MCP Tunnel. The package provides file search, text/image/PDF reading, and PowerShell commands. The selected project is the default directory for relative paths; it is not an access boundary. `run_command` runs with your Windows user permissions.

## Install on a Windows computer

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and open PowerShell or Windows Terminal.
2. Run:

   ```powershell
   uvx --from "git+https://github.com/csquarion/local-project-mcp.git@main" local-project-mcp setup
   ```

3. Select a local project folder in the Windows folder picker. The setup command opens [OpenAI Platform tunnel settings](https://platform.openai.com/settings/organization/tunnels). Sign in and create a tunnel for this computer, then paste its `tunnel_id` into the terminal. Create a runtime API key with Tunnels Read + Use access and paste it at the hidden prompt. The tunnel must be associated with the ChatGPT workspace you will use.
4. Setup installs the command, OpenAI `tunnel-client`, and `ripgrep` for the current Windows user. It checks the tunnel, starts it, and registers a task to start at your Windows sign-in. When setup opens [ChatGPT Plugins](https://chatgpt.com/plugins), enable Developer mode and create a connection using **Tunnel**, selecting this computer's tunnel ID.

Each computer that exposes its own files needs its own tunnel ID and ChatGPT connection. You can use the same OpenAI account on multiple computers. Setup does not require administrator privileges.

The runtime key is saved as a Windows user-bound DPAPI value under `%LOCALAPPDATA%\LocalProjectMcp`; project and tunnel settings are saved there too. Do not copy that directory to another user or computer. Program code is installed separately by `uv tool install`.

## Use and update

The `LocalProjectMcpTunnel` scheduled task runs at sign-in. To select another default project folder, run:

```powershell
uv tool run local-project-mcp choose-project
```

To update manually, stop the task, reinstall from GitHub, and start it again:

```powershell
Stop-ScheduledTask -TaskName LocalProjectMcpTunnel
uv tool install --reinstall --refresh "git+https://github.com/csquarion/local-project-mcp.git@main"
Start-ScheduledTask -TaskName LocalProjectMcpTunnel
```

The program does not update automatically at sign-in. If you want to disconnect temporarily, stop the scheduled task.

## Tools

`project_status`, `list_directory`, `find_files`, `search_files`, `read_text`, `read_image`, `read_pdf_text`, `read_pdf_page`, and `run_command`.
