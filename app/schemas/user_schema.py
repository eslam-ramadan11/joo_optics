def validate_registration_payload(data: dict):
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    if not username or not email or not password:
        return False, 'username, email and password are required'
    return True, None
