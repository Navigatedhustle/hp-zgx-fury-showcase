"""Actual local whiteboard extraction and executive readout."""
import base64
import json
import time

from showcase_app.gb10_agent import ROOT
from showcase_app.gb10_client import LEAD, WORKER, infer, json_content


async def run_vision(run_id, purpose='live', emit=None):
    emit = emit or (lambda event: None)
    began = time.monotonic()
    encoded = base64.b64encode((ROOT / 'samples/stage/vision/whiteboard.png').read_bytes()).decode()
    result = await infer([{'role': 'user', 'content': [
        {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + encoded}},
        {'type': 'text', 'text': 'Extract EVERY action item, owner and ISO date. Return only a JSON array of objects with action, owner, date. Preserve the exact action wording.'}]}],
        model=WORKER, caller='vision', run_id=run_id, purpose=purpose, role='whiteboard', max_tokens=500)
    actions = json_content(result['content'])
    expected = json.loads((ROOT / 'samples/stage/vision/expected.json').read_text())['whiteboard.png']
    from showcase_app.gb10_quality import extraction_matches
    if result['finish_reason'] != 'stop' or not extraction_matches('whiteboard.png', actions, expected):
        raise ValueError('Whiteboard extraction did not match every visible action, owner and date')
    emit({'kind': 'actions', 'actions': actions})
    from showcase_app.gb10_accounting import validated_counts
    validated_counts(result['call_id'], images_analyzed=1)
    readout = await infer([{'role': 'system', 'content': 'Write exactly three short executive bullets from these fictional extracted actions. Preserve dates and owners, no invented facts.'},
                          {'role': 'user', 'content': json.dumps(actions)}], model=LEAD, caller='vision',
                          run_id=run_id, purpose=purpose, role='vision_readout', max_tokens=240)
    if readout['finish_reason'] != 'stop':
        raise ValueError('Executive readout was incomplete')
    output = {'seconds': time.monotonic() - began, 'actions': actions, 'readout': readout['content']}
    folder = ROOT / 'state/stage/outputs' / run_id / 'S2'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'result.json').write_text(json.dumps(output, ensure_ascii=False, indent=2))
    emit({'kind': 'readout', 'text': readout['content']})
    return output
