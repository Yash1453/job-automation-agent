# Job Automation Agent

An open-source Windows-compatible autonomous job automation agent that scrapes job boards, scores listings with a local Ollama LLM, and auto-applies to high-match roles.

## Features

- Multi-source job scraping: LinkedIn, Wellfound, AngelList, HackerNews, RemoteOK, Stack Overflow, Indeed
- Resume-based LLM scoring with local Ollama
- SQLite deduplication and application tracking
- Telegram notifications for applications and daily summaries
- Windows batch runner and scheduler-friendly flow
- Configurable via `.env` and `config/resume_context.txt`

## Quick Start

### 1. Clone or copy this repository

```cmd
cd C:\Users\Yash\Downloads\files
```

### 2. Create and activate a Python virtual environment

```cmd
python -m venv .venv
.venv\Scripts\activate.bat
```

### 3. Install dependencies

```cmd
pip install -r requirements.txt
```

### 4. Create required directories

```cmd
mkdir config
mkdir logs
mkdir data
```

### 5. Configure your resume context

Copy `config_resume_context.txt` into `config/resume_context.txt` and update it with your experience, skills, and target roles.

### 6. Configure environment secrets

Copy `env_template` to `.env` and fill in your values:

```cmd
copy env_template .env
```

Update `.env` with:

```env
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama2
```

### 7. Start Ollama

In a separate terminal:

```cmd
ollama serve
ollama pull llama2
```

### 8. Run the bot

```cmd
python job_agent_complete.py full
```

## Usage

- `python job_agent_complete.py scrape` — scrape job sources
- `python job_agent_complete.py score` — score pending jobs
- `python job_agent_complete.py apply` — apply to high-scoring jobs
- `python job_agent_complete.py full` — run the full pipeline

## Recommended Files

- `job_agent_complete.py` — main orchestrator
- `scrapers.py` — scraper implementations
- `form_automation.py` — browser automation helper
- `config_resume_context.txt` — resume prompt template
- `env_template` — environment variable template
- `run_agent.bat` — Windows batch runner

## Notes

- This project is intended for educational and personal use.
- Scraping or automating applications may violate job board terms of service.
- Always verify the target site's usage policy before automating.
- Keep `.env` private and do not commit it to Git.

## Publishing and Sharing

To share this project:

1. Create a GitHub repository
2. Add this repository’s files
3. Publish with a permissive license (MIT is included)
4. Share setup instructions and disclaimers

## License

This project is licensed under the MIT License.
