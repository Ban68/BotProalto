"""
Analytics API Blueprint for ProAlto WhatsApp Bot.
Provides REST endpoints for the analytics dashboard.
"""
from flask import Blueprint, request, jsonify
from src.auth import requires_auth
from src.analytics_queries import (
    get_funnel_metrics,
    get_volume_stats,
    get_response_time_metrics,
    start_audit,
    get_audit_report,
    get_audit_list,
)

analytics_bp = Blueprint('analytics', __name__)


def _get_dates():
    """Extract from/to date params from request args."""
    return request.args.get('from'), request.args.get('to')


@analytics_bp.route('/admin/api/analytics/funnel')
@requires_auth
def funnel():
    date_from, date_to = _get_dates()
    data = get_funnel_metrics(date_from, date_to)
    return jsonify({'funnel': data, 'period': {'from': date_from, 'to': date_to}})


@analytics_bp.route('/admin/api/analytics/volume')
@requires_auth
def volume():
    date_from, date_to = _get_dates()
    data = get_volume_stats(date_from, date_to)
    return jsonify(data)


@analytics_bp.route('/admin/api/analytics/response-times')
@requires_auth
def response_times():
    date_from, date_to = _get_dates()
    data = get_response_time_metrics(date_from, date_to)
    return jsonify(data)


@analytics_bp.route('/admin/api/analytics/audit', methods=['POST'])
@requires_auth
def create_audit():
    body = request.get_json(silent=True) or {}
    sample_size = body.get('sample_size', 10)
    date_from = body.get('from')
    date_to = body.get('to')
    try:
        audit_id = start_audit(sample_size, date_from, date_to)
        return jsonify({'status': 'started', 'audit_id': audit_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@analytics_bp.route('/admin/api/analytics/audit/<audit_id>')
@requires_auth
def audit_detail(audit_id):
    report = get_audit_report(audit_id)
    if not report:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(report)


@analytics_bp.route('/admin/api/analytics/audits')
@requires_auth
def audits_list():
    audits = get_audit_list()
    return jsonify(audits)
