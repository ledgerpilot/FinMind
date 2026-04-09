from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from marshmallow import ValidationError
from datetime import date, timedelta
import calendar # Import calendar for month-end calculations

from app.extensions import db
from app.models import Bill, User, Account
from app.schemas import BillSchema
from app.utils.api import json_abort, json_response

bills_bp = Blueprint("bills", __name__, url_prefix="/bills")


@bills_bp.route("/", methods=["POST"])
@jwt_required()
def create_bill():
    """
    Create a new bill.
    ---
    post:
      summary: Create a bill
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
                  description: Name of the bill
                  example: Internet
                amount:
                  type: number
                  format: float
                  description: Amount of the bill
                  example: 59.99
                account_id:
                  type: integer
                  description: The ID of the account this bill belongs to.
                  example: 1
                currency:
                  type: string
                  description: ISO 4217 currency code (e.g., 'USD', 'INR')
                  example: USD
                next_due_date:
                  type: string
                  format: date
                  description: Next due date in YYYY-MM-DD format
                  example: 2024-03-20
                cadence:
                  type: string
                  enum: [DAILY, WEEKLY, MONTHLY, YEARLY]
                  description: How often the bill recurs
                  example: MONTHLY
                channel_email:
                  type: boolean
                  description: Whether to send email reminders
                  example: true
                channel_whatsapp:
                  type: boolean
                  description: Whether to send WhatsApp reminders
                  example: false
                autopay_enabled:
                  type: boolean
                  description: Whether autopay is enabled
                  example: false
      responses:
        201:
          description: Bill created successfully.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/BillSchema'
        400:
          description: Invalid input or account_id missing/invalid.
        401:
          description: Unauthorized.
        404:
          description: Account not found or not owned by user.
    """
    user_id = get_jwt_identity()
    user = User.query.get_or_404(user_id)

    try:
        data = BillSchema().load(request.json)
    except ValidationError as err:
        json_abort(400, err.messages)

    account_id = data.get("account_id")
    if not account_id:
        json_abort(400, "Account ID is required for a bill.")
    
    account = Account.query.filter_by(id=account_id, user_id=user_id).first()
    if not account:
        json_abort(404, "Account not found or not owned by user.")

    # If currency is not provided, default to the account's currency
    if "currency" not in data or not data["currency"]:
        data["currency"] = account.currency

    new_bill = Bill(user_id=user_id, **data)
    db.session.add(new_bill)
    db.session.commit()
    return json_response(BillSchema().dump(new_bill), 201)


@bills_bp.route("/", methods=["GET"])
@jwt_required()
def list_bills():
    """
    List all bills for the authenticated user.
    ---
    get:
      summary: List user bills
      security:
        - jwt: []
      parameters:
        - in: query
          name: account_id
          schema:
            type: integer
          description: Optional. ID of the financial account to filter bills by.
                       If not provided, bills from all user accounts are returned.
      responses:
        200:
          description: A list of bills.
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/BillSchema'
        401:
          description: Unauthorized.
    """
    user_id = get_jwt_identity()
    query = Bill.query.filter_by(user_id=user_id)

    account_id = request.args.get("account_id", type=int)
    if account_id:
        account = Account.query.filter_by(id=account_id, user_id=user_id).first()
        if not account:
            json_abort(404, "Account not found or not owned by user.")
        query = query.filter_by(account_id=account_id)

    bills = query.order_by(Bill.next_due_date).all()
    return BillSchema(many=True).dump(bills)


@bills_bp.route("/<int:bill_id>", methods=["GET"])
@jwt_required()
def get_bill(bill_id):
    """
    Get a specific bill by ID for the authenticated user.
    ---
    get:
      summary: Get bill by ID
      security:
        - jwt: []
      parameters:
        - in: path
          name: bill_id
          schema:
            type: integer
          required: true
          description: ID of the bill to retrieve
      responses:
        200:
          description: Bill details.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/BillSchema'
        401:
          description: Unauthorized.
        404:
          description: Bill not found or not owned by the user.
    """
    user_id = get_jwt_identity()
    bill = Bill.query.filter_by(id=bill_id, user_id=user_id).first()
    if not bill:
        json_abort(404, "Bill not found or not owned by user.")
    return BillSchema().dump(bill)


@bills_bp.route("/<int:bill_id>", methods=["PATCH"])
@jwt_required()
def update_bill(bill_id):
    """
    Update a specific bill by ID for the authenticated user.
    ---
    patch:
      summary: Update a bill
      security:
        - jwt: []
      parameters:
        - in: path
          name: bill_id
          schema:
            type: integer
          required: true
          description: ID of the bill to update
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                name:
                  type: string
                  description: Name of the bill
                  example: Updated Internet Bill
                amount:
                  type: number
                  format: float
                  description: New amount
                  example: 65.00
                account_id:
                  type: integer
                  description: The ID of the account this bill belongs to.
                  example: 1
                currency:
                  type: string
                  description: ISO 4217 currency code (e.g., 'USD', 'INR')
                  example: EUR
                next_due_date:
                  type: string
                  format: date
                  description: New next due date in YYYY-MM-DD format
                  example: 2024-04-20
                cadence:
                  type: string
                  enum: [DAILY, WEEKLY, MONTHLY, YEARLY]
                  description: New cadence
                  example: MONTHLY
                channel_email:
                  type: boolean
                  description: Whether to send email reminders
                  example: false
                channel_whatsapp:
                  type: boolean
                  description: Whether to send WhatsApp reminders
                  example: true
                autopay_enabled:
                  type: boolean
                  description: Whether autopay is enabled
                  example: true
      responses:
        200:
          description: Bill updated successfully.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/BillSchema'
        400:
          description: Invalid input or account_id not owned by user.
        401:
          description: Unauthorized.
        404:
          description: Bill not found or not owned by the user.
    """
    user_id = get_jwt_identity()
    bill = Bill.query.filter_by(id=bill_id, user_id=user_id).first()
    if not bill:
        json_abort(404, "Bill not found or not owned by user.")

    try:
        data = BillSchema(partial=True).load(request.json)
    except ValidationError as err:
        json_abort(400, err.messages)

    if "account_id" in data:
        account = Account.query.filter_by(id=data["account_id"], user_id=user_id).first()
        if not account:
            json_abort(400, "Account not found or not owned by user.")

    for key, value in data.items():
        setattr(bill, key, value)

    db.session.commit()
    return BillSchema().dump(bill)


@bills_bp.route("/<int:bill_id>", methods=["DELETE"])
@jwt_required()
def delete_bill(bill_id):
    """
    Delete a bill by ID for the authenticated user.
    ---
    delete:
      summary: Delete a bill
      security:
        - jwt: []
      parameters:
        - in: path
          name: bill_id
          schema:
            type: integer
          required: true
          description: ID of the bill to delete
      responses:
        200:
          description: Bill deleted successfully.
          content:
            application/json:
              schema:
                type: object
                properties:
                  message:
                    type: string
                    example: Bill deleted
        401:
          description: Unauthorized.
        404:
          description: Bill not found or not owned by the user.
    """
    user_id = get_jwt_identity()
    bill = Bill.query.filter_by(id=bill_id, user_id=user_id).first()
    if not bill:
        json_abort(404, "Bill not found or not owned by user.")

    db.session.delete(bill)
    db.session.commit()
    return json_response({"message": "Bill deleted"})


@bills_bp.route("/<int:bill_id>/pay", methods=["POST"])
@jwt_required()
def mark_bill_paid(bill_id):
    """
    Marks a bill as paid and updates its next due date based on its cadence.
    ---
    post:
      summary: Mark bill as paid
      security:
        - jwt: []
      parameters:
        - in: path
          name: bill_id
          schema:
            type: integer
          required: true
          description: ID of the bill to mark as paid
      responses:
        200:
          description: Bill marked as paid and next due date updated.
          content:
            application/json:
              schema:
                type: object
                properties:
                  message:
                    type: string
                    example: updated
        401:
          description: Unauthorized.
        404:
          description: Bill not found or not owned by the user.
    """
    user_id = get_jwt_identity()
    bill = Bill.query.filter_by(id=bill_id, user_id=user_id).first()
    if not bill:
        json_abort(404, "Bill not found or not owned by user.")

    # Update next_due_date based on cadence
    current_date = bill.next_due_date
    if bill.cadence == "DAILY":
        bill.next_due_date = current_date + timedelta(days=1)
    elif bill.cadence == "WEEKLY":
        bill.next_due_date = current_date + timedelta(weeks=1)
    elif bill.cadence == "MONTHLY":
        # Advance by one month, handle month end correctly
        next_month = current_date.month % 12 + 1
        next_year = current_date.year + (current_date.month // 12)
        day = min(current_date.day, calendar.monthrange(next_year, next_month)[1])
        bill.next_due_date = date(next_year, next_month, day)
    elif bill.cadence == "YEARLY":
        bill.next_due_date = date(current_date.year + 1, current_date.month, current_date.day)
    else:
        json_abort(400, "Unknown bill cadence.")

    db.session.commit()
    return json_response({"message": "updated"})