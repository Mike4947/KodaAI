# KodaAI — Gemma 4 GitHub Codebase Analyzer

Analyze GitHub repositories locally using Gemma 4 via Ollama. Finds bugs, security issues, and code quality problems using a Cursor-style agentic scan that explores files incrementally instead of dumping the entire repo into context.

## Prerequisites

1. **Python 3.11+**
2. **Node.js 18+**
3. **Git** on PATH
4. **Ollama 0.22+** — [ollama.com](https://ollama.com)
5. **Gemma 4 model** — pull at least one:
   ```bash
   ollama pull gemma4:e4b
   ```
6. **(Recommended)** Create a 32K context variant:
   ```bash
   ollama create koda-gemma4 -f Modelfile
   ```

### GitHub OAuth (private repos only)

1. Go to [GitHub Developer Settings](https://github.com/settings/developers) → OAuth Apps → New
2. Set **Authorization callback URL** to `http://localhost:8000/api/github/callback`
3. Copy Client ID and Client Secret into `.env`

Generate a Fernet key for token encryption:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Quick start

```bat
copy .env.example .env
pip install -e .
npm install
npm install --prefix frontend
ollama pull gemma4:e4b
start.bat
```

Opens http://localhost:5173 in your browser.

## Usage

1. **Select a model** — the app scans Ollama for Gemma 4 models on load. If none are found, follow the setup instructions shown.
2. **Add a repository** — paste a public GitHub URL, or connect GitHub to pick a private repo.
3. **Configure system prompt** — use the Prompts page to edit what the model looks for (bugs, security, etc.).
4. **Start scan** — watch live activity and findings stream in. Export the final report as Markdown.

## Architecture

- **Backend:** FastAPI on port 8000
- **Frontend:** React + Vite on port 5173
- **LLM:** Ollama with tool-calling agent loop
- **Storage:** SQLite for prompts and scan history

The agent uses tools (`list_directory`, `read_file`, `search_files`, `report_finding`, `finish_scan`) to explore the codebase efficiently without exceeding context limits.

## Environment variables

| Variable | Description |
|----------|-------------|
| `GITHUB_CLIENT_ID` | OAuth app client ID |
| `GITHUB_CLIENT_SECRET` | OAuth app secret |
| `FERNET_KEY` | Encryption key for stored tokens |
| `OLLAMA_BASE_URL` | Default: `http://localhost:11434` |
| `OLLAMA_NUM_CTX` | Context window override (default: 32768) |

## License

Apache 2.0
