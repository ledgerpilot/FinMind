from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from marshmallow import ValidationError
from datetime import date

from app.extensions import db
from app.models import Transaction, Category, User, Account # Import Account
from app.schemas import TransactionSchema
from app.utils.api import json_abort, json_response

transactions_bp = Blueprint("transactions", __name__, url_prefix="/transactions")


@transactions_bp.route("/", methods=["POST"])
@jwt_required()
def create_transaction():
    """
    Create a new transaction.
    ---
    post:
      summary: Create a transaction
      security:
        - jwt: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                description:
                  type: string
                  description: Description of the transaction
                  example: Groceries
                amount:
                  type: number
                  format: float
                  description: Amount of the transaction
                  example: 50.75
                date:
                  type: string
                  format: date
                  description: Date of the transaction in YYYY-MM-DD format
                  example: 2023-10-26
                type:
                  type: string
                  enum: [INCOME, EXPENSE]
                  description: Type of transaction
                  example: EXPENSE
                category_id:
                  type: integer
                  description: Optional ID of the category
                  example: 1
                account_id:
                  type: integer
                  description: The ID of the account this transaction belongs to.
                  example: 1
                currency:
                  type: string
                  description: ISO 4217 currency code (e.g., 'USD', 'INR')
                  example: USD
      responses:
        201:
          description: Transaction created successfully.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/TransactionSchema'
        400:
          description: Invalid input or account_id missing/invalid.
        401:
          description: Unauthorized.
        404:
          description: Category or Account not found or not owned by user.
    """
    user_id = get_jwt_identity()
    user = User.query.get_or_404(user_id)

    try:
        data = TransactionSchema().load(request.json)
    except ValidationError as err:
        json_abort(400, err.messages)

    category_id = data.get("category_id")
    if category_id:
        category = Category.query.filter_by(id=category_id, user_id=user_id).first()
        if not category:
            json_abort(404, "Category not found or not owned by user.")

    account_id = data.get("account_id")
    if not account_id:
        json_abort(400, "Account ID is required for a transaction.")
    
    account = Account.query.filter_by(id=account_id, user_id=user_id).first()
    if not account:
        json_abort(404, "Account not found or not owned by user.")

    # If currency is not provided, default to the account's currency
    if "currency" not in data or not data["currency"]:
        data["currency"] = account.currency

    new_transaction = Transaction(user_id=user_id, **data)
    db.session.add(new_transaction)
    db.session.commit()
    return json_response(TransactionSchema().dump(new_transaction), 201)


@transactions_bp.route("/", methods=["GET"])
@jwt_required()
def list_transactions():
    """
    List all transactions for the authenticated user.
    ---
    get:
      summary: List user transactions
      security:
        - jwt: []
      parameters:
        - in: query
          name: start_date
          schema:
            type: string
            format: date
          description: Filter transactions from this date (YYYY-MM-DD).
        - in: query
          name: end_date
          schema:
            type: string
            format: date
          description: Filter transactions up to this date (YYYY-MM-DD).
        - in: query
          name: type
          schema:
            type: string
            enum: [INCOME, EXPENSE]
          description: Filter by transaction type.
        - in: query
          name: category_id
          schema:
            type: integer
          description: Filter by category ID.
        - in: query
          name: account_id
          schema:
            type: integer
          description: Optional. ID of the financial account to filter transactions by.
                       If not provided, transactions from all user accounts are returned.
      responses:
        200:
          description: A list of transactions.
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/TransactionSchema'
        400:
          description: Invalid date format or account_id.
        401:
          description: Unauthorized.
    """
    user_id = get_jwt_identity()
    query = Transaction.query.filter_by(user_id=user_id)

    start_date_str = request.args.get("start_date")
    end_date_str = request.args.get("end_date")
    transaction_type = request.args.get("type")
    category_id = request.args.get("category_id", type=int)
    account_id = request.args.get("account_id", type=int)

    try:
        if start_date_str:
            start_date = date.fromisoformat(start_date_str)
            query = query.filter(Transaction.date >= start_date)
        if end_date_str:
            end_date = date.fromisoformat(end_date_str)
            query = query.filter(Transaction.date <= end_date)
    except ValueError:
        json_abort(400, "Invalid date format. Use YYYY-MM-DD.")

    if transaction_type:
        if transaction_type not in ["INCOME", "EXPENSE"]:
            json_abort(400, "Invalid transaction type. Must be 'INCOME' or 'EXPENSE'.")
        query = query.filter_by(type=transaction_type)

    if category_id:
        category = Category.query.filter_by(id=category_id, user_id=user_id).first()
        if not category:
            json_abort(404, "Category not found or not owned by user.")
        query = query.filter_by(category_id=category_id)
    
    if account_id:
        account = Account.query.filter_by(id=account_id, user_id=user_id).first()
        if not account:
            json_abort(404, "Account not found or not owned by user.")
        query = query.filter_by(account_id=account_id)

    transactions = query.order_by(Transaction.date.desc()).all()
    return TransactionSchema(many=True).dump(transactions)


@transactions_bp.route("/<int:transaction_id>", methods=["GET"])
@jwt_required()
def get_transaction(transaction_id):
    """
    Get a specific transaction by ID for the authenticated user.
    ---
    get:
      summary: Get transaction by ID
      security:
        - jwt: []
      parameters:
        - in: path
          name: transaction_id
          schema:
            type: integer
          required: true
          description: ID of the transaction to retrieve
      responses:
        200:
          description: Transaction details.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/TransactionSchema'
        401:
          description: Unauthorized.
        404:
          description: Transaction not found or not owned by the user.
    """
    user_id = get_jwt_identity()
    transaction = Transaction.query.filter_by(id=transaction_id, user_id=user_id).first()
    if not transaction:
        json_abort(404, "Transaction not found or not owned by user.")
    return TransactionSchema().dump(transaction)


@transactions_bp.route("/<int:transaction_id>", methods=["PATCH"])
@jwt_required()
def update_transaction(transaction_id):
    """
    Update a specific transaction by ID for the authenticated user.
    ---
    patch:
      summary: Update a transaction
      security:
        - jwt: []
      parameters:
        - in: path
          name: transaction_id
          schema:
            type: integer
          required: true
          description: ID of the transaction to update
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                description:
                  type: string
                  description: New description
                  example: Updated Groceries
                amount:
                  type: number
                  format: float
                  description: New amount
                  example: 60.00
                date:
                  type: string
                  format: date
                  description: New date in YYYY-MM-DD format
                  example: 2023-11-01
                type:
                  type: string
                  enum: [INCOME, EXPENSE]
                  description: New type
                  example: EXPENSE
                category_id:
                  type: integer
                  description: New optional ID of the category
                  example: 2
                account_id:
                  type: integer
                  description: The ID of the account this transaction belongs to.
                  example: 1
                currency:
                  type: string
                  description: New ISO 4217 currency code (e.g., 'USD', 'INR')
                  example: EUR
      responses:
        200:
          description: Transaction updated successfully.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/TransactionSchema'
        400:
          description: Invalid input or category/account not found/owned by user.
        401:
          description: Unauthorized.
        404:
          description: Transaction not found or not owned by the user.
    """
    user_id = get_jwt_identity()
    transaction = Transaction.query.filter_by(id=transaction_id, user_id=user_id).first()
    if not transaction:
        json_abort(404, "Transaction not found or not owned by user.")

    try:
        data = TransactionSchema(partial=True).load(request.json)
    except ValidationError as err:
        json_abort(400, err.messages)

    if "category_id" in data and data["category_id"] is not None:
        category = Category.query.filter_by(
            id=data["category_id"], user_id=user_id
        ).first()
        if not category:
            json_abort(404, "Category not found or not owned by user.")
    
    if "account_id" in data and data["account_id"] is not None:
        account = Account.query.filter_by(id=data["account_id"], user_id=user_id).first()
        if not account:
            json_abort(404, "Account not found or not owned by user.")

    for key, value in data.items():
        setattr(transaction, key, value)

    db.session.commit()
    return TransactionSchema().dump(transaction)


@transactions_bp.route("/<int:transaction_id>", methods=["DELETE"])
@jwt_required()
def delete_transaction(transaction_id):
    """
    Delete a transaction by ID for the authenticated user.
    ---
    delete:
      summary: Delete a transaction
      security:
        - jwt: []
      parameters:
        - in: path
          name: transaction_id
          schema:
            type: integer
          required: true
          description: ID of the transaction to delete
      responses:
        200:
          description: Transaction deleted successfully.
          content:
            application/json:
              schema:
                type: object
                properties:
                  message:
                    type: string
                    example: Transaction deleted
        401:
          description: Unauthorized.
        404:
          description: Transaction not found or not owned by the user.
    """
    user_id = get_jwt_identity()
    transaction = Transaction.query.filter_by(id=transaction_id, user_id=user_id).first()
    if not transaction:
        json_abort(404, "Transaction not found or not owned by user.")

    db.session.delete(transaction)
    db.session.commit()
    return json_response({"message": "Transaction deleted"})