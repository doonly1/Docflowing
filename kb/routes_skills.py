import logging
from flask import Blueprint, jsonify, request, g

from server.auth import login_required

from .skills.manager import (
    create_skill,
    get_skill,
    update_skill,
    patch_skill,
    delete_skill,
    restore_skill,
    list_skills,
    get_categories,
    write_skill_file,
    remove_skill_file,
    list_skill_files,
)
from .skills.curator import (
    run_review,
    run_llm_review,
    list_review_reports,
    get_review_report,
    get_curator_status,
    should_run,
)
from .skills.usage import bump_use, pin_skill, unpin_skill

logger = logging.getLogger(__name__)


def register_skills_routes(bp: Blueprint):

    @bp.route('/skills', methods=['GET'])
    @login_required
    def api_list_skills():
        user_id = g.user_id
        category = request.args.get('category')
        state = request.args.get('state')
        skills = list_skills(user_id, category=category, state=state)
        categories = get_categories(user_id)
        return jsonify({
            'success': True,
            'skills': skills,
            'categories': categories,
            'count': len(skills),
        })

    @bp.route('/skills/create', methods=['POST'])
    @login_required
    def api_create_skill():
        user_id = g.user_id
        data = request.get_json() or {}
        name = data.get('name')
        content = data.get('content')
        category = data.get('category')
        created_by = data.get('created_by', 'user')

        if not name or not content:
            return jsonify({'success': False, 'error': 'name and content are required.'}), 400

        result = create_skill(user_id, name, content, category=category, created_by=created_by)
        status_code = 200 if result.get('success') else 400
        return jsonify(result), status_code

    @bp.route('/skills/<skill_name>', methods=['GET'])
    @login_required
    def api_get_skill(skill_name):
        user_id = g.user_id
        result = get_skill(user_id, skill_name)
        if not result.get('success'):
            return jsonify(result), 404
        return jsonify(result)

    @bp.route('/skills/<skill_name>/use', methods=['POST'])
    @login_required
    def api_use_skill(skill_name):
        user_id = g.user_id
        bump_use(user_id, skill_name)
        return jsonify({'success': True, 'message': f"Usage recorded for '{skill_name}'."})

    @bp.route('/skills/<skill_name>/edit', methods=['POST'])
    @login_required
    def api_edit_skill(skill_name):
        user_id = g.user_id
        data = request.get_json() or {}
        content = data.get('content')
        if not content:
            return jsonify({'success': False, 'error': 'content is required.'}), 400

        result = update_skill(user_id, skill_name, content)
        status_code = 200 if result.get('success') else 400
        return jsonify(result), status_code

    @bp.route('/skills/<skill_name>/patch', methods=['POST'])
    @login_required
    def api_patch_skill(skill_name):
        user_id = g.user_id
        data = request.get_json() or {}
        old_string = data.get('old_string')
        new_string = data.get('new_string')
        if not old_string or not new_string:
            return jsonify({'success': False, 'error': 'old_string and new_string are required.'}), 400

        result = patch_skill(user_id, skill_name, old_string, new_string)
        status_code = 200 if result.get('success') else 400
        return jsonify(result), status_code

    @bp.route('/skills/<skill_name>', methods=['DELETE'])
    @login_required
    def api_delete_skill(skill_name):
        user_id = g.user_id
        data = request.get_json() or {}
        absorbed_into = data.get('absorbed_into')
        result = delete_skill(user_id, skill_name, absorbed_into=absorbed_into)
        status_code = 200 if result.get('success') else 404
        return jsonify(result), status_code

    @bp.route('/skills/<skill_name>/restore', methods=['POST'])
    @login_required
    def api_restore_skill(skill_name):
        user_id = g.user_id
        result = restore_skill(user_id, skill_name)
        status_code = 200 if result.get('success') else 404
        return jsonify(result), status_code

    @bp.route('/skills/<skill_name>/pin', methods=['POST'])
    @login_required
    def api_pin_skill(skill_name):
        user_id = g.user_id
        ok, msg = pin_skill(user_id, skill_name)
        return jsonify({'success': ok, 'message': msg})

    @bp.route('/skills/<skill_name>/unpin', methods=['POST'])
    @login_required
    def api_unpin_skill(skill_name):
        user_id = g.user_id
        ok, msg = unpin_skill(user_id, skill_name)
        return jsonify({'success': ok, 'message': msg})

    @bp.route('/skills/curator/run', methods=['POST'])
    @login_required
    def api_curator_run():
        user_id = g.user_id
        data = request.get_json() or {}
        stale_after_days = data.get('stale_after_days', 30)
        archive_after_days = data.get('archive_after_days', 90)

        report = run_review(
            user_id,
            stale_after_days=stale_after_days,
            archive_after_days=archive_after_days,
        )
        return jsonify(report)

    @bp.route('/skills/curator/status', methods=['GET'])
    @login_required
    def api_curator_status():
        user_id = g.user_id
        status = get_curator_status(user_id)
        return jsonify({'success': True, **status})

    @bp.route('/skills/categories', methods=['GET'])
    @login_required
    def api_get_categories():
        user_id = g.user_id
        categories = get_categories(user_id)
        return jsonify({'success': True, 'categories': categories})

    @bp.route('/skills/<skill_name>/files', methods=['GET'])
    @login_required
    def api_list_skill_files(skill_name):
        user_id = g.user_id
        result = list_skill_files(user_id, skill_name)
        status_code = 200 if result.get('success') else 404
        return jsonify(result), status_code

    @bp.route('/skills/<skill_name>/files', methods=['POST'])
    @login_required
    def api_write_skill_file(skill_name):
        user_id = g.user_id
        data = request.get_json() or {}
        file_path = data.get('file_path')
        content = data.get('content')
        if not file_path or content is None:
            return jsonify({'success': False, 'error': 'file_path and content are required.'}), 400
        result = write_skill_file(user_id, skill_name, file_path, content)
        status_code = 200 if result.get('success') else 400
        return jsonify(result), status_code

    @bp.route('/skills/<skill_name>/files', methods=['DELETE'])
    @login_required
    def api_remove_skill_file(skill_name):
        user_id = g.user_id
        data = request.get_json() or {}
        file_path = data.get('file_path')
        if not file_path:
            return jsonify({'success': False, 'error': 'file_path is required.'}), 400
        result = remove_skill_file(user_id, skill_name, file_path)
        status_code = 200 if result.get('success') else 400
        return jsonify(result), status_code

    @bp.route('/skills/curator/review', methods=['POST'])
    @login_required
    def api_curator_llm_review():
        user_id = g.user_id
        data = request.get_json() or {}
        dry_run = data.get('dry_run', False)

        report = run_llm_review(user_id, dry_run=dry_run)
        return jsonify(report)

    @bp.route('/skills/curator/reports', methods=['GET'])
    @login_required
    def api_curator_reports():
        user_id = g.user_id
        reports = list_review_reports(user_id)
        return jsonify({'success': True, 'reports': reports, 'count': len(reports)})

    @bp.route('/skills/curator/report/<report_id>', methods=['GET'])
    @login_required
    def api_curator_report_detail(report_id):
        user_id = g.user_id
        report = get_review_report(user_id, report_id)
        if not report:
            return jsonify({'success': False, 'error': 'Report not found.'}), 404
        return jsonify({'success': True, 'report': report})
