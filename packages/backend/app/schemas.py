from marshmallow import Schema, fields, validate, post_load


class AccountSchema(Schema):
    id = fields.Int(dump_only=True)
    name = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    user_id = fields.Int(dump_only=True)
    currency = fields.Str(required=True, validate=validate.Length(equal=3))
    is_primary = fields.Bool(dump_only=True)


class UserSchema(Schema):
    id = fields.Int(dump_only=True)
    email = fields.Str(required=True, validate=validate.Email())
    preferred_currency = fields.Str(dump_only=True)
    accounts = fields.List(fields.Nested(AccountSchema), dump_only=True)


class RegisterSchema(UserSchema):
    password = fields.Str(required=True, load_only=True, validate=validate.Length(min=6))


class LoginSchema(UserSchema):
    password = fields.Str(required=True, load_only=True)


class UpdateUserSchema(Schema):
    preferred_currency = fields.Str(
        required=False,
        validate=validate.Length(equal=3),
        metadata={"description": "ISO 4217 currency code (e.g., 'USD', 'INR')"},
    )


class CategorySchema(Schema):
    id = fields.Int(dump_only=True)
    name = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    user_id = fields.Int(dump_only=True)


class TransactionSchema(Schema):
    id = fields.Int(dump_only=True)
    description = fields.Str(required=True, validate=validate.Length(min=1, max=255))
    amount = fields.Float(required=True, validate=validate.Range(min=0.01))
    date = fields.Date(required=True)
    type = fields.Str(required=True, validate=validate.OneOf(["INCOME", "EXPENSE"]))
    category_id = fields.Int(required=False, allow_none=True)
    user_id = fields.Int(dump_only=True)
    account_id = fields.Int(required=True)  # Must be provided when creating
    currency = fields.Str(required=True, validate=validate.Length(equal=3))
    created_at = fields.DateTime(dump_only=True)


class BillSchema(Schema):
    id = fields.Int(dump_only=True)
    name = fields.Str(required=True, validate=validate.Length(min=1, max=255))
    amount = fields.Float(required=True, validate=validate.Range(min=0.01))
    currency = fields.Str(required=False, validate=validate.Length(equal=3)) # Can be inferred
    next_due_date = fields.Date(required=True)
    cadence = fields.Str(
        required=True,
        validate=validate.OneOf(["DAILY", "WEEKLY", "MONTHLY", "YEARLY"]),
    )
    channel_email = fields.Bool(required=False, dump_default=False)
    channel_whatsapp = fields.Bool(required=False, dump_default=False)
    autopay_enabled = fields.Bool(required=False, dump_default=False)
    user_id = fields.Int(dump_only=True)
    account_id = fields.Int(required=True)  # Must be provided when creating
    created_at = fields.DateTime(dump_only=True)


class ReminderSchema(Schema):
    id = fields.Int(dump_only=True)
    bill_id = fields.Int(required=True)
    remind_at = fields.DateTime(required=True)
    status = fields.Str(
        required=True, validate=validate.OneOf(["PENDING", "SENT", "FAILED"])
    )
    channel_email = fields.Bool(required=True)
    channel_whatsapp = fields.Bool(required=True)
    message = fields.Str(required=False, allow_none=True)
    created_at = fields.DateTime(dump_only=True)


class ScheduleRemindersResponseSchema(Schema):
    created = fields.Int(required=True)
    errors = fields.List(fields.Str(), required=False)


class CategoryBreakdownSchema(Schema):
    category_id = fields.Int(allow_none=True)
    category_name = fields.Str()
    amount = fields.Float()
    share_pct = fields.Float()


class DashboardSummarySchema(Schema):
    period = fields.Nested(
        Schema.from_dict({"month": fields.Str(required=True)}), required=True
    )
    summary = fields.Nested(
        Schema.from_dict(
            {
                "net_flow": fields.Float(required=True),
                "monthly_income": fields.Float(required=True),
                "monthly_expenses": fields.Float(required=True),
                "upcoming_bills_total": fields.Float(required=True),
                "upcoming_bills_count": fields.Int(required=True),
            }
        ),
        required=True,
    )
    recent_transactions = fields.List(fields.Nested(TransactionSchema), required=True)
    upcoming_bills = fields.List(fields.Nested(BillSchema), required=True)
    category_breakdown = fields.List(fields.Nested(CategoryBreakdownSchema), required=True)
    errors = fields.List(fields.Str(), required=False)