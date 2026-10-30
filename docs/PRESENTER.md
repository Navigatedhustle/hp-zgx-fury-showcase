# Presenter guide

Open the home page, then choose Demos for direct launch actions. All examples use fictional data. Ask the customer which task and operating constraint matters first.

1. Atlas: copy the forecast question. Inspect grounding, compare a scenario, export PNG/PDF. Explain that inference supports the analytical tools; a fluent answer still needs review.
2. Presentations: use the catalog brief, generate three slides, inspect preview, download/edit the PPTX. Explain the first-draft use case.
3. Agent Factory: start automatic short travel mode. Inspect real model requests, tasks and tests. Show the application and backend. Complete mode supplies its frontend and generates backend/QA; disclose that. A prebuilt reference is never a new generation.
4. Image Studio: use the botanical prompt. Inspect/download the image. Discuss quality and human review.

For shared AI, start the Factory build first, then submit the other three workflows while it generates. Separate sessions retain ownership; one Factory build is admitted globally. Show actual activity in Operator. Simultaneous submission is not proof of backend overlap; the acceptance harness records execution intervals.

Talk track: “Which of these tasks would benefit from local model access? Where would the system sit? Who operates its models? What must be tested before deployment?” Use Why HP ZGX Fury for the sourced system/software discussion. Toolkit/Runtime are available HP capabilities; this demo runs its existing gateway/vLLM stack.

Before a session, run ./launch.sh status; confirm all ten ready and no prior active Factory job. Never cancel another user's work. Factory reconnects in the same browser session; its Stop button cancels only that session's run. Capacity errors are expected when another build owns the system. Inspect error evidence before retrying.

Recovery: ./launch.sh diagnostics, then guarded ./launch.sh recover agent once idle. Do not restart the entire model stack to recover a tab. Health alone does not prove successful generation. Keep access private. Physical microphone/speaker and remote browser permissions depend on the presenting device.

Expected timing varies with input, caches and queues. Allow several minutes for short development; complete travel takes longer. See VERIFICATION.md and V2-VERIFICATION.md for observed results and scope.
