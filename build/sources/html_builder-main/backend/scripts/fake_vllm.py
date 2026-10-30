"""Fake OpenAI-compatible server that imitates vLLM, to exercise the real (non-mock) pipeline path offline.

  python scripts/fake_vllm.py            -> http://127.0.0.1:8799/v1

It returns gold-example specs and deliberately misbehaves in the ways the pipeline must survive:

  * slide 2, variant A  -> a first draft that overflows the stage      (exercises the QA repair loop)
  * slide 3, variant B  -> one unusable, untagged reply                (exercises the format retry)
  * slide 4, variant A  -> one HTTP 400 "maximum context length"       (exercises the trim-and-retry)
  * the first critic call fails the slide, the second passes           (exercises critic-driven repair)

Guided decoding is emulated too, both ways. By default the server accepts `extra_body={"guided_json": ...}`,
counts it and (for the JSON stages) answers with a clean object; start it with `--no-guided`, or POST
`/_guided {"supported": false}`, and it answers the way a server without structured output does — an HTTP 400
naming the field — which is the path the client has to survive without taking the pipeline down with it.

`backend/tests/test_llm.py` drives this in-process; `GET /_stats` exposes the counters it asserts on.
"""
import json
import re
import sys
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.skillpack import examples  # noqa: E402

app = FastAPI()
_COUNTERS = {"n": 0, "repairs": 0, "critic": 0, "plan": 0, "judge": 0, "ab": 0, "generate": 0, "images": 0,
             "plan_images": 0, "format_retry": 0, "context_400": 0, "guided": 0, "guided_refused": 0}
calls = {**_COUNTERS, "systems": [], "guided_schemas": []}
guided = {"supported": True}  # flipped by /_guided to imitate a server without structured output
EX = examples()
A = [e for e in EX if e.variant == "A"]
B = [e for e in EX if e.variant == "B"]
MAX_MODEL_LEN = 65536


def reset() -> None:
    calls.update({**_COUNTERS, "systems": [], "guided_schemas": []})
    for k in ("bad3", "big4"):
        calls.pop(k, None)


def reply(text: str, prompt_tokens: int = 1000):
    return {"id": f"c{calls['n']}", "object": "chat.completion", "created": int(time.time()), "model": "fake",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": text}}],
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": len(text) // 4, "total_tokens": prompt_tokens + len(text) // 4}}


def context_error(tokens: int):
    """What vLLM answers when the prompt does not fit: a plain 400 whose body names the limit."""
    return JSONResponse(status_code=400, content={"object": "error", "type": "BadRequestError", "code": 400,
                                                  "message": f"This model's maximum context length is {MAX_MODEL_LEN} tokens. "
                                                             f"However, you requested {tokens} tokens. "
                                                             "Please reduce the length of the messages."})


def last_text(messages) -> tuple[str, int]:
    m = messages[-1]
    c = m["content"]
    if isinstance(c, list):
        imgs = sum(1 for p in c if p.get("type") == "image_url")
        return " ".join(p.get("text", "") for p in c if p.get("type") == "text"), imgs
    return c, 0


@app.get("/_stats")
def stats():
    return calls


@app.post("/_reset")
def do_reset():
    reset()
    return {"ok": True}


@app.post("/_guided")
async def set_guided(req: Request):
    """Turn structured output on or off at runtime, so one test can drive both branches."""
    guided["supported"] = bool((await req.json()).get("supported", True))
    return dict(guided)


def guided_refusal():
    """What an OpenAI-compatible server WITHOUT guided decoding answers: the request is rejected outright,
    with the offending field named. vLLM before structured-output support, llama.cpp and LM Studio all do
    some version of this, which is why the client has to fall back instead of failing the stage."""
    return JSONResponse(status_code=400, content={"object": "error", "type": "BadRequestError", "code": 400,
                                                  "message": "[{'type': 'extra_forbidden', 'loc': ('body', 'guided_json'), "
                                                             "'msg': 'Extra inputs are not permitted'}]"})


@app.get("/v1/models")
def models():
    return {"object": "list", "data": [{"id": "fake", "object": "model", "owned_by": "vllm", "max_model_len": MAX_MODEL_LEN}]}


@app.post("/v1/chat/completions")
async def chat(req: Request):
    body = await req.json()
    calls["n"] += 1
    schema = body.get("guided_json")
    if schema is not None:
        if not guided["supported"]:
            calls["guided_refused"] += 1
            return guided_refusal()
        calls["guided"] += 1
        keys = ",".join(sorted((schema.get("properties") or {}).keys()))
        if keys not in calls["guided_schemas"]:
            calls["guided_schemas"].append(keys)
    text, imgs = last_text(body["messages"])
    calls["images"] += imgs
    if "could not be used" in text:  # format retry: the task is in the first user message
        calls["format_retry"] += 1
        first_user = next(m for m in body["messages"] if m["role"] == "user")
        text, imgs = last_text([first_user])
        assert not any(m["role"] == "assistant" for m in body["messages"]), "the unusable reply must not be echoed back"
    assert body["messages"][0]["role"] in ("system", "user")
    sys_text = body["messages"][0]["content"] if body["messages"][0]["role"] == "system" else ""
    sys_len = len(sys_text)
    if sys_text and sys_text not in calls["systems"]:
        calls["systems"].append(sys_text)  # every distinct system prefix this process has been sent
    if "What colour is this image" in text:
        return reply("Blue")
    if "Task: plan the deck" in text:
        calls["plan"] += 1
        calls["plan_images"] += imgs
        idx = [int(x) for x in re.findall(r"### Slide (\d+)", text)]
        pats = ["title", "cards", "cards", "chart", "process"]
        # a guided reply is pure JSON; an unguided one is whatever the model felt like, which is the case
        # extract_json exists for
        return reply(("" if schema else "<think>considering the arc</think>") + json.dumps({
            "deck_title": "Fake planned deck", "audience": "IT security leaders", "tone": "Direct", "narrative": "Risk, protection, proof, rollout.",
            "slides": [{"index": i, "role": "other", "pattern": pats[(i - 1) % len(pats)], "eyebrow": "Section", "headline": f"Planned headline {i}",
                        "key_message": "msg", "idea_a": f"spotlight {i}", "idea_b": f"grid {i}", "theme": "light", "include": True} for i in idx]}), sys_len // 3)
    if "Task: review a rendered slide" in text:
        calls["critic"] += 1
        assert imgs >= 1, "critic must receive screenshots"
        if calls["critic"] == 1:
            return reply('{"scores":{"layout":5,"hierarchy":7,"brand":8,"fidelity":8,"craft":6,"interaction":7},'
                         '"branches":{"intention":7,"static_quality":5,"dynamic_behavior":7},'
                         '"issues":[{"severity":"high","area":"layout","problem":"cards crowd the bottom","fix":"reduce copy"}],"verdict":"fix"}')
        clean = ('{"scores":{"layout":8,"hierarchy":8,"brand":9,"fidelity":8,"craft":8,"interaction":8},'
                 '"branches":{"intention":8,"static_quality":8,"dynamic_behavior":8},"issues":[],"verdict":"pass"}')
        return reply(clean if schema else f"```json\n{clean}\n```")
    if "Task: compare a candidate slide to a reference slide" in text:
        calls["judge"] += 1
        assert imgs >= 2, "judge must receive both slides"
        assert "image 1 = " in text, "the judge must be told which image is which"
        return reply('{"relative_quality": 86, "better": "reference", "gaps": ["tighter card rhythm in the reference"]}')
    if "Task: choose between two variants of the same slide" in text:
        calls["ab"] += 1
        assert imgs >= 2, "the pairwise judge must receive both variants"
        # answer positionally (always "the first image") so a caller that never swaps the order shows up as a
        # perfectly one-sided verdict across a deck
        first = re.search(r"image 1 = variant ([AB])", text)
        assert first, "the pairwise judge must be told which image is which variant"
        return reply(json.dumps({"winner": first.group(1), "confidence": 70, "reason": "the first image reads faster"}))
    if "Task: fix this slide" in text:
        calls["repairs"] += 1
        assert "Issues to fix" in text
        return reply(A[1].output if "variant A" in text else B[1].output)
    m = re.search(r"Task: write slide (\d+) of \d+ as variant ([AB])", text)
    if m or "Task: revise slide" in text:
        calls["generate"] += 1
        pos = int(m.group(1)) if m else 1
        variant = m.group(2) if m else "A"
        pool = A if variant == "A" else B
        out = pool[pos % len(pool)].output
        if pos == 4 and variant == "A" and calls.get("big4") is None:  # prompt too long once -> trim and retry
            calls["big4"] = 1
            calls["context_400"] += 1
            return context_error(MAX_MODEL_LEN + 4096)
        if pos == 2 and variant == "A":  # broken first draft: overflowing text -> repair loop
            out = out.replace("<html>", '<html><p style="position:absolute;left:1400px;top:300px;width:600px;font-size:30px">This text overflows the stage</p>', 1)
        if pos == 3 and variant == "B" and calls.get("bad3") is None:  # unusable reply first -> format retry
            calls["bad3"] = 1
            return reply("Sure! Here is a great slide design for you.")
        return reply(out, sys_len // 3)
    return reply("unrecognised prompt")


if __name__ == "__main__":
    guided["supported"] = "--no-guided" not in sys.argv
    uvicorn.run(app, host="127.0.0.1", port=8799, log_level="warning")
