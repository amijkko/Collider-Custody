# Collider Custody - Transaction Security Layer + Wallet-as-a-Service

Enterprise-grade on-prem custody solution for Ethereum with complete transaction lifecycle management.

## Features

- **Wallet Registry (WaaS)**: Create and manage Ethereum wallets with role-based access
- **Transaction Orchestrator**: State machine workflow for transaction lifecycle
- **KYT (Know Your Transaction)**: Screen transactions against blacklists/graylists
- **Policy Engine**: Enforce limits, denylists, and approval requirements
- **Approvals with SoD**: Multi-approval workflows with Segregation of Duties
- **Signing Adapter**: Dev mode signer (HSM/MPC interface ready)
- **Chain Listener**: Monitor confirmations and detect inbound deposits
- **Audit Log**: Tamper-evident hash-chain audit trail with verification

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           REST API (FastAPI)                            │
├─────────────────────────────────────────────────────────────────────────┤
│  Wallets  │  TxRequests  │  Approvals  │  Cases  │  Policies  │  Audit │
├─────────────────────────────────────────────────────────────────────────┤
│                        Transaction Orchestrator                          │
│   SUBMITTED → KYT → POLICY → APPROVALS → SIGN → BROADCAST → CONFIRM    │
├────────────┬────────────┬────────────┬────────────┬─────────────────────┤
│  KYT Mock  │  Policy    │  Approval  │  Signing   │  Ethereum Service   │
│  Service   │  Engine    │  Service   │  Adapter   │  (RPC + Nonce Mgmt) │
├────────────┴────────────┴────────────┴────────────┴─────────────────────┤
│                     Chain Listener (Background)                          │
│              Confirmations Tracking + Inbound Detection                  │
├─────────────────────────────────────────────────────────────────────────┤
│                         Audit Service (Hash Chain)                       │
├─────────────────────────────────────────────────────────────────────────┤
│                         PostgreSQL Database                              │
└─────────────────────────────────────────────────────────────────────────┘
```

## Transaction State Machine

```
SUBMITTED
    ↓
KYT_PENDING → KYT_BLOCKED (terminal)
    ↓
    ├→ KYT_REVIEW (wait for case resolution) → KYT_BLOCKED or continue
    ↓
POLICY_EVAL_PENDING → POLICY_BLOCKED (terminal)
    ↓
APPROVAL_PENDING (if required) → REJECTED (terminal)
    ↓
SIGN_PENDING → FAILED_SIGN (terminal)
    ↓
SIGNED
    ↓
BROADCAST_PENDING → FAILED_BROADCAST (can retry)
    ↓
BROADCASTED
    ↓
CONFIRMING
    ↓
CONFIRMED
    ↓
FINALIZED (terminal success)
```

## Quick Start

### Prerequisites

- Docker & Docker Compose
- (Optional) Python 3.11+ for local development

### Run with Docker

```bash
# Clone and start
cd Collider-custody
docker-compose up -d

# View logs
docker-compose logs -f app

# API available at http://localhost:8000
# OpenAPI docs at http://localhost:8000/docs
```

### Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Start PostgreSQL
docker-compose up -d postgres

# Run migrations
alembic upgrade head

# Start the app
uvicorn app.main:app --reload
```

## Configuration

Environment variables (see `env.example`):

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string (async) | `postgresql+asyncpg://...` |
| `DATABASE_URL_SYNC` | PostgreSQL connection string (sync) | `postgresql://...` |
| `ETH_RPC_URL` | Ethereum RPC endpoint | Sepolia public RPC |
| `DEV_SIGNER_PRIVATE_KEY` | Dev mode signing key | Anvil default key |
| `JWT_SECRET` | JWT signing secret | Dev secret |
| `CONFIRMATION_BLOCKS` | Required confirmations | `3` |
| `KYT_BLACKLIST` | Comma-separated blacklisted addresses | - |
| `KYT_GRAYLIST` | Comma-separated graylisted addresses | - |

## API Usage

See [examples/curl_examples.sh](examples/curl_examples.sh) for complete examples.

### Authentication

```bash
# Register user
curl -X POST http://localhost:8000/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "email": "admin@example.com", "password": "securepass123", "role": "ADMIN"}'

# Login
curl -X POST http://localhost:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "securepass123"}'
```

### Create Wallet

```bash
curl -X POST http://localhost:8000/v1/wallets \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: wallet-001" \
  -d '{"wallet_type": "TREASURY", "subject_id": "org-123", "risk_profile": "HIGH"}'
```

### Create Transaction Request

```bash
curl -X POST http://localhost:8000/v1/tx-requests \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: tx-001" \
  -d '{
    "wallet_id": "WALLET_ID",
    "tx_type": "TRANSFER",
    "to_address": "0x742d35Cc6634C0532925a3b844Bc9e7595f2bD20",
    "asset": "ETH",
    "amount": "0.1"
  }'
```

### Approve Transaction

```bash
curl -X POST http://localhost:8000/v1/tx-requests/{tx_id}/approve \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"decision": "APPROVED", "comment": "Reviewed and approved"}'
```

### Get Audit Package

```bash
curl http://localhost:8000/v1/audit/packages/{tx_id} \
  -H "Authorization: Bearer $TOKEN"
```

### Verify Audit Chain

```bash
curl http://localhost:8000/v1/audit/verify \
  -H "Authorization: Bearer $TOKEN"
```

## Testing

```bash
# Install test dependencies
pip install -r requirements.txt

# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=app --cov-report=html
```

## Security Considerations

- **Never store private keys in audit logs** - only key references
- **JWT tokens** should use strong secrets in production
- **CORS** should be configured for specific origins in production
- **RPC endpoints** should be authenticated/rate-limited
- **Database** should use connection encryption (SSL)

## API Documentation

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

## Project Structure

```
Collider-custody/
├── app/
│   ├── api/              # REST endpoints
│   ├── models/           # SQLAlchemy models
│   ├── schemas/          # Pydantic schemas
│   ├── services/         # Business logic
│   ├── config.py         # Configuration
│   ├── database.py       # Database setup
│   └── main.py           # FastAPI app
├── migrations/           # Alembic migrations
├── tests/                # Test suite
├── examples/             # Usage examples
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

## License

MIT

