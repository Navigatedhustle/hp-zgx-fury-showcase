"""Wordless stage artwork: fixed visual direction and fail-closed local review."""
import base64
import io
import time
from pathlib import Path

from PIL import Image

from showcase_app.gb10_client import infer, WORKER, json_content
from showcase_app.gb10_accounting import validated_counts

COVER_PROMPT = 'Original architectural studio still life: a single sweeping cobalt blue anodized aluminum ribbon suspended between two solid precision-machined silver blocks on an obsidian plinth. Monumental sculptural composition, beautifully controlled broad reflections, fine brushed-metal grain, unmarked surfaces, deep midnight navy studio, pale periwinkle rim light, confident negative space. Museum-quality product photography of an abstract sculpture, exquisitely detailed physical materials.'
RUSH_PROMPTS = (
    'Original studio material study: one continuous cobalt blue anodized metal ribbon folding through a polished silver arch. Strong sculptural silhouette, unmarked surfaces, obsidian stage, deep navy background, broad softbox reflections, meticulous product photography.',
    'Original studio material study: a monumental matte cobalt blue ceramic ring with a brushed silver sphere resting inside its aperture. Asymmetric editorial composition, unmarked surfaces, dark navy studio, pale periwinkle edge light, refined physical material detail.',
    'Original studio material study: three cantilevered solid slabs of cobalt anodized aluminum and satin ivory ceramic, balanced with architectural precision above an obsidian base. Unmarked surfaces, deep navy studio, controlled grazing light, exquisite machined edges.',
    'Original studio material study: two interlocking sculptural arches, one cobalt blue ceramic and one brushed silver aluminum, a clean continuous silhouette. Unmarked surfaces, dark navy stage, broad studio reflections, restrained periwinkle edge light, extraordinary material realism.',
)
RUSH_PROMPT = RUSH_PROMPTS[0]
NO_LETTERING = ' Every surface is blank and unmarked. Absolutely no text, letters, numbers, words, captions, labels, symbols, logos, signatures, watermarks or fake writing in any language, even tiny or unreadable. No screens, keyboards, cards, documents, signs, charts, packaging or printed objects. No people.'
TEXT_SCHEMA = {'type': 'object', 'properties': {'text': {'type': 'boolean'}}, 'required': ['text'], 'additionalProperties': False}


def stage_prompt(batch, index=0):
    """The trusted stage tool applies this documented house art direction."""
    if batch not in (1, 4):
        raise ValueError('Unsupported stage artwork batch')
    if not 0 <= index < batch:
        raise ValueError('Invalid artwork index')
    return (COVER_PROMPT if batch == 1 else RUSH_PROMPTS[index]) + NO_LETTERING


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


async def check_artwork(path, run_id, purpose):
    began = time.monotonic()
    result = await infer([{'role': 'user', 'content': [
        {'type': 'image_url', 'image_url': {'url': vision_payload(path)}},
        {'type': 'text', 'text': 'Inspect the ENTIRE artwork, including tiny markings on objects and in corners. Does it contain any printed or handwritten lettering, numbers, logos, captions, labels, or fake unreadable writing? Gibberish spelling still counts as writing. Plain abstract shapes alone do not count. If uncertain about a marking, count it as writing. Return only JSON {"text":true} when any writing is present, otherwise {"text":false}. Do not transcribe or describe the image.'}]}],
        model=WORKER, caller='vision', run_id=run_id, purpose=purpose, role='image_text_check',
        max_tokens=8 if purpose == 'keepalive' else 24,
        response_format={'type': 'json_schema', 'json_schema': {'name': 'artwork_text_check', 'strict': True, 'schema': TEXT_SCHEMA}})
    value = json_content(result['content'])
    if not isinstance(value, dict) or set(value) != {'text'} or type(value['text']) is not bool:
        raise ValueError('Local artwork text check returned an invalid result')
    validated_counts(result['call_id'], images_analyzed=1)
    return {'text': value['text'], 'model': result['model'], 'seconds': time.monotonic() - began,
            'call_id': result['call_id']}
