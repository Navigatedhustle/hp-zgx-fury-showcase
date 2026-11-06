import base64
import io
import pytest
from PIL import Image
from showcase_app.creative import reference_image


def test_reference_is_decoded_without_a_file_or_remote_fetch():
    raw = io.BytesIO()
    Image.new('RGB', (32, 24), '#173c34').save(raw, format='PNG')
    image = reference_image('data:image/png;base64,' + base64.b64encode(raw.getvalue()).decode())
    assert image.size == (32, 24)
    assert image.mode == 'RGB'
    image.close()


@pytest.mark.parametrize('data', ['https://example.com/image.png', '/etc/passwd', 'data:image/png;base64,not-valid-base64', 'data:text/plain;base64,eA=='])
def test_reference_rejects_paths_urls_and_invalid_encodings(data):
    with pytest.raises((ValueError, OSError)):
        reference_image(data)
