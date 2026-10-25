# Autonomous AI Task Worker

## Setup

Requirements: Python 3.10 or newer and Git.

Clone the repository, install Python dependencies, and install the Playwright Chromium browser:

```bash
git clone https://github.com/Asmitha-6364/AI-Worker.git
cd AI-Worker
python -m pip install -r requirements.txt
python -m playwright install chromium
```

The project runs with its deterministic planner by default and does not require an API key. To use an LLM, create a `.env` file in the project root and configure either OpenAI or Gemini:

```dotenv
LLM_PROVIDER=auto
OPENAI_API_KEY=your-openai-api-key
OPENAI_MODEL=gpt-4o
```

Or configure Gemini instead:

```dotenv
LLM_PROVIDER=auto
GEMINI_API_KEY=your-gemini-api-key
GEMINI_MODEL=gemini-1.5-pro
```

Do not commit `.env` or API keys. The application uses OpenAI when both provider keys are configured.

## Run

Run a demo task:

```bash
python run.py --demo standard
python run.py --demo recovery
python run.py --demo clarification
```

Run a custom task:

```bash
python run.py "Find the latest invoice from Apex Technologies and record it in AcmeOps."
```

Start the AcmeOps web application on its own:

```bash
python run.py --server
```

Then open http://127.0.0.1:8000. The local demo credentials are `admin` / `acmepass123`.

Run the test suite:

```bash
python -m pytest tests/
```

Re-seed the sample database and invoice documents:

```bash
python run.py --seed
```
