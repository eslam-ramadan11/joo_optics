from flask import jsonify


def api_response(success: bool, data=None, message=None, status_code=200):
    # BUG FIX: `data or {}` silently replaced any falsy-but-valid payload
    # (an empty list `[]`, `0`, `''`) with `{}`. That broke every endpoint
    # that legitimately returns an empty list - e.g. a user with zero
    # shipping addresses got `data: {}` instead of `data: []`, and the
    # frontend's `addresses.map(...)` then crashed with
    # "addresses.map is not a function" because `{}` isn't an array.
    payload = {'success': success, 'data': data if data is not None else {}}
    if message:
        payload['message'] = message
    return jsonify(payload), status_code
