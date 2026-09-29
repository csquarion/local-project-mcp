"""Windows setup and runtime commands for Local Project MCP."""

import argparse
import getpass
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import webbrowser
import zipfile
from pathlib import Path

from .config import data_dir, load_config, save_config


TASK_NAME = "LocalProjectMcpTunnel"
PROFILE_NAME = "local-project"
DEFAULT_SOURCE = "git+https://github.com/csquarion/local-project-mcp.git@main"


def windows_powershell_env() -> dict[str, str]:
    env = os.environ.copy()
    modules = Path(env.get("SystemRoot", "C:\\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "Modules"
    env["PSModulePath"] = str(modules)
    return env


def powershell(script: str, *, stdin: str = "") -> str:
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", "$ErrorActionPreference = 'Stop'; " + script],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=windows_powershell_env(),
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "PowerShell command failed.")
    return result.stdout.strip()


def save_runtime_key(key: str) -> None:
    script = (
        "Import-Module Microsoft.PowerShell.Security -ErrorAction Stop; "
        "$plain = [Console]::In.ReadToEnd(); "
        "$secure = ConvertTo-SecureString -String $plain -AsPlainText -Force; "
        "ConvertFrom-SecureString -SecureString $secure"
    )
    encrypted = powershell(script, stdin=key)
    if not encrypted:
        raise RuntimeError("Windows did not protect the runtime key.")
    data_dir().mkdir(parents=True, exist_ok=True)
    (data_dir() / "runtime-key.dpapi").write_text(encrypted, encoding="utf-8")


def load_runtime_key() -> str:
    encrypted = (data_dir() / "runtime-key.dpapi").read_text(encoding="utf-8")
    script = (
        "Import-Module Microsoft.PowerShell.Security -ErrorAction Stop; "
        "$secure = [Console]::In.ReadToEnd() | ConvertTo-SecureString; "
        "$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure); "
        "try { [Console]::Out.Write([Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)) } "
        "finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }"
    )
    return powershell(script, stdin=encrypted)


def select_project() -> Path:
    script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "$picker = New-Object System.Windows.Forms.FolderBrowserDialog; "
        "$picker.Description = 'Select the project folder for ChatGPT'; "
        "if ($picker.ShowDialog() -eq 'OK') { [Console]::Out.Write($picker.SelectedPath) }"
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-STA", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=windows_powershell_env(),
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Folder picker failed.")
    selected = result.stdout.strip()
    if not selected:
        raise RuntimeError("No project folder was selected.")
    path = Path(selected)
    if not path.is_dir():
        raise RuntimeError("No project folder was selected.")
    return path.resolve()


def machine_arch() -> str:
    machine = platform.machine().lower()
    if machine in {"amd64", "x86_64"}:
        return "amd64"
    if machine in {"arm64", "aarch64"}:
        return "arm64"
    raise RuntimeError(f"Unsupported Windows architecture: {machine}")


def github_asset(repository: str, prefix: str, suffix: str) -> str:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/releases/latest",
        headers={"User-Agent": "local-project-mcp"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        release = json.load(response)
    matches = [
        asset["browser_download_url"]
        for asset in release["assets"]
        if asset["name"].startswith(prefix) and asset["name"].endswith(suffix)
    ]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one release asset ending in {suffix} from {repository}.")
    return matches[0]


def install_archive_exe(url: str, executable: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        archive = Path(temporary) / "download.zip"
        urllib.request.urlretrieve(url, archive)
        with zipfile.ZipFile(archive) as package:
            matches = [name for name in package.namelist() if Path(name).name.lower() == executable.lower()]
            if len(matches) != 1:
                raise RuntimeError(f"Expected {executable} in the downloaded archive.")
            with package.open(matches[0]) as source, destination.open("wb") as target:
                shutil.copyfileobj(source, target)


def install_binaries() -> None:
    arch = machine_arch()
    directory = data_dir() / "bin"
    tunnel = directory / "tunnel-client.exe"
    if not tunnel.is_file():
        print("Downloading OpenAI tunnel-client...")
        url = github_asset("openai/tunnel-client", "tunnel-client-v", f"-windows-{arch}.zip")
        install_archive_exe(url, "tunnel-client.exe", tunnel)
    ripgrep = directory / "rg.exe"
    if not ripgrep.is_file():
        print("Downloading ripgrep...")
        target = "x86_64" if arch == "amd64" else "aarch64"
        url = github_asset("BurntSushi/ripgrep", "ripgrep-", f"-{target}-pc-windows-msvc.zip")
        install_archive_exe(url, "rg.exe", ripgrep)


def installed_command(source: str) -> Path:
    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("uv was not found. Install uv before running setup.")
    subprocess.run([uv, "tool", "install", source], check=True)
    result = subprocess.run([uv, "tool", "dir", "--bin"], check=True, capture_output=True, text=True)
    executable = Path(result.stdout.strip()) / "local-project-mcp.exe"
    if not executable.is_file():
        raise RuntimeError(f"Installed command was not found: {executable}")
    return executable


def write_profile(executable: Path, tunnel_id: str) -> None:
    command = subprocess.list2cmdline([str(executable).replace("\\", "/"), "mcp-stdio"])
    profile_dir = data_dir() / "profiles"
    profile_dir.mkdir(parents=True, exist_ok=True)
    profile = (
        "config_version: 1\n"
        "control_plane:\n"
        "  base_url: \"https://api.openai.com\"\n"
        f"  tunnel_id: {json.dumps(tunnel_id)}\n"
        "  api_key: \"env:CONTROL_PLANE_API_KEY\"\n"
        "health:\n"
        "  listen_addr: \"127.0.0.1:0\"\n"
        "admin_ui:\n"
        "  open_browser: false\n"
        "mcp:\n"
        "  commands:\n"
        "    - channel: main\n"
        f"      command: {json.dumps(command)}\n"
    )
    (profile_dir / f"{PROFILE_NAME}.yaml").write_text(profile, encoding="utf-8")


def register_autostart(executable: Path) -> None:
    # Both paths come from this user's installation, not from a shell argument.
    quoted_exe = str(executable).replace("'", "''")
    script = (
        "Import-Module ScheduledTasks -ErrorAction Stop; "
        f"$name = '{TASK_NAME}'; "
        f"$exe = '{quoted_exe}'; "
        "$user = [Security.Principal.WindowsIdentity]::GetCurrent().Name; "
        "$action = New-ScheduledTaskAction -Execute 'powershell.exe' "
        "-Argument ('-NoProfile -WindowStyle Hidden -Command "
        "\"& ''{0}'' run\"' -f $exe); "
        "$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user; "
        "$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited; "
        "$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) "
        "-MultipleInstances IgnoreNew; "
        "if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) { "
        "Stop-ScheduledTask -TaskName $name -ErrorAction Stop }; "
        "Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger "
        "-Principal $principal -Settings $settings -Force -ErrorAction Stop | Out-Null; "
        "Start-ScheduledTask -TaskName $name -ErrorAction Stop"
    )
    powershell(script)


def doctor(key: str) -> None:
    env = os.environ.copy()
    env["CONTROL_PLANE_API_KEY"] = key
    subprocess.run(
        [str(data_dir() / "bin" / "tunnel-client.exe"), "doctor", "--profile", PROFILE_NAME, "--profile-dir", str(data_dir() / "profiles"), "--explain"],
        env=env,
        check=True,
    )


def setup(source: str) -> None:
    if os.name != "nt":
        raise RuntimeError("This release supports Windows only.")
    if not source:
        raise RuntimeError("The package source is not configured; pass --source.")
    print("Choose the project folder that ChatGPT should use by default.")
    project = select_project()
    print("Open OpenAI Platform tunnel settings and create a tunnel for this computer.")
    input("Press Enter to open the Platform page...")
    webbrowser.open("https://platform.openai.com/settings/organization/tunnels")
    tunnel_id = input("Paste this computer's tunnel ID: ").strip()
    if not tunnel_id.startswith("tunnel_"):
        raise RuntimeError("Expected a tunnel ID beginning with 'tunnel_'.")
    print("Create a runtime API key with Tunnels Read + Use access.")
    key = getpass.getpass("Paste the runtime API key (hidden): ").strip()
    if not key:
        raise RuntimeError("A runtime API key is required.")
    print("Installing the local command and dependencies...")
    executable = installed_command(source)
    install_binaries()
    save_config({"project_root": str(project), "tunnel_id": tunnel_id, "source": source})
    save_runtime_key(key)
    write_profile(executable, tunnel_id)
    doctor(key)
    register_autostart(executable)
    print("The local tunnel is configured and running at Windows sign-in.")
    print("In ChatGPT, enable Developer mode, create a plugin using Tunnel, and select this tunnel ID:")
    print(tunnel_id)
    input("Press Enter to open ChatGPT Plugins...")
    webbrowser.open("https://chatgpt.com/plugins")


def run() -> None:
    load_config()
    env = os.environ.copy()
    env["CONTROL_PLANE_API_KEY"] = load_runtime_key()
    result = subprocess.run(
        [str(data_dir() / "bin" / "tunnel-client.exe"), "run", "--profile", PROFILE_NAME, "--profile-dir", str(data_dir() / "profiles")],
        env=env,
    )
    raise SystemExit(result.returncode)


def choose_project() -> None:
    config = load_config()
    project = select_project()
    config["project_root"] = str(project)
    save_config(config)
    powershell(f"Stop-ScheduledTask -TaskName '{TASK_NAME}'; Start-ScheduledTask -TaskName '{TASK_NAME}'")
    print(f"Active project: {project}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="local-project-mcp")
    commands = parser.add_subparsers(dest="command", required=True)
    setup_parser = commands.add_parser("setup", help="configure this Windows computer")
    setup_parser.add_argument("--source", default=DEFAULT_SOURCE, help="GitHub package source")
    commands.add_parser("run", help="run the configured tunnel")
    commands.add_parser("mcp-stdio", help="run the MCP server over stdio")
    commands.add_parser("choose-project", help="select another project folder")
    args = parser.parse_args()
    try:
        if args.command == "setup":
            setup(args.source)
        elif args.command == "run":
            run()
        elif args.command == "mcp-stdio":
            from .server import main as server_main

            server_main()
        elif args.command == "choose-project":
            choose_project()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
