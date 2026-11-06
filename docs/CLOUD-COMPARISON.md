# Fury electricity and frontier API comparison

The Cloud vs Local page (`/economics`) now leads with an interactive horizontal bar chart. All bars share a linear USD axis starting at zero, with exact values visible alongside them. Power, hours, tariff and monthly workload are editable; changing them updates the chart and preserves the existing detailed calculator and measured event-energy readout.

The local bar is **estimated whole-Fury electricity**, using the presenter's average system power, runtime and tariff. The initial 1,200 W / 40 hours / $0.25 per kWh are explicitly illustrative assumptions, not wall-meter measurements or a local tariff claim. Runtime must cover the entered workload. Hardware, support, cooling outside the supplied power scope and client-device costs are excluded. Electricity is not total ownership cost.

Cloud bars include the text API estimate plus the same configured image/video-generation services. Provider electricity is bundled into the API charge; providers do not publish a separate per-request electricity charge to add. No artificial cloud power surcharge or energy split is invented. Tokenizers, reasoning usage, throughput, quality and task success differ; these are cost scenarios, not measured output equivalence or a model popularity ranking.

## Rates checked 6 November 2026

| Representative model | Standard input / 1M USD | Standard output / 1M USD | Official source |
|---|---:|---:|---|
| GPT-6 Astra | 10 | 50 | [OpenAI model page](https://developers.openai.com/api/docs/models/gpt-6-astra) and [pricing](https://developers.openai.com/api/docs/pricing) |
| Claude Fable 5.1 | 10 | 50 | [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing) |
| Claude Opus 5.5 | 4 | 20 | [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing) |
| Gemini 4 Argon | 2 | 10 | [Google pricing](https://aistudio.google.com/docs/pricing#gemini-4-argon) |

Gemini's promotional $2 / $10 rates expire after 30 November 2026; the server uses $4 / $20 from 1 December. Existing per-request long-context pricing remains intact for event repricing. Monthly items use the displayed short-request assumptions. No prompt-cache, batch or regional discounts, taxes or paid tools are inferred. All prices are cached locally; visitors make no cloud inference or price-fetch calls.

For the initial monthly example, 10,000 chats, 5,000 vision inputs and 1,000 translated pages represent 25.9 million assumed input and 8.9 million assumed output tokens. Image generation adds $40 (1,000 × $0.04) and video adds $100 (1,000 seconds × $0.10). These shared Imagen 4 / Veo 3.1 Fast assumptions and their official sources remain visible in the calculator. The resulting cloud rows are $844.00, $844.00, $421.60 and $280.80. The local example is 1.2 kW × 40 hours × $0.25 = **$12.00** for 48 kWh. This arithmetic does not establish that the machine can finish any arbitrary workload in 40 hours.

## Verification

Five independent arithmetic tests cover token/media reconciliation, zero versus unavailable electricity, promotion-expiry inputs and numeric overflow. Existing fifteen event accounting/pricing tests pass. Real Chromium and Firefox checks cover dark/light themes at six viewport sizes (24 combinations), visible exact values, changed runtime, zero/missing tariff and changed workload. Browser exceptions and failed HTTP resources were absent. Screenshots were visually inspected in dark/light and mobile layouts. The retained operator's four-model prices and cumulative chart were also checked. No model engines, inference admission, privacy retention or service lifecycle settings changed.
