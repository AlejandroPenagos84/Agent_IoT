import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "auth.http.app:create_app",
        factory=True,
        host=os.getenv("AUTH_API_HOST", "0.0.0.0"),
        port=int(os.getenv("AUTH_API_PORT", "8001")),
    )
