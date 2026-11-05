# HP claims register

Rechecked 2026-11-04. Product descriptions are sourced statements, not test results. Confirm the current SKU and region with HP before purchase. No competitive, savings, thermal, noise or unlimited-capacity claims are made.

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

## Red Hat collaboration — conference wording

The stationary Why HP screen describes an enterprise software pathway, not a deployment running on this demo. [HP's September 2026 announcement](https://www.hp.com/us-en/newsroom/press-releases/2026/hp-extends-data-center-ai-architecture-to-the-edge.html) and [Red Hat's October 2026 discussion](https://www.redhat.com/en/blog/red-hat-and-hp-empowering-physical-ai-bench-fleet) describe a planned combination of ZGX Fury and Red Hat AI Factory with NVIDIA. Enterprise lifecycle/support consistency is the stated practical direction; availability and supported configurations require confirmation. Red Hat's published reference workflow is separate evidence, not this application's acceptance test.

This host runs Ubuntu, vLLM, the existing gateway, FLUX and local speech. It does not run OpenShift or Red Hat AI and does not invoke Z Toolkit or Z Runtime. No exclusivity, certification, partner endorsement, comparative benchmark or thermal/noise advantage is invented. Only the already approved HP logo is newly reused; permission to redistribute new product photography was not established, so none was added.
