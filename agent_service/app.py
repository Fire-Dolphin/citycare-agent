"""The agent service. Run: uvicorn agent_service.app:app --port 8000"""

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException  # noqa: E402

from . import naive_agent  # noqa: E402
from .schemas import ChatRequest, ChatResponse  # noqa: E402

app = FastAPI(title="City Care front desk agent", version="0.1")


@app.get("/health")
async def health():
    return {"ok": True}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    # TODO: replace with: emergency check -> router -> specialist agent (all on agentcore)
    return await naive_agent.handle(req)


@app.get("/trace/{session_id}")
async def trace(session_id: str):
    # TODO: return every model call and tool call for this session, with timing, tokens and cost
    raise HTTPException(status_code=501, detail="Not built yet")
