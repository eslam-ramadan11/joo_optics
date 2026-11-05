# Joo Optics API - Production-Ready Backend

A professional, production-ready optical store backend API built with Flask. Fully secure, scalable, and following clean architecture principles.

## Features

- ✅ **User Authentication**: JWT-based auth with secure password hashing (bcrypt)
- ✅ **Role-Based Access Control**: Admin and user roles with decorator-based authorization
- ✅ **Product Management**: Full CRUD with pagination, search, sorting, and category filtering
- ✅ **Prescription Management**: Secure file uploads with validation and access controls
- ✅ **Order Management**: Automatic stock validation, total calculation, and stock management
- ✅ **Payment Processing**: Unique transaction IDs, payment status tracking
- ✅ **Rate Limiting**: Flask-Limiter for API protection against abuse
- ✅ **Comprehensive Logging**: Rotating file logging to `logs/app.log`
- ✅ **Database Migrations**: Flask-Migrate for schema versioning
- ✅ **CORS Support**: Enabled for cross-origin requests
- ✅ **Complete API Documentation**: Swagger/OpenAPI specification
- ✅ **Unit & Integration Tests**: Comprehensive test coverage
- ✅ **Type Hints**: Full type annotations across codebase
- ✅ **Docstrings**: Complete documentation for all functions

## Project Structure

```
app/
├── __init__.py                 # App factory and initialization
├── extensions.py               # Flask extensions setup
├── models/
│   ├── __init__.py
│   └── models.py              # All SQLAlchemy models
├── routes/
│   ├── auth.py                # Authentication endpoints
│   ├── products.py            # Product CRUD endpoints
│   ├── prescriptions.py       # Prescription upload endpoints
│   ├── orders.py              # Order management endpoints
│   ├── payments.py            # Payment processing endpoints
│   ├── docs.py                # API documentation serving
│   └── __init__.py
├── services/
│   ├── auth_service.py        # Authentication business logic
│   ├── product_service.py     # Product operations
│   ├── prescription_service.py # Prescription file handling
│   ├── order_service.py       # Order processing
│   ├── payment_service.py     # Payment operations
│   └── __init__.py
├── schemas/
│   ├── product_schema.py      # Product validation schemas
│   ├── prescription_schema.py # Prescription schemas
│   ├── order_schema.py        # Order validation schemas
│   ├── payment_schema.py      # Payment schemas
│   ├── user_schema.py         # User schemas
│   └── __init__.py
├── middleware/
│   ├── auth.py                # JWT decorators (login_required, admin_required)
│   ├── error_handlers.py      # Global error handling
│   └── __init__.py
├── utils/
│   ├── response.py            # Standardized API response helper
│   ├── exceptions.py          # Custom exceptions
│   ├── limiter.py             # Rate limiting config
│   └── __init__.py
├── logs/
│   └── app.log                # Application logs (rotating)
└── uploads/
    └── prescriptions/         # Prescription image storage

config.py                       # Configuration management
.env                           # Environment variables
requirements.txt               # Python dependencies
openapi.json                   # OpenAPI/Swagger specification
migrations/                    # Database migrations (Alembic)
tests/
├── test_products.py          # Product tests
├── test_prescriptions.py      # Prescription upload tests
├── test_orders.py            # Order tests
└── test_integration.py       # Full integration tests
```

## Installation & Setup

### 1. Clone and Create Virtual Environment

```bash
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
# macOS/Linux
source .venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment

Edit `.env` with your settings:

```env
SECRET_KEY=your-secret-key-change-in-production
JWT_SECRET_KEY=your-jwt-secret-key
DATABASE_URL=sqlite:///site.db
JWT_ACCESS_TOKEN_EXPIRES=900
JWT_REFRESH_TOKEN_EXPIRES=2592000
PRESCRIPTIONS_UPLOAD_FOLDER=uploads/prescriptions
MAX_CONTENT_LENGTH=5242880
ALLOWED_PRESCRIPTION_EXTENSIONS=png,jpg,jpeg,pdf
```

### 4. Initialize Database

```bash
flask db init
flask db migrate -m "Initial migration"
flask db upgrade
```

### 5. Run Development Server

```bash
python app.py
```

Server will be available at `http://localhost:5000`

## API Endpoints

### Authentication

- `POST /api/auth/register` - Register new user
- `POST /api/auth/login` - Login user
- `POST /api/auth/refresh` - Refresh access token
- `POST /api/auth/change-password` - Change password (requires JWT)

### Products

- `GET /api/products` - List products (with pagination, search, filtering)
- `GET /api/products/<id>` - Get product by ID
- `POST /api/products` - Create product (admin only)
- `PUT /api/products/<id>` - Update product (admin only)
- `DELETE /api/products/<id>` - Delete product (admin only)

### Prescriptions

- `POST /api/prescriptions` - Upload prescription (requires JWT)
- `GET /api/prescriptions` - List user's prescriptions (requires JWT)
- `GET /api/prescriptions/<id>` - Get prescription (requires JWT)
- `DELETE /api/prescriptions/<id>` - Delete prescription (requires JWT)

### Orders

- `POST /api/orders` - Create order (requires JWT)
- `GET /api/orders` - List orders (requires JWT)
- `GET /api/orders/<id>` - Get order details (requires JWT)
- `PUT /api/orders/<id>` - Update order status (admin only)
- `DELETE /api/orders/<id>` - Delete order (admin only)

### Payments

- `POST /api/payments` - Create payment (requires JWT)
- `GET /api/payments/<id>` - Get payment (requires JWT)
- `PUT /api/payments/<id>` - Update payment status (admin only)

## API Response Format

All endpoints return standardized JSON:

```json
{
  "success": true,
  "data": {},
  "message": "Optional message"
}
```

## Authentication

Use JWT Bearer token in Authorization header:

```
Authorization: Bearer <access_token>
```

## Rate Limiting

API endpoints are rate limited to prevent abuse:

- Auth: 5-10 requests per minute
- Products: 100 requests per minute
- Orders: 20 requests per minute
- Payments: 10 requests per minute
- Prescriptions: 30 requests per minute

## Testing

Run the test suite:

```bash
pytest -q
```

With coverage:

```bash
pytest --cov=app tests/
```

## Security Features

- ✅ **Password Hashing**: Bcrypt with salt rounds
- ✅ **JWT Token Management**: Separate access and refresh tokens
- ✅ **File Upload Validation**: Extension, size, and MIME type checks
- ✅ **SQL Injection Protection**: SQLAlchemy ORM prevents injection
- ✅ **CORS Protection**: Configurable cross-origin requests
- ✅ **Rate Limiting**: Prevents brute force and DoS attacks
- ✅ **Input Validation**: Marshmallow schemas validate all inputs
- ✅ **Admin Authorization**: Decorator-based access control
- ✅ **Logging**: All errors and important events logged

## Database Schema

### Users Table
- id (Primary Key)
- username (Unique, Indexed)
- email (Unique, Indexed)
- password_hash (Hashed)
- is_admin (Boolean)
- created_at (Timestamp)

### Products Table
- id (Primary Key)
- name
- price
- old_price (Optional)
- category
- image_file
- discount_badge (Optional)
- colors
- stock_quantity

### Prescriptions Table
- id (Primary Key)
- user_id (Foreign Key → Users)
- image_file (Path to uploaded file)
- sph_r, cyl_r, axis_r (Right eye prescription)
- sph_l, cyl_l, axis_l (Left eye prescription)
- uploaded_at (Timestamp)

### Orders Table
- id (Primary Key)
- user_id (Foreign Key → Users)
- address_id (Foreign Key → ShippingAddresses)
- status (pending, processing, shipped, delivered, cancelled)
- total_amount
- date_posted (Timestamp)

### OrderItems Table
- id (Primary Key)
- order_id (Foreign Key → Orders)
- product_id (Foreign Key → Products)
- prescription_id (Foreign Key → Prescriptions)
- lens_type
- quantity
- item_price

### Payments Table
- id (Primary Key)
- order_id (Foreign Key → Orders, Unique)
- amount
- payment_method (credit_card, paypal, bank_transfer, cash)
- payment_status (pending, completed, failed, cancelled)
- transaction_id (Unique, UUID format)
- payment_date (Timestamp)

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| SECRET_KEY | change-me-in-production | Flask secret key |
| JWT_SECRET_KEY | SECRET_KEY | JWT signing key |
| DATABASE_URL | sqlite:///site.db | Database URL |
| JWT_ACCESS_TOKEN_EXPIRES | 900 | Access token lifetime (seconds) |
| JWT_REFRESH_TOKEN_EXPIRES | 2592000 | Refresh token lifetime (seconds) |
| PRESCRIPTIONS_UPLOAD_FOLDER | uploads/prescriptions | File upload directory |
| MAX_CONTENT_LENGTH | 5242880 | Max upload size (5MB) |
| ALLOWED_PRESCRIPTION_EXTENSIONS | png,jpg,jpeg,pdf | Allowed file types |

## Production Deployment

### Before Deploying

1. Change SECRET_KEY and JWT_SECRET_KEY to secure random values
2. Use a production database (PostgreSQL recommended)
3. Set up proper CORS origins
4. Enable HTTPS
5. Configure proper logging and monitoring
6. Set up database backups
7. Configure environment variables securely

### Recommended Stack

- **Server**: Gunicorn or Waitress
- **Database**: PostgreSQL with regular backups
- **Reverse Proxy**: Nginx with SSL
- **Monitoring**: Application Performance Monitoring (APM)
- **Logging**: Centralized log aggregation (ELK, Datadog, etc.)
- **Storage**: Cloud storage for prescription files (AWS S3, GCS)

### Example Gunicorn Command

```bash
gunicorn --workers 4 --timeout 120 --bind 0.0.0.0:5000 'wsgi:app'
```

## Logging

All application logs are written to `logs/app.log` with rotation:

- Max file size: 5MB
- Backup count: 3 files
- Format: `%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]`

## API Documentation

### OpenAPI/Swagger Spec

Access the OpenAPI specification at `/api/openapi.json`

### Endpoint Details

See `openapi.json` for complete API documentation with:
- Request/response schemas
- Parameter descriptions
- Authentication requirements
- Error codes
- Examples

## Contributing

When adding new endpoints:

1. Add proper type hints and docstrings
2. Include input validation using schemas
3. Apply rate limiting decorators
4. Add proper error handling
5. Document in OpenAPI spec
6. Write unit tests
7. Update this README if needed

## Error Handling

The API returns consistent error responses:

```json
{
  "success": false,
  "data": {},
  "message": "Error description"
}
```

HTTP Status Codes:
- 200: OK
- 201: Created
- 400: Bad Request (validation error)
- 401: Unauthorized (missing/invalid JWT)
- 403: Forbidden (insufficient permissions)
- 404: Not Found
- 409: Conflict (duplicate username/email)
- 413: Payload Too Large
- 422: Unprocessable Entity (JWT decode error)
- 429: Too Many Requests (rate limit exceeded)
- 500: Internal Server Error

## License

MIT License

## Support

For issues or questions, please create an issue in the repository.
