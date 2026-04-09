import json
from urllib import request

from sqlalchemy import extract, func

from ..config import Settings
from ..extensions import db
from ..models import Expense

_settings = Settings()
DEFAULT_PERSONA = (
    "You are FinMind's pragmatic financial coach. Be concise, non-judgmental, "
    "data-driven, and action-oriented. Return actionable, realistic guidance."
)


def _monthly_totals(uid: int, ym: str) -> tuple[float, float]:
    year, month = map(int, ym.split("-"))
    income = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type == "INCOME",
        )
        .scalar()
    )
    expenses = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type != "INCOME",
        )
        .scalar()
    )
    return float(income or 0), float(expenses or 0)


def _category_spend(uid: int, ym: str) -> dict[str, float]:
    year, month = map(int, ym.split("-"))
    rows = (
        db.session.query(
            Expense.category_id, func.coalesce(func.sum(Expense.amount), 0)
        )
        .filter(
            Expense.user_id == uid,
            extract("year", Expense.spent_at) == year,
            extract("month", Expense.spent_at) == month,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.category_id)
        .all()
    )
    return {str(k or "uncat"): float(v) for k, v in rows}


def _previous_month(ym: str) -> str:
    year, month = map(int, ym.split("-"))
    if month == 1:
        return f"{year - 1:04d}-12"
    return f"{year:04d}-{month - 1:02d}"


def _build_analytics(uid: int, ym: str) -> dict:
    _, current_expenses = _monthly_totals(uid, ym)
    _, prev_expenses = _monthly_totals(uid, _previous_month(ym))
    if prev_expenses > 0:
        mom = round(((current_expenses - prev_expenses) / prev_expenses) * 100, 2)
    else:
        mom = 0.0
    cats = _category_spend(uid, ym)
    top = sorted(cats.items(), key=lambda x: x[1], reverse=True)[:3]
    return {
        "month_over_month_change_pct": mom,
        "current_month_expenses": round(current_expenses, 2),
        "previous_month_expenses": round(prev_expenses, 2),
        "top_categories": [{"category_id": k, "amount": round(v, 2)} for k, v in top],
    }


def _heuristic_budget(
    uid: int, ym: str, persona: str, warnings: list[str] | None = None
):
    income, expenses = _monthly_totals(uid, ym)
    target = round((expenses * 0.9) if expenses else 500.0, 2)
    payload = {
        "month": ym,
        "suggested_total": target,
        "breakdown": {
            "needs": round(target * 0.5, 2),
            "wants": round(target * 0.3, 2),
            "savings": round(target * 0.2, 2),
        },
        "tips": [
            "Cap discretionary spending in the highest category by 10%.",
            "Set one automatic transfer to savings on payday.",
        ],
        "analytics": _build_analytics(uid, ym),
        "persona": persona,
        "method": "heuristic",
    }
    if warnings:
        payload["warnings"] = warnings
    payload["net_flow"] = round(income - expenses, 2)
    return payload


def _extract_json_object(raw: str) -> dict:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("model did not return JSON object")
    return json.loads(text[start : end + 1])


def _gemini_budget_suggestion(
    uid: int, ym: str, api_key: str, model: str, persona: str
) -> dict:
    categories = _category_spend(uid, ym)
    analytics = _build_analytics(uid, ym)
    prompt = (
        f"{persona}\n"
        "Use this month data and return strict JSON only with keys: "
        "suggested_total, breakdown(needs,wants,savings), tips(list <=3).\n"
        f"month={ym}\n"
        f"category_spend={categories}\n"
        f"analytics={analytics}"
    )
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    body = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2},
        }
    ).encode("utf-8")
    req = request.Request(
        url=url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=10) as resp:  # nosec B310
        payload = json.loads(resp.read().decode("utf-8"))
    text = (
        payload.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    )
    parsed = _extract_json_object(text)
    parsed["month"] = ym
    parsed["analytics"] = analytics
    parsed["persona"] = persona
    parsed["method"] = "gemini"
    return parsed


def monthly_budget_suggestion(
    uid: int,
    ym: str,
    gemini_api_key: str | None = None,
    gemini_model: str | None = None,
    persona: str | None = None,
):
    key = (gemini_api_key or "").strip() or (_settings.gemini_api_key or "")
    model = gemini_model or _settings.gemini_model
    persona_text = (persona or DEFAULT_PERSONA).strip()

    if key:
        try:
            return _gemini_budget_suggestion(uid, ym, key, model, persona_text)
        except Exception:
            return _heuristic_budget(
                uid, ym, persona_text, warnings=["gemini_unavailable"]
            )
    return _heuristic_budget(uid, ym, persona_text)


from datetime import date, timedelta


def _week_bounds(week_start_str: str | None = None) -> tuple[date, date]:
    """Return (monday, sunday) for the given week start, defaulting to current week."""
    if week_start_str:
        start = date.fromisoformat(week_start_str)
    else:
        today = date.today()
        start = today - timedelta(days=today.weekday())
    end = start + timedelta(days=6)
    return start, end


def _weekly_totals(uid: int, week_start: date, week_end: date) -> tuple[float, float]:
    income = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            func.date(Expense.spent_at) >= week_start,
            func.date(Expense.spent_at) <= week_end,
            Expense.expense_type == "INCOME",
        )
        .scalar()
    )
    expenses = (
        db.session.query(func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            func.date(Expense.spent_at) >= week_start,
            func.date(Expense.spent_at) <= week_end,
            Expense.expense_type != "INCOME",
        )
        .scalar()
    )
    return float(income or 0), float(expenses or 0)


def _weekly_category_spend(uid: int, week_start: date, week_end: date) -> dict[str, float]:
    rows = (
        db.session.query(Expense.category_id, func.coalesce(func.sum(Expense.amount), 0))
        .filter(
            Expense.user_id == uid,
            func.date(Expense.spent_at) >= week_start,
            func.date(Expense.spent_at) <= week_end,
            Expense.expense_type != "INCOME",
        )
        .group_by(Expense.category_id)
        .all()
    )
    return {str(k or "uncat"): float(v) for k, v in rows}


def _heuristic_weekly_summary(
    uid: int, week_start: date, week_end: date, persona: str
) -> dict:
    income, total_spending = _weekly_totals(uid, week_start, week_end)
    prev_start = week_start - timedelta(days=7)
    prev_end = week_end - timedelta(days=7)
    _, prev_spending = _weekly_totals(uid, prev_start, prev_end)
    wow = (
        round(((total_spending - prev_spending) / prev_spending) * 100, 2)
        if prev_spending > 0
        else 0.0
    )
    cats = _weekly_category_spend(uid, week_start, week_end)
    top = sorted(cats.items(), key=lambda x: x[1], reverse=True)[:5]
    net_flow = round(income - total_spending, 2)
    insights = []
    if total_spending > income > 0:
        insights.append("Spending exceeded income this week — review discretionary expenses.")
    if top:
        top_cat, top_amt = top[0]
        insights.append(f"Highest spend: {top_cat} (${top_amt:.2f}).")
    if wow > 20:
        insights.append(f"Spending up {wow:.1f}% vs last week.")
    elif wow < -20:
        insights.append(f"Spending down {abs(wow):.1f}% vs last week — good progress.")
    return {
        "week_start": week_start.isoformat(),
        "total_spending": round(total_spending, 2),
        "income": round(income, 2),
        "net_flow": net_flow,
        "top_categories": [{"category_id": k, "amount": round(v, 2)} for k, v in top],
        "week_over_week_change_pct": wow,
        "insights": insights or ["No significant trends this week."],
        "persona": persona,
        "method": "heuristic",
    }


def _gemini_weekly_summary(
    uid: int, week_start: date, week_end: date,
    api_key: str, model: str, persona: str,
) -> dict:
    base = _heuristic_weekly_summary(uid, week_start, week_end, persona)
    json_hint = '{"insights": ["<insight 1>", "<insight 2>", "<insight 3>"]}'
    prompt = (
        f"{persona}\n"
        f"Return strict JSON only matching this shape: {json_hint}\n"
        f"week={week_start.isoformat()} total_spending={base['total_spending']} "
        f"income={base['income']} top={base['top_categories']} wow={base['week_over_week_change_pct']}"
    )
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3},
    }).encode("utf-8")
    req = request.Request(url=url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with request.urlopen(req, timeout=10) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    text = (
        payload.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
    )
    parsed = _extract_json_object(text)
    base["insights"] = parsed.get("insights", base["insights"])
    base["method"] = "gemini"
    return base


def weekly_financial_summary(
    uid: int,
    week_start_str: str | None = None,
    gemini_api_key: str | None = None,
    persona: str | None = None,
) -> dict:
    """Return a weekly financial summary for *uid*.

    Parameters
    ----------
    uid:
        User ID.
    week_start_str:
        ISO date string (YYYY-MM-DD) for the Monday of the target week.
        Defaults to the current week.
    gemini_api_key:
        Optional Gemini API key; when provided, insights are AI-generated.
    persona:
        Override the default financial-coach persona prompt.
    """
    week_start, week_end = _week_bounds(week_start_str)
    persona_text = (persona or DEFAULT_PERSONA).strip()
    key = (gemini_api_key or "").strip() or (_settings.gemini_api_key or "")
    if key:
        try:
            return _gemini_weekly_summary(
                uid, week_start, week_end, key, _settings.gemini_model, persona_text
            )
        except Exception:
            result = _heuristic_weekly_summary(uid, week_start, week_end, persona_text)
            result["method"] = "heuristic_fallback"
            return result
    return _heuristic_weekly_summary(uid, week_start, week_end, persona_text)
