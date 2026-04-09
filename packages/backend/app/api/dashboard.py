from flask import Blueprint, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from app.extensions import db
from app.models import Transaction, Bill, Category, User, Account
from app.schemas import DashboardSummarySchema, TransactionSchema, BillSchema, CategoryBreakdownSchema
from app.utils.api import json_abort

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


@dashboard_bp.route("/summary", methods=["GET"])
@jwt_required()
def dashboard_summary():
    """
    Provides a financial overview for the authenticated user for a given month,
    optionally filtered by account.
    ---
    get:
      summary: Get dashboard summary
      security:
        - jwt: []
      parameters:
        - in: query
          name: month
          schema:
            type: string
            format: YYYY-MM
          description: Month for which to retrieve the summary (e.g., "2023-10"). Defaults to current month.
        - in: query
          name: account_id
          schema:
            type: integer
          description: Optional. ID of the financial account to filter the summary by.
                       If not provided, the summary will be for the user's primary account.
      responses:
        200:
          description: A summary of financial data.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/DashboardSummarySchema'
        400:
          description: Invalid month format or account_id.
        401:
          description: Unauthorized.
        404:
          description: Account not found or not owned by user.
    """
    user_id = get_jwt_identity()
    user = User.query.get_or_404(user_id)

    # Determine the target account
    account_id = request.args.get("account_id", type=int)
    target_account = None

    if account_id:
        target_account = Account.query.filter_by(id=account_id, user_id=user_id).first()
        if not target_account:
            json_abort(404, "Account not found or not owned by user.")
    else:
        # If no account_id is provided, use the user's primary account
        target_account = Account.query.filter_by(user_id=user_id, is_primary=True).first()
        if not target_account:
            json_abort(400, "No account_id provided and user has no primary account. Please specify an account or create a primary one.")

    # Validate month parameter
    month_str = request.args.get("month")
    if month_str:
        try:
            year, month = map(int, month_str.split("-"))
            start_date = datetime(year, month, 1).date()
            # Calculate end_date for the month
            if month == 12:
                end_date = datetime(year + 1, 1, 1).date()
            else:
                end_date = datetime(year, month + 1, 1).date()
            period = {"month": month_str}
        except ValueError:
            json_abort(400, "Invalid month format. Use YYYY-MM.")
    else:
        # Default to current month
        now = datetime.now()
        start_date = datetime(now.year, now.month, 1).date()
        if now.month == 12:
            end_date = datetime(now.year + 1, 1, 1).date()
        else:
            end_date = datetime(now.year, now.month + 1, 1).date()
        period = {"month": now.strftime("%Y-%m")}

    # Base query filters for transactions and bills
    base_transaction_filter = [
        Transaction.user_id == user_id,
        Transaction.account_id == target_account.id,
        Transaction.date >= start_date,
        Transaction.date < end_date,
    ]

    base_bill_filter = [
        Bill.user_id == user_id,
        Bill.account_id == target_account.id,
        Bill.next_due_date >= datetime.now().date(),
    ]

    # Get transactions for the period
    transactions_query = Transaction.query.filter(*base_transaction_filter)
    transactions = transactions_query.order_by(Transaction.date.desc()).all()
    transactions_data = TransactionSchema(many=True).dump(transactions)

    # Calculate monthly income and expenses
    income = db.session.query(func.sum(Transaction.amount)).filter(
        *base_transaction_filter,
        Transaction.type == "INCOME",
    ).scalar() or 0.0

    expenses = db.session.query(func.sum(Transaction.amount)).filter(
        *base_transaction_filter,
        Transaction.type == "EXPENSE",
    ).scalar() or 0.0

    net_flow = income - expenses

    # Upcoming bills (for the current month onwards)
    upcoming_bills_query = Bill.query.filter(*base_bill_filter)
    upcoming_bills = upcoming_bills_query.order_by(Bill.next_due_date.asc()).all()
    upcoming_bills_data = BillSchema(many=True).dump(upcoming_bills)

    upcoming_bills_total = sum(b.amount for b in upcoming_bills)
    upcoming_bills_count = len(upcoming_bills)

    # Category breakdown for expenses
    category_breakdown_query = (
        db.session.query(
            Category.id,
            Category.name,
            func.sum(Transaction.amount).label("total_amount"),
        )
        .join(Transaction, Transaction.category_id == Category.id)
        .filter(
            *base_transaction_filter,
            Transaction.type == "EXPENSE",
        )
        .group_by(Category.id, Category.name)
    ).all()

    total_expenses_for_breakdown = (
        db.session.query(func.sum(Transaction.amount))
        .filter(
            *base_transaction_filter,
            Transaction.type == "EXPENSE",
        )
        .scalar()
        or 0.0
    )

    category_breakdown_data = []
    for cat_id, cat_name, total_amount in category_breakdown_query:
        share_pct = (
            (total_amount / total_expenses_for_breakdown * 100)
            if total_expenses_for_breakdown > 0
            else 0.0
        )
        category_breakdown_data.append(
            {
                "category_id": cat_id,
                "category_name": cat_name,
                "amount": total_amount,
                "share_pct": round(share_pct, 2),
            }
        )

    # Handle uncategorized expenses
    uncategorized_expenses = (
        db.session.query(func.sum(Transaction.amount))
        .filter(
            *base_transaction_filter,
            Transaction.type == "EXPENSE",
            Transaction.category_id.is_(None),
        )
        .scalar()
        or 0.0
    )

    if uncategorized_expenses > 0:
        share_pct = (
            (uncategorized_expenses / total_expenses_for_breakdown * 100)
            if total_expenses_for_breakdown > 0
            else 0.0
        )
        category_breakdown_data.append(
            {
                "category_id": None,
                "category_name": "Uncategorized",
                "amount": uncategorized_expenses,
                "share_pct": round(share_pct, 2),
            }
        )

    response_data = {
        "period": period,
        "summary": {
            "net_flow": round(net_flow, 2),
            "monthly_income": round(income, 2),
            "monthly_expenses": round(expenses, 2),
            "upcoming_bills_total": round(upcoming_bills_total, 2),
            "upcoming_bills_count": upcoming_bills_count,
        },
        "recent_transactions": transactions_data,
        "upcoming_bills": upcoming_bills_data,
        "category_breakdown": category_breakdown_data,
    }

    return DashboardSummarySchema().dump(response_data)