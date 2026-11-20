# Frontend

The runnable [Hong Kong live panel](live_markets/README.md) is in
`live_markets/`. Run the root `Start HK Dashboard.command`, or
`python -B -m src.hk.dashboard serve` in the project Python environment.
It reads the existing HK collector and refreshes every five seconds.
The static build and later AWS setup are documented there.

`reddit_dashboard/` is the existing team attention dashboard. Its files are
preserved; the live panel uses the same plain HTML/CSS/JS framework.

---

This folder is for the UI/UX portion of the project. Typical contents may include:

- React, Vue, or plain HTML/CSS/JS code
- static assets for dashboards or visualizations
- frontend build configuration
- a README describing how to run and deploy the web interface
