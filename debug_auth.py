from pathlib import Path
from app import create_app
from app.extensions import db
from app.models.models import User
from flask_jwt_extended import create_access_token

class TestConfig:
    TESTING = True
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{Path('debug_auth.sqlite').resolve()}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SECRET_KEY = 'test-secret'
    JWT_SECRET_KEY = 'test-jwt-secret'

app = create_app(TestConfig)
with app.app_context():
    db.drop_all()
    db.create_all()
    user = User(username='c', email='c@example.com', password_hash='hash', is_admin=False)
    db.session.add(user)
    db.session.commit()
    print('user_id', user.id)
    print('user_count', User.query.count())
    token = create_access_token(identity=str(user.id), additional_claims={'is_admin': False})
    print('token', token)
    with app.test_client() as client:
        resp = client.get('/api/user/profile', headers={'Authorization': f'Bearer {token}'})
        print('status', resp.status_code)
        print(resp.get_data(as_text=True))
