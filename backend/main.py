from fastapi import FastAPI
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from agents.agentWorkflow import initialize_agent, run_agent

app = FastAPI()

origins = [
    "*",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

initialize_agent()


@app.get("/")
def read_root():
    return {"status": "Okay", "message": "Leave Application AI Agent Server is Running."}


@app.post("/leaves/apply")
def apply_leaves(application: str):
    print(application)
    result = run_agent(application)
    return result


def main():
    print("Hello from leave-application-agent!")

    uvicorn.run(app, host="0.0.0.0", port=7007)


if __name__ == "__main__":
    main()
