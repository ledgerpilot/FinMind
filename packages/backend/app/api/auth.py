from flask import Blueprint, request
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_jwt_identity,
    get_jwt,
    current_user,
)
from marshmallow import ValidationError
from sqlalchemy.exc import IntegrityError
from datetime import timedelta

from app.extensions import db, jwt
from app.models import User, Account # Import Account
from app.schemas import RegisterSchema, LoginSchema, UserSchema, UpdateUserSchema, AccountSchema # Import AccountSchema
from app.utils.api import json_abort, json_response
from app.utils.auth import hash_password, verify_password, add_token_to_blocklist    if existing_user:
        json_abort(409, "User with this email already exists.")

    hashed_password = hash_password(data["password"])
    new_user = User(email=data["email"], password_hash=hashed_password)
    db.session.add(new_user)
    db.session.flush() # Flush to get new_user.id before committing

    # Create a default primary account for the new user
    default_account = Account(
        name="Main Account",
        user_id=new_user.id,
        currency=new_user.preferred_currency, # Use user's preferred currency
        is_primary=True
    )
    db.session.add(default_account)
    db.session.commit()

    return json_response(UserSchema().dump(new_user), 201)    """
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        json_abort(404, "User not found")

    try:
        data = UpdateUserSchema().load(request.json, partial=True)
    except ValidationError as err:
        json_abort(400, err.messages)

    if "preferred_currency" in data:
        user.preferred_currency = data["preferred_currency"].upper()

    db.session.commit()
    # The UserSchema now includes accounts, which need to be dumped.
    # We must ensure the user object has its relationships loaded.
    db.session.refresh(user)
    return UserSchema().dump(user)