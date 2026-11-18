"""Story-grounded fictional stage visuals and fail-closed local review."""
import base64
import io
import time
from pathlib import Path

from PIL import Image

from showcase_app.gb10_client import infer, WORKER, json_content
from showcase_app.gb10_accounting import validated_counts

COVER_BRIEF = {
    'id': 'cio-cover', 'title': 'CIO briefing cover',
    'use': 'Opening slide of the proposed Northwind planning pilot',
    'subject': 'A recognizable administrative meeting room with a table and chairs; not an abstract sculpture or clinical scene.',
    'prompt': 'Fictional healthcare administration meeting suite for a CIO pilot briefing. Human-scale oak conference table, navy chairs, oak side credenza, large windows overlooking a landscaped campus. Realistic architectural visualization, warm daylight, blue accents, wide editorial composition. Recognizable practical room, not abstract sculpture.',
}
RUSH_BRIEFS = (
    {'id': 'briefing-cover', 'title': 'CIO briefing', 'use': 'Presentation opener / account context',
     'subject': 'A recognizable landscaped institutional campus or administrative building, not an abstract sculpture.',
     'prompt': 'Fictional healthcare administration campus for a CIO planning proposal. Welcoming low-rise building, glass windows, pale stone walls, sheltered entrance, landscaped courtyard, mature trees. Human-scale architectural visualization, gentle morning light, restrained blue accents, wide editorial composition. Recognizable institutional building, not abstract sculpture.'},
    {'id': 'local-workspace', 'title': 'Private workspace', 'use': 'Local-workflow and privacy proposal illustration',
     'subject': 'A recognizable private office with a desk, chair and closed storage cabinets. There must be no computer, monitor or keyboard; not an abstract sculpture.',
     'prompt': 'Fictional private administrative workspace for a local AI pilot proposal. Tidy oak writing desk, one navy upholstered chair, closed floor-to-ceiling wooden storage cabinets, frosted glass partition, large daylight window. Entirely empty desk. No electronics, screens or printed objects. Realistic human-scale architectural visualization, warm wood and restrained blue accents. Private work setting, not sculpture.'},
    {'id': 'team-workshop', 'title': 'Team workshop', 'use': 'Technical workshop invitation background',
     'subject': 'A recognizable collaborative meeting or training room with a table and chairs, not an abstract sculpture.',
     'prompt': 'Fictional healthcare administration workshop room for a planning invitation. Oval oak discussion table, six navy chairs, entirely blank wall whiteboard, broad windows, natural daylight. Practical human-scale collaborative room, realistic architectural visualization, restrained blue and warm ivory palette. Recognizable furniture, not abstract sculpture.'},
    {'id': 'pilot-planning', 'title': 'Pilot planning', 'use': 'Pilot checklist / follow-up document background',
     'subject': 'Recognizable everyday planning stationery such as a notebook, folder, blank cards and pen on a desk; not an abstract sculpture.',
     'prompt': 'Fictional pilot-planning desk for a follow-up document background. Overhead editorial illustration: entirely blank open notebook, two plain blue document folders, four completely blank ivory note cards, unmarked pen, warm oak tabletop. Familiar practical stationery, realistic paper grain, natural daylight, clear space for copy. Not abstract sculpture.'},
)
COVER_PROMPT = COVER_BRIEF['prompt']
RUSH_PROMPTS = tuple(brief['prompt'] for brief in RUSH_BRIEFS)
RUSH_PROMPT = RUSH_PROMPTS[0]
# Free Mode retains its original conservative user-prompt guard.
NO_LETTERING = ' Every surface is blank and unmarked. Absolutely no text, letters, numbers, words, captions, labels, symbols, logos, signatures, watermarks or fake writing in any language, even tiny or unreadable. No screens, keyboards, cards, documents, signs, charts, packaging or printed objects. No people.'
STAGE_NO_LETTERING = ' Every surface is blank and unmarked. Absolutely no text, letters, numbers, logos, labels, watermarks or fake writing, even tiny. No screens, keyboards, signage, charts, people, patients or medical equipment. All paper and whiteboards entirely blank. Original fictional concept, no real facility or deployment claim.'
STAGE_CONDITIONING_TOKENS = 256
TEXT_SCHEMA = {'type': 'object', 'properties': {'text': {'type': 'boolean'}}, 'required': ['text'], 'additionalProperties': False}
STAGE_REVIEW_SCHEMA = {'type': 'object', 'properties': {'text': {'type': 'boolean'}, 'relevant': {'type': 'boolean'}},
                       'required': ['text', 'relevant'], 'additionalProperties': False}


def stage_brief(batch, index=0):
    """Approved visual deliverables for the fixed fictional presenter story."""
    if batch not in (1, 4):
        raise ValueError('Unsupported stage artwork batch')
    if not 0 <= index < batch:
        raise ValueError('Invalid artwork index')
    return dict(COVER_BRIEF if batch == 1 else RUSH_BRIEFS[index])


def stage_prompt(batch, index=0):
    return stage_brief(batch, index)['prompt'] + STAGE_NO_LETTERING


def vision_payload(path):
    path = Path(path)
    data = path.read_bytes()
    mime = 'image/png'
    if len(data) > 700000:
        # Encode the review input only; accepted output pixels are untouched.
        with Image.open(io.BytesIO(data)) as picture:
            buffer = io.BytesIO()
            picture.convert('RGB').save(buffer, format='JPEG', quality=96)
        data, mime = buffer.getvalue(), 'image/jpeg'
    if len(data) > 700000:
        raise ValueError('Artwork exceeds the bounded full-resolution text-check input')
    return 'data:' + mime + ';base64,' + base64.b64encode(data).decode()


async def check_artwork(path, run_id, purpose, *, brief=None):
    began = time.monotonic()
    instruction = 'Inspect the ENTIRE artwork, including tiny markings on objects and in corners. Does it contain any printed or handwritten lettering, numbers, logos, captions, labels, or fake unreadable writing? Gibberish spelling still counts as writing. Plain objects and shapes alone do not count as writing. If uncertain about a marking, count it as writing. Do not transcribe or describe the image.'
    schema = STAGE_REVIEW_SCHEMA if brief else TEXT_SCHEMA
    if brief:
        instruction += ' Also check the visual brief: ' + brief['subject'] + ' Set relevant=true only when the visible scene matches that subject. An unrelated abstract sculpture must be relevant=false. Return only JSON with boolean text and relevant.'
    else:
        instruction += ' Return only JSON {"text":true} when any writing is present, otherwise {"text":false}.'
    result = await infer([{'role': 'user', 'content': [
        {'type': 'image_url', 'image_url': {'url': vision_payload(path)}},
        {'type': 'text', 'text': instruction}]}],
        model=WORKER, caller='vision', run_id=run_id, purpose=purpose, role='image_text_check',
        max_tokens=32 if brief else 8 if purpose == 'keepalive' else 24,
        response_format={'type': 'json_schema', 'json_schema': {'name': 'artwork_text_check', 'strict': True, 'schema': schema}})
    value = json_content(result['content'])
    if not isinstance(value, dict) or set(value) != set(schema['properties']) or any(type(v) is not bool for v in value.values()):
        raise ValueError('Local artwork text check returned an invalid result')
    validated_counts(result['call_id'], images_analyzed=1)
    return {**value, 'model': result['model'], 'seconds': time.monotonic() - began,
            'call_id': result['call_id']}
