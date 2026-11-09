import pytest

from showcase_app.gb10_miniapp import CSP, preview_document, secure_html


def test_opaque_iframe_and_no_network_policy_are_both_present():
    source = secure_html('<html><body><p>Original local calculator</p><script>let n=1;</script></body></html>')
    document = preview_document(source)
    assert 'sandbox="allow-scripts"' in document
    assert 'allow-same-origin' not in document
    assert "connect-src 'none'" in CSP
    assert "frame-src 'none'" in CSP
    assert 'Content-Security-Policy' in source
    assert '&lt;html&gt;' in document


@pytest.mark.parametrize('payload', [
    '<iframe srcdoc="<script>1</script>"></iframe>',
    '<img src="https://example.invalid/pixel">',
    '<script>fetch("http://example.invalid")</script>',
    '<base href="/">',
    '<style>body{background:url(/asset)}</style>',
])
def test_generated_resources_and_nested_frames_are_rejected(payload):
    with pytest.raises(ValueError):
        secure_html('<html><body>' + payload + '</body></html>')
