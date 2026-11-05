# Deployment Guide - Joo Optics API

Complete production deployment instructions for the Joo Optics API backend.

## Pre-Deployment Checklist

### Release gates added by the final hardening pass

- [ ] Run `flask db upgrade` against a disposable PostgreSQL database.
- [ ] Confirm `/api/health` returns `200` and `database: ok` through nginx.
- [ ] Configure a scheduler to run
  `python maintenance.py release-expired-reservations` every 5 minutes.
- [ ] Configure private object storage and a tested backup/restore process
  for prescription files; local disk is suitable only for a single-node trial.
- [ ] Test Paymob Sandbox success, decline, duplicate webhook, delayed webhook,
  cancelled-order success, and retry after a failed attempt.
- [ ] Confirm `Idempotency-Key` is preserved across client retries.
- [ ] Confirm Redis, PostgreSQL, TLS, alerting, and log retention are healthy.

### Security Configuration

- [ ] Change `SECRET_KEY` to a secure random value (at least 32 characters)
- [ ] Change `JWT_SECRET_KEY` to a different secure random value
- [ ] Update `JWT_ACCESS_TOKEN_EXPIRES` based on security requirements
- [ ] Ensure `CORS_ORIGINS` is configured with allowed domains only
- [ ] Enable HTTPS/TLS on production server
- [ ] Set up a WAF (Web Application Firewall) if needed

### Database Configuration

- [ ] Migrate from SQLite to PostgreSQL for production
- [ ] Set `DATABASE_URL=postgresql://user:password@host:5432/joo_optics`
- [ ] Create database and user on PostgreSQL
- [ ] Run database migrations: `flask db upgrade`
- [ ] Set up automated backups
- [ ] Test database recovery procedure

### Environment Setup

- [ ] Create `.env` file with all required variables
- [ ] Verify all environment variables are set
- [ ] Do NOT commit `.env` to version control
- [ ] Use environment management service (HashiCorp Vault, AWS Secrets Manager, etc.)

### File Storage

- [ ] Set up cloud storage for prescription uploads (AWS S3, Google Cloud Storage, or Azure Blob)
- [ ] Configure backup for uploaded files
- [ ] Set up CDN if serving files directly
- [ ] Implement file retention/cleanup policies

### Logging & Monitoring

- [ ] Set up centralized logging (ELK Stack, Datadog, Splunk, etc.)
- [ ] Configure application performance monitoring (APM)
- [ ] Set up error tracking (Sentry, Bugsnag, etc.)
- [ ] Configure log rotation and retention policies
- [ ] Set up alerts for critical errors

## Environment Variables for Production

```bash
# Security
SECRET_KEY=<generate-secure-32-char-string>
JWT_SECRET_KEY=<generate-secure-32-char-string>
FLASK_ENV=production

# Database
DATABASE_URL=postgresql://user:password@host:5432/joo_optics
SQLALCHEMY_TRACK_MODIFICATIONS=False

# JWT Configuration
JWT_ACCESS_TOKEN_EXPIRES=900
JWT_REFRESH_TOKEN_EXPIRES=2592000
JWT_ALGORITHM=HS256

# File Upload
PRESCRIPTIONS_UPLOAD_FOLDER=/var/uploads/prescriptions
MAX_CONTENT_LENGTH=5242880
ALLOWED_PRESCRIPTION_EXTENSIONS=png,jpg,jpeg,pdf

# CORS
CORS_ORIGINS=https://yourdomain.com,https://www.yourdomain.com

# Rate Limiting
RATELIMIT_STORAGE_URL=redis://localhost:6379

# Logging
LOG_LEVEL=INFO
LOG_FILE=/var/log/joo-optics/app.log
```

## Docker Deployment

### Dockerfile

Create `Dockerfile` in project root:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create upload and log directories
RUN mkdir -p uploads/prescriptions logs

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:5000/api/health', timeout=5)" || exit 1

# Run with gunicorn
CMD ["gunicorn", "--workers=4", "--timeout=120", "--bind=0.0.0.0:5000", "--access-logfile=-", "--error-logfile=-", "wsgi:app"]
```

### Docker Compose

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: joo_optics
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      POSTGRES_DB: joo_optics
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U joo_optics"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  app:
    build: .
    environment:
      DATABASE_URL: postgresql://joo_optics:${DB_PASSWORD}@db:5432/joo_optics
      RATELIMIT_STORAGE_URL: redis://redis:6379
      SECRET_KEY: ${SECRET_KEY}
      JWT_SECRET_KEY: ${JWT_SECRET_KEY}
      FLASK_ENV: production
    ports:
      - "5000:5000"
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./uploads:/app/uploads
      - ./logs:/app/logs
    command: >
      sh -c "flask db upgrade &&
             gunicorn --workers=4 --timeout=120 --bind=0.0.0.0:5000 --access-logfile=- --error-logfile=- 'wsgi:app'"

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
    depends_on:
      - app

volumes:
  postgres_data:
```

### .env.example

Create `.env.example` for reference:

```bash
# Copy to .env and fill in actual values
SECRET_KEY=your-secret-key-here
JWT_SECRET_KEY=your-jwt-secret-here
DB_PASSWORD=secure-database-password
DATABASE_URL=postgresql://joo_optics:password@db:5432/joo_optics
RATELIMIT_STORAGE_URL=redis://redis:6379
FLASK_ENV=production
```

### Build and Run

```bash
# Create .env from example
cp .env.example .env
# Edit .env with production values

# Build images
docker-compose build

# Start services
docker-compose up -d

# Run migrations
docker-compose exec app flask db upgrade

# View logs
docker-compose logs -f app
```

## Nginx Configuration

Create `nginx.conf`:

```nginx
upstream app {
    server app:5000;
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;
    return 301 https://$server_name$request_uri;
}

# HTTPS server
server {
    listen 443 ssl http2;
    server_name yourdomain.com www.yourdomain.com;

    # SSL certificates (use Let's Encrypt)
    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Compression
    gzip on;
    gzip_min_length 1000;
    gzip_proxied any;
    gzip_types text/plain text/css text/xml text/javascript 
               application/x-javascript application/xml+rss 
               application/json application/javascript;

    # Proxy settings
    location /api {
        proxy_pass http://app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # Static files (if any)
    location /static {
        alias /app/static;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Health check endpoint
    location /health {
        proxy_pass http://app;
        access_log off;
    }
}
```

## SSL/TLS Setup with Let's Encrypt

```bash
# Install Certbot
apt-get install certbot python3-certbot-nginx

# Generate certificate
certbot certonly --standalone -d yourdomain.com -d www.yourdomain.com

# Copy to nginx ssl directory
cp /etc/letsencrypt/live/yourdomain.com/fullchain.pem ./ssl/cert.pem
cp /etc/letsencrypt/live/yourdomain.com/privkey.pem ./ssl/key.pem

# Set up auto-renewal
certbot renew --dry-run
```

## Systemd Service (Alternative to Docker)

Create `/etc/systemd/system/joo-optics.service`:

```ini
[Unit]
Description=Joo Optics API
After=network.target postgresql.service redis.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/joo-optics

Environment="PATH=/opt/joo-optics/.venv/bin"
Environment="DATABASE_URL=postgresql://user:password@localhost/joo_optics"
Environment="FLASK_ENV=production"

ExecStart=/opt/joo-optics/.venv/bin/gunicorn \
    --workers 4 \
    --timeout 120 \
    --bind 127.0.0.1:5000 \
    --access-logfile=/var/log/joo-optics/access.log \
    --error-logfile=/var/log/joo-optics/error.log \
    'wsgi:app'

Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable joo-optics
sudo systemctl start joo-optics
sudo systemctl status joo-optics
```

## Production Checklist

### Application Deployment

- [ ] Run database migrations
- [ ] Collect static files (if any)
- [ ] Run full test suite
- [ ] Verify all environment variables are set
- [ ] Enable production logging
- [ ] Configure rate limiting appropriately
- [ ] Set up error tracking/monitoring

### Server Configuration

- [ ] Configure firewall rules
- [ ] Set up fail2ban for intrusion protection
- [ ] Configure SELinux or AppArmor
- [ ] Set up automatic updates
- [ ] Disable SSH root login
- [ ] Configure SSH key-based authentication

### Database

- [ ] Enable PostgreSQL backups (daily)
- [ ] Test backup restoration
- [ ] Enable connection pooling (PgBouncer)
- [ ] Set up replication for high availability
- [ ] Monitor database size and performance

### Monitoring & Alerting

- [ ] Set up uptime monitoring
- [ ] Configure error rate alerts
- [ ] Set up CPU/memory/disk alerts
- [ ] Configure log aggregation
- [ ] Set up APM dashboard
- [ ] Create runbooks for common issues

## Performance Tuning

### Gunicorn Configuration

For better performance, adjust workers and threads:

```bash
# Calculate optimal workers: (2 x CPU_CORES) + 1
# For 4-core machine: (2 x 4) + 1 = 9 workers

gunicorn \
    --workers 9 \
    --worker-class sync \
    --max-requests 1000 \
    --timeout 120 \
    --bind 0.0.0.0:5000 \
    'wsgi:app'
```

### PostgreSQL Optimization

```sql
-- Analyze query performance
EXPLAIN ANALYZE SELECT * FROM products WHERE category = 'glasses';

-- Create indexes
CREATE INDEX idx_products_category ON products(category);
CREATE INDEX idx_orders_user_id ON orders(user_id);
CREATE INDEX idx_prescriptions_user_id ON prescriptions(user_id);
```

### Redis Configuration

For rate limiting, optimize Redis:

```bash
# In docker-compose or redis config
maxmemory 512mb
maxmemory-policy allkeys-lru
```

## Troubleshooting

### Health Check Endpoint

Add a health check endpoint to your app (recommended):

```python
@app.route('/api/health')
def health():
    return {'status': 'healthy'}, 200
```

### Common Issues

**502 Bad Gateway from Nginx**
```bash
# Check if app is running
docker-compose ps
# Check app logs
docker-compose logs app
# Verify proxy configuration
curl http://localhost:5000/api/health
```

**Database Connection Errors**
```bash
# Test database connection
psql postgresql://user:password@host/dbname
# Check DATABASE_URL format
echo $DATABASE_URL
```

**Out of Memory**
```bash
# Monitor memory usage
docker stats
# Adjust gunicorn workers
# Increase container memory limits
```

## Backup & Recovery

### Database Backup

```bash
# Automatic daily backup
0 2 * * * pg_dump -h localhost -U joo_optics joo_optics | gzip > /backups/db_$(date +\%Y\%m\%d).sql.gz

# Test restoration
gunzip -c /backups/db_20240101.sql.gz | psql -h localhost -U joo_optics joo_optics
```

### File Upload Backup

```bash
# Backup prescription uploads
0 3 * * * tar -czf /backups/uploads_$(date +\%Y\%m\%d).tar.gz /app/uploads/
```

## Scaling Considerations

### Load Balancing

Use load balancer (Nginx, HAProxy) in front of multiple app instances:

```yaml
upstream app {
    least_conn;
    server app1:5000;
    server app2:5000;
    server app3:5000;
}
```

### Database Scaling

- **Read replicas**: Set up PostgreSQL replicas for read-heavy operations
- **Connection pooling**: Use PgBouncer for better connection management
- **Sharding**: Consider sharding if data grows very large

### Caching

- **Redis caching**: Cache frequently accessed data (products, user sessions)
- **CDN**: Distribute static content globally
- **HTTP caching headers**: Set appropriate cache headers on responses

## Security Hardening

### API Security

- Implement rate limiting (already done)
- Use HTTPS exclusively
- Validate and sanitize all inputs
- Implement CSRF protection if needed
- Use security headers

### Data Security

- Encrypt sensitive data at rest
- Encrypt data in transit (TLS)
- Use strong passwords for database
- Implement row-level security if needed
- Regular security audits

### Compliance

- GDPR: Implement data export/deletion endpoints
- PCI-DSS: If processing payments, comply with standards
- Audit logging: Log all sensitive operations
- Data retention: Implement appropriate retention policies

## Support & Maintenance

### Regular Tasks

- Weekly: Monitor logs and alerts
- Weekly: Check database size and performance
- Monthly: Review security logs
- Monthly: Test backup/recovery procedures
- Quarterly: Security assessment
- Quarterly: Performance tuning review

### Updates

- Keep Python dependencies updated
- Apply security patches immediately
- Test updates in staging environment first
- Plan maintenance windows for major updates

## Contact & Escalation

For deployment issues:
1. Check logs: `docker-compose logs app`
2. Verify environment variables
3. Check database connectivity
4. Review monitoring dashboards
