from sqlalchemy.orm import Session
from sqlalchemy import func, extract
from db.models import UserAnalytics, User
from uuid import UUID
from datetime import datetime, timedelta

def get_user_detailed_analytics(db: Session, user_id: UUID):
    """Get comprehensive analytics for a user"""
    overall = db.query(
        func.count(UserAnalytics.id).label('total_requests'),
        func.sum(UserAnalytics.input_tokens).label('total_input_tokens'),
        func.sum(UserAnalytics.output_tokens).label('total_output_tokens'),
        func.sum(UserAnalytics.total_tokens).label('total_tokens'),
        func.sum(UserAnalytics.estimated_cost).label('total_cost')
    ).filter(UserAnalytics.user_id == user_id).first()
    
    model_stats = db.query(
        UserAnalytics.model_type,
        func.count(UserAnalytics.id).label('requests'),
        func.sum(UserAnalytics.input_tokens).label('input_tokens'),
        func.sum(UserAnalytics.output_tokens).label('output_tokens'),
        func.sum(UserAnalytics.total_tokens).label('total_tokens'),
        func.sum(UserAnalytics.estimated_cost).label('cost')
    ).filter(UserAnalytics.user_id == user_id).group_by(UserAnalytics.model_type).all()
    
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    daily_stats = db.query(
        func.date(UserAnalytics.request_date).label('date'),
        func.count(UserAnalytics.id).label('requests'),
        func.sum(UserAnalytics.input_tokens).label('input_tokens'),
        func.sum(UserAnalytics.output_tokens).label('output_tokens'),
        func.sum(UserAnalytics.total_tokens).label('total_tokens'),
        func.sum(UserAnalytics.estimated_cost).label('cost')
    ).filter(UserAnalytics.user_id == user_id, UserAnalytics.request_date >= thirty_days_ago)\
     .group_by(func.date(UserAnalytics.request_date)).order_by(func.date(UserAnalytics.request_date)).all()
    
    monthly_stats = db.query(
        extract('year', UserAnalytics.request_date).label('year'),
        extract('month', UserAnalytics.request_date).label('month'),
        func.count(UserAnalytics.id).label('requests'),
        func.sum(UserAnalytics.input_tokens).label('input_tokens'),
        func.sum(UserAnalytics.output_tokens).label('output_tokens'),
        func.sum(UserAnalytics.total_tokens).label('total_tokens'),
        func.sum(UserAnalytics.estimated_cost).label('cost')
    ).filter(UserAnalytics.user_id == user_id)\
     .group_by(extract('year', UserAnalytics.request_date), extract('month', UserAnalytics.request_date))\
     .order_by(extract('year', UserAnalytics.request_date).desc(), extract('month', UserAnalytics.request_date).desc()).limit(12).all()
    
    yearly_stats = db.query(
        extract('year', UserAnalytics.request_date).label('year'),
        func.count(UserAnalytics.id).label('requests'),
        func.sum(UserAnalytics.input_tokens).label('input_tokens'),
        func.sum(UserAnalytics.output_tokens).label('output_tokens'),
        func.sum(UserAnalytics.total_tokens).label('total_tokens'),
        func.sum(UserAnalytics.estimated_cost).label('cost')
    ).filter(UserAnalytics.user_id == user_id)\
     .group_by(extract('year', UserAnalytics.request_date))\
     .order_by(extract('year', UserAnalytics.request_date).desc()).all()
    
    return {
        "overall": {
            "total_requests": overall.total_requests or 0,
            "total_input_tokens": int(overall.total_input_tokens or 0),
            "total_output_tokens": int(overall.total_output_tokens or 0),
            "total_tokens": int(overall.total_tokens or 0),
            "total_cost": round(float(overall.total_cost or 0), 4)
        },
        "by_model": [{"model": s[0] or "unknown", "requests": s[1], "input_tokens": int(s[2] or 0), "output_tokens": int(s[3] or 0), "total_tokens": int(s[4] or 0), "cost": round(float(s[5] or 0), 4)} for s in model_stats],
        "daily": [{"date": s[0].isoformat(), "requests": s[1], "input_tokens": int(s[2] or 0), "output_tokens": int(s[3] or 0), "total_tokens": int(s[4] or 0), "cost": round(float(s[5] or 0), 4)} for s in daily_stats],
        "monthly": [{"year": int(s[0]), "month": int(s[1]), "requests": s[2], "input_tokens": int(s[3] or 0), "output_tokens": int(s[4] or 0), "total_tokens": int(s[5] or 0), "cost": round(float(s[6] or 0), 4)} for s in monthly_stats],
        "yearly": [{"year": int(s[0]), "requests": s[1], "input_tokens": int(s[2] or 0), "output_tokens": int(s[3] or 0), "total_tokens": int(s[4] or 0), "cost": round(float(s[5] or 0), 4)} for s in yearly_stats]
    }

def get_admin_detailed_analytics(db: Session, client_name: str = None):
    """Get comprehensive system-wide analytics with optional client filtering"""
    
    # Base query for filtering by client
    user_filter = db.query(User.id)
    if client_name:
        user_filter = user_filter.filter(User.client_name == client_name)
    user_ids = [u.id for u in user_filter.all()]
    
    # Total users (filtered by client if specified)
    total_users_query = db.query(func.count(User.id))
    if client_name:
        total_users_query = total_users_query.filter(User.client_name == client_name)
    total_users = total_users_query.scalar() or 0
    
    # Overall stats (filtered by client if specified)
    overall_query = db.query(
        func.count(UserAnalytics.id).label('total_requests'),
        func.sum(UserAnalytics.input_tokens).label('total_input_tokens'),
        func.sum(UserAnalytics.output_tokens).label('total_output_tokens'),
        func.sum(UserAnalytics.total_tokens).label('total_tokens'),
        func.sum(UserAnalytics.estimated_cost).label('total_cost')
    )
    if client_name and user_ids:
        overall_query = overall_query.filter(UserAnalytics.user_id.in_(user_ids))
    overall = overall_query.first()
    
    # Top users by cost (filtered by client if specified)
    top_users_query = db.query(
        User.email,
        User.name,
        User.client_name,
        func.count(UserAnalytics.id).label('requests'),
        func.sum(UserAnalytics.input_tokens).label('input_tokens'),
        func.sum(UserAnalytics.output_tokens).label('output_tokens'),
        func.sum(UserAnalytics.total_tokens).label('total_tokens'),
        func.sum(UserAnalytics.estimated_cost).label('cost')
    ).outerjoin(UserAnalytics, User.id == UserAnalytics.user_id)
    
    if client_name:
        top_users_query = top_users_query.filter(User.client_name == client_name)
    
    top_users = top_users_query.group_by(User.id, User.email, User.name, User.client_name)\
                               .order_by(func.coalesce(func.sum(UserAnalytics.estimated_cost), 0).desc())\
                               .limit(10).all()
    
    # Model-wise stats (filtered by client if specified)
    model_stats_query = db.query(
        UserAnalytics.model_type,
        func.count(UserAnalytics.id).label('requests'),
        func.sum(UserAnalytics.input_tokens).label('input_tokens'),
        func.sum(UserAnalytics.output_tokens).label('output_tokens'),
        func.sum(UserAnalytics.total_tokens).label('total_tokens'),
        func.sum(UserAnalytics.estimated_cost).label('cost')
    )
    if client_name and user_ids:
        model_stats_query = model_stats_query.filter(UserAnalytics.user_id.in_(user_ids))
    model_stats = model_stats_query.group_by(UserAnalytics.model_type).all()
    
    # Monthly stats (filtered by client if specified)
    monthly_stats_query = db.query(
        extract('year', UserAnalytics.request_date).label('year'),
        extract('month', UserAnalytics.request_date).label('month'),
        func.count(UserAnalytics.id).label('requests'),
        func.sum(UserAnalytics.input_tokens).label('input_tokens'),
        func.sum(UserAnalytics.output_tokens).label('output_tokens'),
        func.sum(UserAnalytics.total_tokens).label('total_tokens'),
        func.sum(UserAnalytics.estimated_cost).label('cost')
    )
    if client_name and user_ids:
        monthly_stats_query = monthly_stats_query.filter(UserAnalytics.user_id.in_(user_ids))
    
    monthly_stats = monthly_stats_query.group_by(extract('year', UserAnalytics.request_date), extract('month', UserAnalytics.request_date))\
                                      .order_by(extract('year', UserAnalytics.request_date).desc(), extract('month', UserAnalytics.request_date).desc())\
                                      .limit(12).all()
    
    # Daily stats (filtered by client if specified) - last 7 days
    from datetime import datetime, timedelta
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    daily_stats_query = db.query(
        func.date(UserAnalytics.request_date).label('date'),
        func.count(UserAnalytics.id).label('requests'),
        func.sum(UserAnalytics.input_tokens).label('input_tokens'),
        func.sum(UserAnalytics.output_tokens).label('output_tokens'),
        func.sum(UserAnalytics.total_tokens).label('total_tokens'),
        func.sum(UserAnalytics.estimated_cost).label('cost'),
        func.count(func.distinct(UserAnalytics.user_id)).label('active_users')
    ).filter(UserAnalytics.request_date >= seven_days_ago)
    if client_name and user_ids:
        daily_stats_query = daily_stats_query.filter(UserAnalytics.user_id.in_(user_ids))
    
    daily_stats = daily_stats_query.group_by(func.date(UserAnalytics.request_date))\
                                   .order_by(func.date(UserAnalytics.request_date).desc()).all()

    # Daily user breakdown - user-wise data for each day
    daily_user_stats_query = db.query(
        func.date(UserAnalytics.request_date).label('date'),
        User.name,
        User.email,
        func.count(UserAnalytics.id).label('requests'),
        func.sum(UserAnalytics.total_tokens).label('total_tokens'),
        func.sum(UserAnalytics.estimated_cost).label('cost')
    ).join(User, UserAnalytics.user_id == User.id)\
     .filter(UserAnalytics.request_date >= seven_days_ago)
    if client_name and user_ids:
        daily_user_stats_query = daily_user_stats_query.filter(UserAnalytics.user_id.in_(user_ids))
    
    daily_user_stats = daily_user_stats_query.group_by(
        func.date(UserAnalytics.request_date), User.id, User.name, User.email
    ).order_by(func.date(UserAnalytics.request_date).desc()).all()

    # Client breakdown (new feature)
    client_stats = db.query(
        User.client_name,
        func.count(func.distinct(User.id)).label('users'),
        func.count(UserAnalytics.id).label('requests'),
        func.sum(UserAnalytics.input_tokens).label('input_tokens'),
        func.sum(UserAnalytics.output_tokens).label('output_tokens'),
        func.sum(UserAnalytics.total_tokens).label('total_tokens'),
        func.sum(UserAnalytics.estimated_cost).label('cost')
    ).outerjoin(UserAnalytics, User.id == UserAnalytics.user_id)\
     .group_by(User.client_name)\
     .order_by(func.coalesce(func.sum(UserAnalytics.estimated_cost), 0).desc()).all()
    
    return {
        "total_users": total_users,
        "client_filter": client_name,
        "overall": {
            "total_requests": overall.total_requests or 0,
            "total_input_tokens": int(overall.total_input_tokens or 0),
            "total_output_tokens": int(overall.total_output_tokens or 0),
            "total_tokens": int(overall.total_tokens or 0),
            "total_cost": round(float(overall.total_cost or 0), 4)
        },
        "top_users": [
            {
                "email": user[0],
                "name": user[1],
                "client_name": user[2],
                "requests": user[3] or 0,
                "input_tokens": int(user[4] or 0),
                "output_tokens": int(user[5] or 0),
                "total_tokens": int(user[6] or 0),
                "cost": round(float(user[7] or 0), 4)
            }
            for user in top_users
        ],
        "by_model": [
            {
                "model": stat[0] or "unknown",
                "requests": stat[1],
                "input_tokens": int(stat[2] or 0),
                "output_tokens": int(stat[3] or 0),
                "total_tokens": int(stat[4] or 0),
                "cost": round(float(stat[5] or 0), 4)
            }
            for stat in model_stats
        ],
        "by_client": [
            {
                "client_name": stat[0] or "unknown",
                "users": stat[1],
                "requests": stat[2] or 0,
                "input_tokens": int(stat[3] or 0),
                "output_tokens": int(stat[4] or 0),
                "total_tokens": int(stat[5] or 0),
                "cost": round(float(stat[6] or 0), 4)
            }
            for stat in client_stats
        ],
        "monthly": [
            {
                "year": int(stat[0]),
                "month": int(stat[1]),
                "requests": stat[2],
                "input_tokens": int(stat[3] or 0),
                "output_tokens": int(stat[4] or 0),
                "total_tokens": int(stat[5] or 0),
                "cost": round(float(stat[6] or 0), 4)
            }
            for stat in monthly_stats
        ],
        "daily": [
            {
                "date": stat[0].isoformat(),
                "requests": stat[1],
                "input_tokens": int(stat[2] or 0),
                "output_tokens": int(stat[3] or 0),
                "total_tokens": int(stat[4] or 0),
                "cost": round(float(stat[5] or 0), 4),
                "active_users": stat[6] or 0
            }
            for stat in daily_stats
        ],
        "daily_users": [
            {
                "date": stat[0].isoformat(),
                "name": stat[1],
                "email": stat[2],
                "requests": stat[3],
                "total_tokens": int(stat[4] or 0),
                "cost": round(float(stat[5] or 0), 4)
            }
            for stat in daily_user_stats
        ]
    }


# TODO: Uncomment after running migration (see DATA_MODEL_CHANGES.md)
# def add_infrastructure_cost(db, data): ...
# def get_infrastructure_costs(db, filters): ...
# def get_total_cost_summary(db, filters): ...
