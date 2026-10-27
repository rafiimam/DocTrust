"""DocTrust backend — FastAPI entry point.

Day-1 scaffold: health check only. The agent loop (segment -> read ->
perturbation uncertainty -> investigate -> normalize -> cross-examine ->
verdict) lands here during the hackathon building period.
"""

from fastapi import FastAPI

app = FastAPI(title="DocTrust", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "doctrust"}
