from fastapi import FastAPI

from api.blinkit_api.blinkit_api import router as blinkit_router
from api.zepto_api.zepto_api import router as zepto_router
from api.swiggy_api.swiggy_api import router as swiggy_router

app = FastAPI(
    title="Khwaaish API",
    description="A single API to rule them all.",
    version="1.0.0",
)

app.include_router(blinkit_router, prefix="/api", tags=["blinkit"])
app.include_router(zepto_router, prefix="/api", tags=["zepto"])
app.include_router(swiggy_router, prefix="/api", tags=["swiggy"])


