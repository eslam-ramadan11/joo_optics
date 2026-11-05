# Contributing to Joo Optics API

Thank you for your interest in contributing! This document outlines our development standards and contribution process.

## Code Standards

### Type Hints

All Python code must include type hints. This improves code clarity and enables better IDE support.

```python
# ✅ Good
def create_product(data: Dict[str, Any]) -> Product:
    """Create a new product."""
    product = Product(**data)
    db.session.add(product)
    db.session.commit()
    return product

# ❌ Bad
def create_product(data):
    product = Product(**data)
    db.session.add(product)
    db.session.commit()
    return product
```

### Docstrings

All functions, classes, and modules must have docstrings using Google style format.

```python
# ✅ Good
def authenticate_user(username: str, password: str) -> Optional[User]:
    """Authenticate user with username and password.
    
    Args:
        username: The user's username.
        password: The user's plaintext password.
    
    Returns:
        User object if authentication successful, None otherwise.
    
    Raises:
        ValueError: If username is empty.
    """
    if not username:
        raise ValueError("Username cannot be empty")
    user = User.query.filter_by(username=username).first()
    if user and bcrypt.check_password_hash(user.password_hash, password):
        return user
    return None

# ❌ Bad
def authenticate_user(username, password):
    # Check if user exists and password matches
    user = User.query.filter_by(username=username).first()
    if user and bcrypt.check_password_hash(user.password_hash, password):
        return user
    return None
```

### Naming Conventions

- **Classes**: PascalCase (e.g., `UserService`, `ProductSchema`)
- **Functions/Methods**: snake_case (e.g., `create_product`, `validate_input`)
- **Constants**: UPPER_SNAKE_CASE (e.g., `MAX_UPLOAD_SIZE`, `ALLOWED_EXTENSIONS`)
- **Private methods**: Prefix with underscore (e.g., `_validate_password`)

### Error Handling

Always use specific exceptions and proper error messages.

```python
# ✅ Good
if not product:
    raise ValueError(f"Product {product_id} not found")

# ❌ Bad
if not product:
    return None  # Unclear what happened
```

## Architecture & Design Patterns

### Service Layer Pattern

Always use service layer for business logic, never put it in route handlers.

```python
# ✅ Good - routes/products.py
@products_bp.route('/products', methods=['POST'])
@login_required
def create_product() -> Tuple[dict, int]:
    data = request.get_json()
    schema = ProductSchema()
    errors = schema.validate(data)
    if errors:
        return api_response(False, {}, str(errors)), 400
    
    product = ProductService.create_product(data)
    return api_response(True, {'product': product.to_dict()}), 201

# ❌ Bad - Business logic in route handler
@products_bp.route('/products', methods=['POST'])
@login_required
def create_product():
    data = request.get_json()
    product = Product(**data)  # Business logic in route
    db.session.add(product)
    db.session.commit()
    return {'product': product.to_dict()}, 201
```

### Schema Validation

Always validate input using Marshmallow schemas.

```python
# ✅ Good
class ProductSchema(Schema):
    name = fields.String(required=True, validate=Length(min=1, max=255))
    price = fields.Float(required=True, validate=Range(min=0))
    category = fields.String(required=True, validate=Length(min=1))

schema = ProductSchema()
errors = schema.validate(request.get_json())
if errors:
    return api_response(False, {}, str(errors)), 400

# ❌ Bad - Manual validation
data = request.get_json()
if not data.get('name'):
    return {'error': 'Name required'}, 400
if data.get('price', 0) < 0:
    return {'error': 'Price must be positive'}, 400
```

## File Organization

```
app/
├── routes/
│   ├── __init__.py           # Blueprint registration
│   ├── auth.py               # Authentication endpoints
│   ├── products.py           # Product endpoints
│   └── orders.py             # Order endpoints
├── services/
│   ├── __init__.py
│   ├── product_service.py    # Product business logic
│   ├── order_service.py      # Order business logic
│   └── auth_service.py       # Auth business logic
├── schemas/
│   ├── __init__.py
│   ├── product_schema.py     # Product validation
│   └── order_schema.py       # Order validation
├── models/
│   ├── __init__.py
│   └── models.py             # SQLAlchemy models
└── middleware/
    ├── __init__.py
    ├── auth.py               # JWT decorators
    └── error_handlers.py     # Error handling
```

## Testing

### Test Structure

```python
# ✅ Good - tests/test_products.py
import pytest
from app import create_app
from app.models.models import Product

@pytest.fixture
def app():
    """Create app for testing."""
    app = create_app()
    app.config['TESTING'] = True
    app.config['DATABASE_URL'] = 'sqlite:///:memory:'
    return app

def test_create_product(client, auth_headers):
    """Test product creation."""
    response = client.post(
        '/api/products',
        json={
            'name': 'Test Product',
            'price': 99.99,
            'category': 'glasses'
        },
        headers=auth_headers
    )
    assert response.status_code == 201
    assert response.json['success'] is True

def test_create_product_missing_name(client, auth_headers):
    """Test product creation fails with missing name."""
    response = client.post(
        '/api/products',
        json={
            'price': 99.99,
            'category': 'glasses'
        },
        headers=auth_headers
    )
    assert response.status_code == 400
```

### Running Tests

```bash
# Run all tests
pytest -q

# Run specific test file
pytest tests/test_products.py -v

# Run with coverage
pytest --cov=app tests/ --cov-report=html

# Run with markers
pytest -m "not slow"
```

## Creating New Endpoints

### Step 1: Define Schema (if needed)

```python
# app/schemas/my_schema.py
from marshmallow import Schema, fields, validate

class MyResourceSchema(Schema):
    """Schema for my resource."""
    id = fields.Integer(dump_only=True)
    name = fields.String(required=True, validate=Length(min=1, max=255))
    description = fields.String()
```

### Step 2: Create Service Methods

```python
# app/services/my_service.py
class MyService:
    """Service for my resource operations."""
    
    @staticmethod
    def create_resource(data: Dict[str, Any]) -> MyModel:
        """Create a new resource.
        
        Args:
            data: Resource data.
        
        Returns:
            Created resource object.
        """
        resource = MyModel(**data)
        db.session.add(resource)
        db.session.commit()
        return resource
```

### Step 3: Implement Routes

```python
# app/routes/my_routes.py
from flask import Blueprint, request
from app.middleware.auth import login_required
from app.utils.response import api_response
from app.services.my_service import MyService
from app.schemas.my_schema import MyResourceSchema
from app.utils.limiter import limiter

my_bp = Blueprint('my', __name__, url_prefix='/api')

@my_bp.route('/resources', methods=['POST'])
@limiter.limit('10 per minute')
@login_required
def create_resource() -> Tuple[dict, int]:
    """Create a new resource.
    
    Returns:
        201: Resource created successfully.
        400: Validation error.
    """
    schema = MyResourceSchema()
    errors = schema.validate(request.get_json())
    if errors:
        return api_response(False, {}, str(errors)), 400
    
    try:
        resource = MyService.create_resource(request.get_json())
        return api_response(True, {'resource': resource.to_dict()}), 201
    except Exception as e:
        return api_response(False, {}, str(e)), 500
```

### Step 4: Register Blueprint

```python
# app/__init__.py
from app.routes import my_routes

def create_app(config_class=None):
    app = Flask(__name__)
    # ... other setup ...
    app.register_blueprint(my_routes.my_bp)
    return app
```

### Step 5: Update OpenAPI Spec

Add endpoint documentation to `openapi.json`:

```json
{
  "paths": {
    "/api/resources": {
      "post": {
        "tags": ["Resources"],
        "summary": "Create a new resource",
        "security": [{"BearerAuth": []}],
        "requestBody": {
          "required": true,
          "content": {
            "application/json": {
              "schema": {"$ref": "#/components/schemas/MyResource"}
            }
          }
        },
        "responses": {
          "201": {"description": "Resource created"},
          "400": {"description": "Validation error"}
        }
      }
    }
  }
}
```

### Step 6: Add Tests

```python
# tests/test_my_resource.py
def test_create_resource(client, auth_headers):
    """Test creating a resource."""
    response = client.post(
        '/api/resources',
        json={'name': 'My Resource', 'description': 'Test'},
        headers=auth_headers
    )
    assert response.status_code == 201
    assert response.json['success'] is True
```

## Security Guidelines

### Never:
- ❌ Store passwords in plaintext
- ❌ Return sensitive data in error messages
- ❌ Trust user input without validation
- ❌ Commit secrets to version control
- ❌ Use `eval()` or `exec()` on user input
- ❌ Return database errors directly to clients

### Always:
- ✅ Use parameterized queries (SQLAlchemy ORM does this)
- ✅ Hash passwords with bcrypt
- ✅ Validate and sanitize all inputs
- ✅ Use HTTPS in production
- ✅ Implement rate limiting
- ✅ Use strong JWT secrets
- ✅ Log security events
- ✅ Keep dependencies updated

## Performance Considerations

### Database Queries

```python
# ✅ Good - Use eager loading for related data
products = Product.query.options(
    joinedload(Product.category)
).all()

# ❌ Bad - N+1 query problem
products = Product.query.all()
for product in products:
    print(product.category.name)  # Query executed for each product
```

### Caching

```python
# ✅ Good - Cache frequently accessed data
from flask import cache

@cache.cached(timeout=300)
def get_categories():
    return db.session.query(Category).all()

# ❌ Bad - No caching for expensive operations
def get_categories():
    return db.session.query(Category).all()
```

## Commit Message Guidelines

Use clear, descriptive commit messages:

```
# ✅ Good
feat: add payment processing endpoint
- Implement POST /api/payments
- Generate unique transaction IDs
- Add comprehensive error handling

# ❌ Bad
fix bug
update stuff
changes
```

## Pull Request Process

1. Create feature branch: `git checkout -b feature/description`
2. Make changes following code standards
3. Add tests for new functionality
4. Run test suite: `pytest --cov=app tests/`
5. Update documentation
6. Push to branch: `git push origin feature/description`
7. Create Pull Request with clear description
8. Address review comments
9. Merge once approved

## Questions?

- Check existing code for examples
- Review the API documentation in `README.md`
- Check `DEPLOYMENT.md` for deployment questions
- Review type hints and docstrings in existing code

Thank you for contributing!
