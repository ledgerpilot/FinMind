from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from marshmallow import ValidationError
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import Account, User
from app.schemas import AccountSchema
from app.utils.api import json_abort, json_response

accounts_bp = Blueprint("accounts", __name__, url_prefix="/accounts")


@accounts_bp.route("/", methods=["GET"])
@jwt_required()
def list_accounts():
    """
    List all financial accounts for the authenticated user.
    ---
    get:
      summary: List user accounts
      security:
        - jwt: []
      responses:
        200:
          description: A list of financial accounts.
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/AccountSchema'
        401:
          description: Unauthorized.
    """
    user_id = get_jwt_identity()
    accounts = Account.query.filter_by(user_id=user_id).order_by(Account.name).all()
    return AccountSchema(many=True).dump(accounts)


@accounts_bp.route("/", methods=["POST"])
@jwt_required()
def create_account():
    """
    Create a new financial account for the authenticated user.
    ---
    post:
      summary: Create an account
      security:
        - jwt: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                name:
                  type: string
                  description: Name of the account
                  example: My Savings
                currency:
                  type: string
                  description: ISO 4217 currency code (e.g., 'USD', 'INR')
                  example: USD
      responses:
        201:
          description: Account created successfully.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/AccountSchema'
        400:
          description: Invalid input or missing required fields.
        401:
          description: Unauthorized.
        409:
          description: An account with this name already exists for the user.
    """
    user_id = get_jwt_identity()
    user = User.query.get(user_id)
    if not user:
        json_abort(404, "User not found")

    try:
        data = AccountSchema(partial=True).load(request.json)  # Use partial to allow 'name' and 'currency' only
    except ValidationError as err:
        json_abort(400, err.messages)

    name = data.get("name")
    currency = data.get("currency")

    if not name or not currency:
        json_abort(400, "Account name and currency are required.")

    # Check if this is the first account for the user, if so, make it primary
    is_primary = Account.query.filter_by(user_id=user_id).count() == 0

    new_account = Account(
        name=name,
        user_id=user_id,
        currency=currency,
        is_primary=is_primary
    )

    try:
        db.session.add(new_account)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        json_abort(409, "An account with this name already exists, or primary account constraint violated.")
    except Exception as e:
        db.session.rollback()
        json_abort(500, f"Failed to create account: {str(e)}")

    return json_response(AccountSchema().dump(new_account), 201)


@accounts_bp.route("/<int:account_id>", methods=["GET"])
@jwt_required()
def get_account(account_id):
    """
    Get a specific financial account by ID for the authenticated user.
    ---
    get:
      summary: Get account by ID
      security:
        - jwt: []
      parameters:
        - in: path
          name: account_id
          schema:
            type: integer
          required: true
          description: ID of the account to retrieve
      responses:
        200:
          description: Account details.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/AccountSchema'
        401:
          description: Unauthorized.
        404:
          description: Account not found or not owned by the user.
    """
    user_id = get_jwt_identity()
    account = Account.query.filter_by(id=account_id, user_id=user_id).first()
    if not account:
        json_abort(404, "Account not found or not owned by user.")
    return AccountSchema().dump(account)


@accounts_bp.route("/<int:account_id>", methods=["PATCH"])
@jwt_required()
def update_account(account_id):
    """
    Update a specific financial account by ID for the authenticated user.
    Allows changing name, currency, and setting as primary.
    ---
    patch:
      summary: Update an account
      security:
        - jwt: []
      parameters:
        - in: path
          name: account_id
          schema:
            type: integer
          required: true
          description: ID of the account to update
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                name:
                  type: string
                  description: New name for the account
                  example: My Checking
                currency:
                  type: string
                  description: New ISO 4217 currency code
                  example: EUR
                is_primary:
                  type: boolean
                  description: Set this account as the user's primary account
                  example: true
      responses:
        200:
          description: Account updated successfully.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/AccountSchema'
        400:
          description: Invalid input.
        401:
          description: Unauthorized.
        404:
          description: Account not found or not owned by the user.
        409:
          description: An account with this name already exists, or primary account constraint violated.
    """
    user_id = get_jwt_identity()
    account = Account.query.filter_by(id=account_id, user_id=user_id).first()
    if not account:
        json_abort(404, "Account not found or not owned by user.")

    try:
        data = AccountSchema(partial=True).load(request.json)
    except ValidationError as err:
        json_abort(400, err.messages)

    new_name = data.get("name")
    new_currency = data.get("currency")
    set_primary = data.get("is_primary")

    if new_name:
        account.name = new_name
    if new_currency:
        account.currency = new_currency
    
    if set_primary is not None:
        if set_primary and not account.is_primary: # if we want to make it primary and it's not already
            # Unset current primary account for this user
            current_primary = Account.query.filter_by(user_id=user_id, is_primary=True).first()
            if current_primary and current_primary.id != account.id:
                current_primary.is_primary = False
                db.session.add(current_primary)
            account.is_primary = True
        elif not set_primary and account.is_primary: # if we want to unset it, but it's currently primary
            # A user must always have one primary account.
            # If this is the only account, it cannot be unset as primary.
            if Account.query.filter_by(user_id=user_id).count() == 1:
                json_abort(400, "Cannot unset the only primary account. A user must always have one primary account.")
            # If there are other accounts, we could randomly pick another one to become primary,
            # or require the client to specify a new primary, or fail and let the client explicitly
            # set a new one. Let's fail for now to enforce explicit primary setting.
            json_abort(400, "Cannot unset a primary account. Please set another account as primary first.")

    try:
        db.session.add(account)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        json_abort(409, "An account with this name already exists for the user, or primary account constraint violated.")
    except Exception as e:
        db.session.rollback()
        json_abort(500, f"Failed to update account: {str(e)}")

    return AccountSchema().dump(account)


@accounts_bp.route("/<int:account_id>", methods=["DELETE"])
@jwt_required()
def delete_account(account_id):
    """
    Delete a financial account by ID for the authenticated user.
    ---
    delete:
      summary: Delete an account
      security:
        - jwt: []
      parameters:
        - in: path
          name: account_id
          schema:
            type: integer
          required: true
          description: ID of the account to delete
      responses:
        200:
          description: Account deleted successfully.
          content:
            application/json:
              schema:
                type: object
                properties:
                  message:
                    type: string
                    example: Account deleted
        400:
          description: Cannot delete primary account if it's the only one.
        401:
          description: Unauthorized.
        404:
          description: Account not found or not owned by the user.
    """
    user_id = get_jwt_identity()
    account = Account.query.filter_by(id=account_id, user_id=user_id).first()
    if not account:
        json_abort(404, "Account not found or not owned by user.")
    
    # Prevent deleting the last primary account
    if account.is_primary:
        remaining_accounts = Account.query.filter_by(user_id=user_id).count()
        if remaining_accounts == 1:
            json_abort(400, "Cannot delete the only primary account. A user must always have one primary account.")
        # If there are other accounts, we need to make another one primary before deleting this one.
        # This design choice prefers explicit action from the client.
        json_abort(400, "Cannot delete a primary account. Please set another account as primary first.")


    try:
        db.session.delete(account)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        json_abort(500, f"Failed to delete account: {str(e)}")

    return json_response({"message": "Account deleted"})

