from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.database import engine, Base
import app.models.models
from app.api import auth,projects, variables, history

# Initialize tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="EnvShare API",
    description="Secure internal portal for managing team environment variables",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(variables.router)
app.include_router(history.router)
@app.get("/health")
def health_check():
    return {"status": "ok", "app": "EnvShare"}