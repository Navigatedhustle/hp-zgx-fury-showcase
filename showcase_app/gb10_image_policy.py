"""Wordless stage artwork: fixed visual direction and fail-closed local review."""
import base64
import io
import time
from pathlib import Path

from PIL import Image

from showcase_app.gb10_client import infer, WORKER, json_content
from showcase_app.gb10_accounting import validated_counts

COVER_PROMPT = 'Original minimalist editorial landscape of gently rolling cobalt blue dunes and pale periwinkle hills. Smooth matte unmarked surfaces, soft studio light, plain light background. Purely abstract visual artwork.'
RUSH_PROMPT = 'Original minimalist abstract landscape of flowing cobalt blue waves and softly layered pale periwinkle hills. Smooth matte unmarked surfaces, soft studio light, plain light background. Purely visual artwork.'
NO_LETTERING = ' Every surface is blank and unmarked. Absolutely no text, letters, numbers, words, captions, labels, symbols, logos, signatures, watermarks or fake writing in any language, even tiny or unreadable. No screens, keyboards, cards, documents, signs, charts, packaging or printed objects. No people.'
TEXT_SCHEMA = {'type': 'object', 'properties': {'text': {'type': 'boolean'}}, 'required': ['text'], 'additionalProperties': False}


def stage_prompt(batch):
    """The trusted stage tool applies this documented house art direction."""
    if batch not in (1, 4):
        raise ValueError('Unsupported stage artwork batch')
    return (COVER_PROMPT if batch == 1 else RUSH_PROMPT) + NO_LETTERING


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
