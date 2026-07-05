from fastapi import FastAPI

from app.api.routes import router

app = FastAPI(title="Procurement Approval Agent")
app.include_router(router)


def main() -> None:
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
