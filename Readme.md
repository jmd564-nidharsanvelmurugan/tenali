# Tenali-AI-AZ Backend

FastAPI-based backend service for the Jlens AI chatbot platform providing document query, general chat, multi-model support, and workspace management.

**Production URL**: https://jlens4o.jmangroup.tech  
**Status**: Production Ready (83 files)  
**Port**: 8000

## Features

- **General Chat**: Standard conversational AI with Azure OpenAI
- **Document Query**: RAG-based document search with Azure Cognitive Search
- **Multi-Model Support**: GPT-4, GPT-3.5, and custom models
- **Workspace Management**: System, Own, and Shared workspaces
- **Microsoft SSO**: Azure AD authentication + JWT
- **File Upload**: Azure Blob Storage integration
- **Access Control**: Role-based permissions (Admin/User)
- **Analytics**: Usage tracking and monitoring
- **MCP Integration**: Model Context Protocol support

## Architecture

```
Tenali-AI-AZ/
├── auth/                   # JWT + Microsoft SSO
├── core/                   # Database configuration
├── db/                     # SQLAlchemy models
├── alembic/                # Database migrations
├── Jlens/                  # Main application
│   ├── conversations/      # Conversation management
│   ├── messages/           # Message handling & AI
│   ├── workspace/          # Workspace & file management
│   ├── models/             # AI model management
│   ├── user_access/        # Access control
│   ├── analytics/          # Usage tracking
│   ├── mcp_server/         # MCP integration
│   └── lib/                # Utilities
├── AiProposal/             # Proposal generation
├── SelfAnalytics/          # Analytics module
├── seeds/                  # Database seeding scripts
├── scripts/                # Utility scripts
├── config/                 # Configuration files
└── main.py                 # Application entry point
```

## Tech Stack

- **Framework**: FastAPI (Python 3.11+)
- **Database**: PostgreSQL (Neon hosted)
- **ORM**: SQLAlchemy + Alembic
- **Authentication**: JWT + Microsoft SSO (Azure AD)
- **Storage**: Azure Blob Storage
- **Search**: Azure Cognitive Search
- **AI**: Azure OpenAI (GPT-4, GPT-3.5)
- **Deployment**: Docker + Docker Compose

## Prerequisites

- Python 3.11+
- PostgreSQL database
- Azure account with:
  - Blob Storage
  - Cognitive Search
  - OpenAI Service
- Microsoft Azure AD app registration

## Backend Setup

### 1. Clone and Navigate
```bash
git clone <repository-url>
cd Tenali-AI-AZ
```

### 2. Create Virtual Environment
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Environment Configuration
```bash
cp .env.template .env
# Edit .env with your configuration values
```

### 5. Database Setup
```bash
# Run migrations
alembic upgrade head

# Seed initial data (optional)
python seeds/seed.py
python seeds/ai_proposal_seed.py
```

### 6. Initialize Services
```bash
# Initialize workspace system
python scripts/init_user_workspace_system.py

# Grant default access (optional)
python scripts/grant_default_access.py
```

### 7. Start Development Server
```bash
python main.py
```

### 8. Verify Installation
- API Documentation: http://localhost:8000/docs
- Health Check: http://localhost:8000/health
- Backend should be running on port 8000

## Configuration

### Environment Variables (.env)

```env
# Environment
ENVIRONMENT=development
ENABLE_DOCS=true

# Database
DATABASE_URL=postgresql://user:password@host:port/database
SQLALCHEMY_DATABASE_URL=postgresql://user:password@host:port/database

# JWT
JWT_SECRET_KEY=your-jwt-secret-key
ACCESS_TOKEN_EXPIRE_MINUTES=15
ALGORITHM=HS256

# Microsoft SSO
MICROSOFT_CLIENT_ID=your-client-id
MICROSOFT_CLIENT_SECRET=your-client-secret
MICROSOFT_TENANT_ID=your-tenant-id
MICROSOFT_REDIRECT_URI=http://localhost:8000/api/auth/microsoft/callback
FRONTEND_URL=http://localhost:3000

# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://your-openai.openai.azure.com/
AZURE_OPENAI_KEY=your-openai-key
AZURE_OPENAI_DEPLOYMENT_MODEL_1=gpt-4
AZURE_OPENAI_DEPLOYMENT_MODEL_NAME_1=gpt-4

# Azure Blob Storage
AZURE_BLOB_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;...
AZURE_BLOB_STORAGE_CONTAINER_NAME=your-container

# Azure Search
AZURE_SEARCH_SERVICE=your-search-service
AZURE_SEARCH_KEY=your-search-key
AZURE_SEARCH_SERVICE_INDEXER_WORKSPACE_NAME=workspaces
```

### Azure Services Setup

1. **Azure Blob Storage**: Create container for document storage
2. **Azure Cognitive Search**: Create search service with indexes:
   - `workspaces` - for workspace documents
   - `ai-proposal-workspace-index` - for AI proposals
3. **Azure OpenAI**: Deploy GPT models
4. **Azure AD**: Register app for SSO authentication

## Database Schema

### Core Tables

- **users** - User accounts (email, name, role)
- **conversations** - Chat conversations with title
- **messages** - Chat messages (user/assistant)
- **workspaces** - Document workspaces (system/own/shared)
- **workspace_files** - Uploaded files metadata
- **workspace_folders** - Folder organization
- **workspace_shares** - Workspace sharing records
- **workspace_access** - Access control (view/edit/admin)
- **models** - AI model configurations
- **user_model_access** - User-model permissions
- **analytics** - Usage tracking

### Workspace Types

- **system** - Pre-configured templates (color: #19105B)
- **own** - User-created workspaces (color: #A16BDB)
- **shared** - Shared with other users (color: #FF6196)

### Migrations

```bash
# Create migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Check current version
alembic current

# Rollback
alembic downgrade -1
```

## Authentication

### JWT Authentication
- Standard email/password login
- JWT tokens with configurable expiration

### Microsoft SSO
- Azure AD integration
- Automatic user creation/login
- Token-based session management

## API Endpoints

### Authentication
- `POST /api/auth/login` - Email/password login
- `POST /api/auth/microsoft-login` - Microsoft SSO
- `POST /api/auth/signup` - User registration
- `GET /api/auth/user-exists` - Check user existence

### Conversations
- `GET /api/conversations/` - List user conversations
- `POST /api/conversations/` - Create conversation
- `GET /api/conversations/{id}` - Get conversation details
- `DELETE /api/conversations/{id}` - Delete conversation
- `GET /api/conversations/{id}/messages` - Get messages

### Messages
- `POST /api/messages/` - Send message (streaming response)

### Workspaces
- `GET /api/workspaces/` - List workspaces (system/own/shared)
- `POST /api/workspaces/` - Create workspace
- `POST /api/workspaces/upload-file/` - Upload document
- `GET /api/workspaces/{id}/files/` - List files
- `POST /api/workspaces/{id}/share` - Share workspace
- `GET /api/workspaces/{id}/folders/` - List folders

### Models
- `GET /api/models/` - List all models
- `GET /api/models/user-models` - User's accessible models

### Analytics
- `GET /api/analytics/usage` - Usage statistics

### Health
- `GET /health` - Health check
- `GET /docs` - Swagger UI
- `GET /redoc` - ReDoc UI

## Deployment

### Production Setup

1. **Install dependencies**
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configure environment**
   ```bash
   # Edit .env with production values
   nano .env
   ```

3. **Run migrations**
   ```bash
   alembic upgrade head
   ```

4. **Start server**
   ```bash
   python main.py
   ```

### Docker Deployment

```bash
# Build image
docker build -t jlens-backend:latest .

# Run container
docker run -d -p 8000:8000 --env-file .env jlens-backend:latest
```

### Docker Compose

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

## Testing

```bash
# Run tests
pytest

# Run with coverage
pytest --cov=.

# Run specific test file
pytest tests/test_auth.py
```

## Monitoring

### Health Check
- `GET /docs` - API documentation
- `GET /health` - Health status

### Logging
- Structured logging with timestamps
- Error tracking and monitoring
- Performance metrics

## Development

### Code Style
```bash
# Format code
black .

# Lint code
flake8 .

# Type checking
mypy .
```

### Pre-commit Hooks
```bash
pre-commit install
pre-commit run --all-files
```

## Troubleshooting

### Common Issues

1. **Database Connection Error**
   - Check DATABASE_URL format
   - Verify database is running
   - Check network connectivity

2. **Azure Service Errors**
   - Verify Azure credentials
   - Check service endpoints
   - Validate API keys

3. **Migration Issues**
   - Check database permissions
   - Verify migration files
   - Run `alembic current` to check status

### Debug Mode
```bash
# Run with debug logging
PYTHONPATH=. python main.py --log-level debug
```

## Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support and questions:
- Create an issue in the repository
- Contact the development team
- Check the documentation at `/docs`
