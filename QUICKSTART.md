# Quick Start Guide - Joo Optics API

Get the Joo Optics API backend running in minutes.

## 5-Minute Setup (Development)

### 1. Clone & Install

```bash
# Navigate to project directory
cd "e:\joo optics by vs"

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
# Copy environment template
copy .env.example .env
# or on macOS/Linux:
cp .env.example .env

# Edit .env - for development, defaults are usually fine
```

### 3. Initialize Database

```bash
# Inside project directory with .venv activated
flask db init
flask db migrate -m "Initial migration"
flask db upgrade
```

### 4. Run Server

```bash
# Development mode
python app.py

# Server runs at http://localhost:5000
```

### 5. Test It Works

```bash
# In another terminal, test registration
curl -X POST http://localhost:5000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","email":"test@example.com","password":"password123"}'

# Response should be:
# {"success": true, "data": {...}, "message": "User registered successfully"}
```

## Using the API

### Get Access Token

```bash
# Login
curl -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","password":"password123"}'

# Save the access_token from response
```

### Use Token in Requests

```bash
# List products (no auth required)
curl http://localhost:5000/api/products

# Get user's orders (requires auth)
curl http://localhost:5000/api/orders \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

## Running Tests

```bash
# Run all tests
pytest -q

# Run with verbose output
pytest -v

# Run with coverage
pytest --cov=app tests/

# Run specific test file
pytest tests/test_integration.py -v

# Run tests matching pattern
pytest -k "test_create" -v
```

## Useful Flask Commands

```bash
# Create admin user
flask shell
>>> from app.services.auth_service import AuthService
>>> from app.extensions import db
>>> user = AuthService.register_user('admin', 'admin@example.com', 'admin123')
>>> user.is_admin = True
>>> db.session.add(user)
>>> db.session.commit()
>>> exit()

# Database operations
flask db current      # Show current migration
flask db heads        # Show available heads
flask db downgrade    # Rollback one migration

# Run tests directly
flask test
```

## API Documentation

### Swagger UI (Development)

If swagger-ui is configured, visit:
```
http://localhost:5000/api-docs
```

### OpenAPI Specification

Download the OpenAPI spec at:
```
http://localhost:5000/api/openapi.json
```

Or view the file:
```bash
cat openapi.json
```

## Common Tasks

### Add a Product

```bash
TOKEN="your_access_token_here"

curl -X POST http://localhost:5000/api/products \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Reading Glasses",
    "price": 49.99,
    "category": "glasses",
    "image_file": "reading-glasses.jpg",
    "colors": "black,brown",
    "stock_quantity": 100
  }'
```

### Create an Order

```bash
# First, list products to get ID
curl http://localhost:5000/api/products

# Create order (replace IDs and token)
TOKEN="your_access_token"
curl -X POST http://localhost:5000/api/orders \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "address_id": 1,
    "items": [
      {
        "product_id": 1,
        "prescription_id": 1,
        "quantity": 1,
        "item_price": 49.99
      }
    ]
  }'
```

### Upload Prescription

```bash
TOKEN="your_access_token"

curl -X POST http://localhost:5000/api/prescriptions \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@prescription.jpg" \
  -F "sph_r=-1.0" \
  -F "cyl_r=-0.5" \
  -F "axis_r=90" \
  -F "sph_l=-1.5" \
  -F "cyl_l=-0.5" \
  -F "axis_l=180"
```

## Troubleshooting

### Issue: `ModuleNotFoundError: No module named 'flask'`

```bash
# Ensure virtual environment is activated
.\.venv\Scripts\Activate.ps1  # Windows
source .venv/bin/activate     # macOS/Linux

# Reinstall dependencies
pip install -r requirements.txt
```

### Issue: Database locked or migration failed

```bash
# Remove existing database and start fresh
rm site.db
flask db upgrade
```

### Issue: CORS errors in browser

Check `.env` file CORS_ORIGINS setting:
```bash
# .env
CORS_ORIGINS=http://localhost:3000,http://localhost:8080
```

### Issue: JWT token invalid or expired

Tokens have expiration times:
```bash
# .env
JWT_ACCESS_TOKEN_EXPIRES=900  # 15 minutes
```

Use the refresh endpoint to get a new token:
```bash
curl -X POST http://localhost:5000/api/auth/refresh \
  -H "Authorization: Bearer YOUR_REFRESH_TOKEN"
```

## Project Structure

```
app/
├── routes/          # API endpoints
├── services/        # Business logic
├── schemas/         # Input validation
├── models/          # Database models
├── middleware/      # Auth, error handling
└── utils/           # Helpers, response format

tests/               # Test files
config.py            # Configuration
requirements.txt     # Dependencies
```

## Documentation Files

- **README.md** - Complete project documentation
- **DEPLOYMENT.md** - Production deployment guide
- **CONTRIBUTING.md** - Development guidelines
- **PRODUCTION_CHECKLIST.md** - Production readiness verification
- **openapi.json** - API specification

## Next Steps

1. Read [README.md](README.md) for comprehensive documentation
2. Check [DEPLOYMENT.md](DEPLOYMENT.md) for production setup
3. Review [CONTRIBUTING.md](CONTRIBUTING.md) before adding code
4. See [PRODUCTION_CHECKLIST.md](PRODUCTION_CHECKLIST.md) for verification

## Support

- Check existing tests in `tests/` for examples
- Review service layer code for patterns
- See route files for endpoint implementation
- Check docstrings for function details

## Development Workflow

```bash
# 1. Create feature branch
git checkout -b feature/my-feature

# 2. Make changes with type hints and docstrings

# 3. Run tests
pytest

# 4. Check code quality
# No specific tool configured yet, but follow CONTRIBUTING.md guidelines

# 5. Commit
git add .
git commit -m "feat: add my feature"

# 6. Push and create pull request
git push origin feature/my-feature
```

## Performance Tips

### Pagination

Always use pagination for large datasets:
```bash
curl "http://localhost:5000/api/products?page=1&per_page=20"
```

### Search & Filter

Use search to reduce data:
```bash
# Search products
curl "http://localhost:5000/api/products?search=glasses"

# Filter by category
curl "http://localhost:5000/api/products?category=sunglasses"

# Combine search, filter, sort
curl "http://localhost:5000/api/products?search=ray&category=sunglasses&sort_by=price&sort_dir=asc"
```

### Database Queries

- Use `page=1&per_page=20` to avoid loading everything
- The API automatically handles pagination
- Sorting is done on server side, not client side

## Rate Limiting

API endpoints are rate-limited to prevent abuse:

```bash
# Try to exceed rate limit (10 attempts in 1 minute)
for i in {1..15}; do
  curl http://localhost:5000/api/products
  echo ""
done

# After 10 requests, you'll get: 429 Too Many Requests
```

Limits by endpoint:
- Auth: 5-10 per minute
- Products: 100 per minute
- Orders: 20 per minute
- Payments: 10 per minute
- Prescriptions: 30 per minute

## Database Options

### Development (SQLite)
```bash
# Default - works out of box
DATABASE_URL=sqlite:///site.db
```

### Production (PostgreSQL)
```bash
# In .env
DATABASE_URL=postgresql://user:password@localhost:5432/joo_optics

# Install PostgreSQL driver
pip install psycopg2-binary
```

## Environment Variables

Key variables in `.env`:

```bash
SECRET_KEY=change-me-in-production
JWT_SECRET_KEY=change-me-in-production
DATABASE_URL=sqlite:///site.db
JWT_ACCESS_TOKEN_EXPIRES=900
CORS_ORIGINS=http://localhost:3000
```

See `.env.example` for complete list.

## Summary

You now have a fully functional Joo Optics API running locally!

**Next: Read [README.md](README.md) for complete documentation**
