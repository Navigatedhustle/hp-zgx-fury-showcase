"""The author/review endpoint split.

A second review model (its own server, or its own label behind one gateway URL) is optional — leaving VLM_BASE_URL empty must keep the single-server setup working
byte for byte — so what matters here is that the fallbacks collapse correctly, that a call goes to the
server its role names, and that what one server learns about itself never leaks onto the other.
"""
import asyncio
import os
from contextlib import contextmanager

import pytest
from app.config import Role, settings
from app.llm import client as llm


@contextmanager
def env(**kw):
    """Set env vars, rebuild settings and drop every cached client/probe for the duration."""
    prev = {k: os.environ.get(k) for k in kw}
    os.environ.update({k: v for k, v in kw.items() if v is not None})
    for k, v in kw.items():
        if v is None:
            os.environ.pop(k, None)
    settings.cache_clear()
    llm.reset()
    try:
        yield settings()
    finally:
        for k, v in prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        settings.cache_clear()
        llm.reset()


AUTHOR = {"LLM_BASE_URL": "http://author:8080/v1", "LLM_API_KEY": "akey", "LLM_MODEL": "author-model"}
SPLIT = {**AUTHOR, "VLM_BASE_URL": "http://review:8081/v1", "VLM_API_KEY": "rkey", "VLM_MODEL": "review-model"}


# ---------------------------------------------------------------- configuration
def test_an_empty_review_endpoint_falls_back_to_the_authoring_one():
    """The whole point of the fallbacks: a deployment that never heard of VLM_* is unchanged."""
    with env(**AUTHOR, VLM_BASE_URL=None, VLM_API_KEY=None, VLM_MODEL=None) as s:
        a, r = s.endpoint(Role.author), s.endpoint(Role.review)
        assert (r.base_url, r.api_key, r.model) == (a.base_url, a.api_key, a.model)
        assert s.split_endpoints is False


def test_each_review_field_falls_back_on_its_own():
    """A second model behind the *same* URL is a real setup (a ZRT gateway): only VLM_MODEL is set, and it is a split."""
    with env(**AUTHOR, VLM_BASE_URL=None, VLM_API_KEY=None, VLM_MODEL="review-model") as s:
        r = s.endpoint(Role.review)
        assert (r.base_url, r.api_key, r.model) == (AUTHOR["LLM_BASE_URL"], "akey", "review-model")
        assert s.split_endpoints is True, "one URL can front several models; a different model is a different engine"


def test_a_separate_base_url_is_a_split():
    with env(**SPLIT) as s:
        a, r = s.endpoint(Role.author), s.endpoint(Role.review)
        assert (a.base_url, a.api_key, a.model) == ("http://author:8080/v1", "akey", "author-model")
        assert (r.base_url, r.api_key, r.model) == ("http://review:8081/v1", "rkey", "review-model")
        assert s.split_endpoints is True


def test_vision_model_still_answers_for_anything_reading_the_old_name():
    with env(**AUTHOR, VLM_MODEL=None) as s:
        assert s.vision_model == "author-model"
    with env(**AUTHOR, VLM_MODEL="review-model") as s:
        assert s.vision_model == "review-model"


# ---------------------------------------------------------------- routing
class _FakeCompletions:
    def __init__(self, log, tag):
        self._log, self._tag = log, tag

    async def create(self, **kw):
        self._log.append((self._tag, kw["model"]))
        raise RuntimeError("stop here — the routing is all this test needs")


class _FakeClient:
    def __init__(self, log, tag):
        self.chat = type("C", (), {"completions": _FakeCompletions(log, tag)})()


def _route(monkeypatch, **envkw):
    """Send one chat per role and report (base_url, model) for each."""
    log: list[tuple[str, str]] = []
    with env(**envkw):
        monkeypatch.setattr(llm, "_client", lambda ep=None: _FakeClient(log, (ep or llm.endpoint()).base_url))

        async def go():
            for role in (Role.author, Role.review):
                with pytest.raises(RuntimeError):
                    await llm.chat([{"role": "user", "content": "hi"}], role=role, retries=0)

        asyncio.run(go())
    return log


def test_each_role_calls_its_own_server_with_its_own_model(monkeypatch):
    author, review = _route(monkeypatch, **SPLIT)
    assert author == ("http://author:8080/v1", "author-model")
    assert review == ("http://review:8081/v1", "review-model")


def test_without_a_split_both_roles_share_one_server(monkeypatch):
    author, review = _route(monkeypatch, **AUTHOR, VLM_BASE_URL=None, VLM_API_KEY=None, VLM_MODEL=None)
    assert author == review == ("http://author:8080/v1", "author-model")


def test_the_default_role_is_authoring(monkeypatch):
    """Every pre-existing call site passes no role, and must keep reaching the authoring server."""
    log: list[tuple[str, str]] = []
    with env(**SPLIT):
        monkeypatch.setattr(llm, "_client", lambda ep=None: _FakeClient(log, (ep or llm.endpoint()).base_url))

        async def go():
            with pytest.raises(RuntimeError):
                await llm.chat([{"role": "user", "content": "hi"}], retries=0)

        asyncio.run(go())
    assert log == [("http://author:8080/v1", "author-model")]


# ---------------------------------------------------------------- isolation
def test_one_servers_guided_refusal_does_not_disable_the_other():
    """Two vLLM builds can differ. Remembering a refusal globally would cost the working server its schema."""
    with env(**SPLIT):
        llm._S.server(llm.endpoint(Role.review).key).guided = False
        assert llm.guided_json_enabled(Role.review) is False
        assert llm.guided_json_enabled(Role.author) is True
        assert llm.guided_json_state(Role.review) is False
        assert llm.guided_json_state(Role.author) is None


def test_one_servers_context_window_does_not_trim_the_others():
    """The review model is served with a much smaller window; the authoring prompt must not be cut to fit it."""
    with env(**SPLIT):
        llm._S.server(llm.endpoint(Role.review).key).max_model_len = 32768
        llm._S.server(llm.endpoint(Role.author).key).max_model_len = 65536
        assert asyncio.run(llm.context_limit(Role.author)) == 65536
        assert asyncio.run(llm.context_limit(Role.review)) == 32768


def test_two_models_behind_one_url_keep_their_own_state():
    """A gateway routes by `model`: the review model must not inherit the author's context window or refusals."""
    with env(**AUTHOR, VLM_BASE_URL=None, VLM_MODEL="review-model"):
        llm._S.server(llm.endpoint(Role.author).key).guided = False
        llm._S.server(llm.endpoint(Role.author).key).max_model_len = 65536
        llm._S.server(llm.endpoint(Role.review).key).max_model_len = 32768
        assert llm.guided_json_enabled(Role.review) is True
        assert asyncio.run(llm.context_limit(Role.review)) == 32768


def test_sharing_a_url_and_model_means_sharing_the_learned_state():
    """The flip side: one model is one model, however many roles point at it."""
    with env(**AUTHOR, VLM_BASE_URL=None, VLM_API_KEY=None, VLM_MODEL=None):
        llm._S.server(llm.endpoint(Role.author).key).guided = False
        assert llm.guided_json_enabled(Role.review) is False
