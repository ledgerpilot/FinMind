from flask import Blueprint

from app.api.auth import auth_bp
from app.api.transactions import transactions_bp
from app.api.categories import categories_bp
from app.api.dashboard import dashboard_bp
from app.api.bills import bills_bp
from app.api.reminders import reminders_bp
from app.api.observability import observability_bp
from app.api.accounts import accounts_bp # Import the new accounts blueprint

api_bp = Blueprint("api", __name__, url_prefix="/api")

api_bp.register_blueprint(auth_bp)
api_bp.register_blueprint(transactions_bp)
api_bp.register_blueprint(categories_bp)
api_bp.register_blueprint(dashboard_bp)
api_bp.register_blueprint(bills_bp)
api_bp.register_blueprint(reminders_bp)
api_bp.register_blueprint(observability_bp)
api_bp.register_blueprint(accounts_bp) # Register the new accounts blueprint