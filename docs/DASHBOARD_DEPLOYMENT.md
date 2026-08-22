# Dashboard Deployment Guide

This dashboard runs locally by default, but it can be deployed publicly.

## Local Run

```bash
python launch_dashboard.py
# or directly:
streamlit run dashboard/app_modern.py --server.port 8501
```

- Local URL: `http://localhost:8501`
- Same-network URL: shown by Streamlit (for devices on your LAN)

## Option 1: Streamlit Community Cloud

1. Push this repository to GitHub.
2. Set app entrypoint to:
   - `dashboard/app_modern.py`
3. Deploy.

## Option 2: Render (Web Service)

1. Create a new Web Service from this repository.
2. Build command:

```bash
pip install -r requirements.txt
```

3. Start command:

```bash
streamlit run dashboard/app_modern.py --server.port $PORT --server.address 0.0.0.0
```

## Option 3: Docker

Use the existing `Dockerfile` and expose Streamlit port.

Example runtime command:

```bash
docker run -p 8501:8501 -e CENSUS_API_KEY=... <image_name>
```

Then open `http://localhost:8501`.

## Production Notes

- Prefer precomputed outputs in `outputs/results` for fast dashboard responses.
- Keep API keys out of source control.
- Add auth (reverse proxy or platform-level access control) for non-public deployments.
