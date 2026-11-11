# codium

VSCodium in your browser, on Termux. One command starts a VS Code web IDE from a
proot-distro container on your phone, served on `http://127.0.0.1:8080`, with a
fuzzy project picker rooted at `~/The Projects`.

## How it fits together

```
Termux shell
└─ codium (termux/codium)          proot-distro wrapper
   └─ proot login codium-ubuntu    dedicated session, --kill-on-exit safe
      ├─ lib/serve                 foreground server runner (proot's main command)
      └─ bin/codium                launcher: picker, start/stop/status/logs
         └─ OpenVSCode Server      /opt/openvscode-server, VSCodium-branded
            └─ your browser        http://127.0.0.1:8080
```

Why the dedicated proot session: proot runs with `--kill-on-exit` and traces
every process inside it, so a server started from your interactive proot shell
dies the moment that shell exits. The Termux wrapper gives the server its own
proot session whose foreground command is the server itself, so it keeps
running while your shell (and the rest of the session) goes away.

The server is upstream [gitpod-io/openvscode-server](https://github.com/gitpod-io/openvscode-server)
(MIT), rebranded to VSCodium at install time via `product.json` edits plus a
runtime patch to `server-main.js` that the launcher re-applies on every start.

## Install

Inside the proot distro (Ubuntu assumed, run as root):

```sh
apt update && apt install -y git python3 curl
git clone https://github.com/WatashiAD/vscode-in-termux ~/codium
bash ~/codium/install.sh
```

On the Termux side (outside proot):

```sh
cp ~/codium/termux/codium $PREFIX/bin/codium
chmod +x $PREFIX/bin/codium
```

Requirements on the Termux side:

```sh
pkg install proot-distro
proot-distro install ubuntu
```

The wrapper prefers a distro aliased `codium-ubuntu` and falls back to `ubuntu`.

## Usage

Run `codium` from Termux (or from inside proot, where it warns that the server
dies with your session).

```text
codium                  pick a project (type to search, Enter to open/create)
codium <name>           open ~/The Projects/<name>, creating it if missing
codium <path>           open any folder
codium .                open the current directory

codium list             list projects
codium status           show server status
codium stop             stop the server
codium restart          restart the server
codium logs             tail the server log
```

## Configuration

Everything is driven by environment variables, with the same defaults the
scripts were written against:

| Variable | Default | Purpose |
|---|---|---|
| `CODIUM_PROJECTS_DIR` | `~/The Projects` | Root of the project picker |
| `CODIUM_SERVER_HOME` | `/opt/openvscode-server` | Where the server lives |
| `CODIUM_HOST` | `127.0.0.1` | Server bind address |
| `CODIUM_PORT` | `8080` | Server port |
| `CODIUM_RUN_DIR` | `~/.codium-run` | pidfiles and logs |
| `CODIUM_PREFIX` | `/usr/local` | Install prefix (install.sh only) |
| `CODIUM_SERVER_VERSION` | `1.109.5` | Upstream release to download (install.sh only) |

## License

MIT. Not affiliated with or endorsed by the VSCodium or Visual Studio Code
projects; the branding is applied locally for personal preference.
