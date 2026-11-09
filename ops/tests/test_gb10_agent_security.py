import json
from pathlib import Path

import pytest
from jsonschema import ValidationError, validate

from showcase_app.gb10_agent import AccountJail, FILES, PLAN_SCHEMA, TOOL_SCHEMAS, validate_plan

ROOT = Path(__file__).resolve().parents[2]


def test_plan_covers_every_artifact_and_rejects_unknown_tools():
    plan = json.loads((ROOT / 'samples/stage/rehearsed-plan.json').read_text())
    assert validate_plan(plan) == plan
    plan['steps'][0]['tool'] = 'run_shell'
    with pytest.raises(ValidationError):
        validate_plan(plan)


def test_plan_cannot_omit_spanish_or_add_audio_when_off():
    plan = json.loads((ROOT / 'samples/stage/rehearsed-plan.json').read_text())
    plan['deliverables'].remove('email_es')
    with pytest.raises(ValidationError):
        validate_plan(plan)
    plan = json.loads((ROOT / 'samples/stage/rehearsed-plan.json').read_text())
    plan['steps'].append({'tool': 'speak_summary', 'label': 'Speak'})
    with pytest.raises(ValueError, match='Audio is off'):
        validate_plan(plan)


def test_jail_blocks_traversal_absolute_paths_and_symlink(tmp_path):
    jail = tmp_path / 'sample'
    jail.mkdir()
    for name in FILES:
        (jail / name).write_text('fictional note')
    reader = AccountJail(jail)
    assert reader.read_file(FILES[0]) == 'fictional note'
    for name in ('../outside.txt', '/etc/passwd', 'a/../../outside', 'meeting_notes.txt\x00'):
        with pytest.raises(ValueError):
            reader.read_file(name)
    outside = tmp_path / 'outside.txt'
    outside.write_text('outside sentinel')
    (jail / FILES[0]).unlink()
    (jail / FILES[0]).symlink_to(outside)
    assert FILES[0] not in reader.list_files()
    with pytest.raises(OSError):
        reader.read_file(FILES[0])


def test_read_schema_bounds_batch_and_email_has_no_send_fields():
    validate({'files': list(FILES)}, TOOL_SCHEMAS['read_file'])
    with pytest.raises(ValidationError):
        validate({'files': [FILES[0]]}, TOOL_SCHEMAS['read_file'])
    with pytest.raises(ValidationError):
        validate({'subject': 'Fictional', 'body': 'Draft', 'to': 'person@example.invalid'}, TOOL_SCHEMAS['draft_email'])


def test_generated_compliance_and_certification_statements_cannot_be_published():
    from showcase_app.gb10_agent import check_claims
    for value in ['This model is HIPAA compliant', {'subtitle': 'SOC 2 certified'}, ['GDPR compliance']]:
        with pytest.raises(ValueError, match='unsupported'):
            check_claims(value)
    assert check_claims({'title': 'Review access controls', 'points': ['Confirm the fictional pilot owner']})
