FROM python:3.12-slim

WORKDIR /app

# Install system dependencies (curl + gnupg for Node.js installation)
RUN apt-get update && apt-get install -y curl gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .

RUN pip install --upgrade pip

RUN pip install --no-cache-dir -r requirements.txt

# Install modelcontextprotocol/server-postgres globally via npm
RUN npm install -g @modelcontextprotocol/server-postgres

# Copy backend source code
COPY . .

# Expose FastAPI port
EXPOSE 8000

CMD ["bash", "-c", "echo 'Starting application...' && echo 'Running database migrations...' && alembic upgrade head && echo 'Migrations completed!' && python scripts/init_user_workspace_system.py && python seed.py && (python -c 'from core.database import SessionLocal; from db.models import ProposalQuestions; db=SessionLocal(); count=db.query(ProposalQuestions).count(); db.close(); exit(0 if count > 0 else 1)' || python ai_proposal_seed.py) && echo 'Starting FastAPI server...' && uvicorn main:app --host 0.0.0.0 --port 8000"]
