# HP claims register

Checked 2026-10-30. Product descriptions are sourced statements, not test results. Confirm the current SKU and region with HP before purchase. No competitive, savings, thermal, noise or unlimited-capacity claims are made.

| Wording used | Source | Qualification |
|---|---|---|
| Tower or 5U rack deployment | [HP Fury FAQ](https://www.hp.com/us-en/workstations/ai-stations/zgx-fury-ai-station.html) | FAQ describes included rails; interface asks presenters to confirm accessories/configuration. Site power requirements apply. |
| Liquid cooling, front-to-back airflow | Same product page, system design section | No measured thermal or noise claim. |
| HP Z Toolkit: discovery, remote connection, development-tool setup | [HP software](https://www.hp.com/us-en/workstations/ai-stations/zgx-ai-stations-software.html) | Supported client/VS Code prerequisites and regional availability apply. |
| HP Z Runtime: pull, serve, manage, monitor | Same software page, quick start | Available capability; not the serving stack used by this demo. Model access and size affect setup. |
| Multiple applications share local inference | docs/VERIFICATION.md and V2 acceptance | Bounded gateway/engine queues; tested workflows, not unlimited users. |
| Local execution reduces reliance on metered cloud inference | Inspected gateway/runtime settings | Setup downloads from public sources. Hardware, energy and administration remain costs. |
| Host: 256703 MiB HBM, 743.65 GiB RAM | Host nvidia-smi and /proc/meminfo, private checkpoint | Observed values; advertised coherent memory is not all GPU VRAM. |

Integration inspection: ops/runtime.py launches vLLM models, showcase_app/gateway.py admits application requests. No HP Z Runtime CLI/API or HP Z Toolkit service is invoked in this execution path. These software capabilities are informational coverage only. No infrastructure migration is part of V2.
