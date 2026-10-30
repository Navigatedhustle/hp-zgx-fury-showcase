# Prebuilt reference: Aster Journeys

This is an existing completed Agent Factory backend from this workstation, copied as source only. The frontend is the openly supplied maintained portal, using vector destination illustrations in place of excluded private runtime imagery. It is **not a new live generation** and contains no customer records, database, model response logs, or sessions.

Run `./launch.sh setup` at the repository root, then `./.venv/bin/python examples/reference-travel/serve.py`. Open **http://localhost:8510**. The page is permanently labeled PREBUILT REFERENCE. It never submits an Agent Factory generation run. Data is initialized in `state/reference-travel/` on the first request. Public fictional administrator: `admin@example.test` / `DemoAdmin2028!`; never use real credentials here.

Use the dashboard Agent Factory link to generate a **new** application using the resident DeepSeek lead and Qwen specialists. The complete-travel mode explicitly discloses its supplied frontend foundation; DeepSeek generates backend modules and QA; Qwen is reserved for frontend repair tasks when required. The short mode generates its frontend too.

Stop its foreground server with Ctrl+C. To verify the reference through an actual browser and isolated backend, run `.venv/bin/python ops/acceptance/reference.py` from the repository root while its server is running. This test creates fictional accounts and reservations in the reference database.
