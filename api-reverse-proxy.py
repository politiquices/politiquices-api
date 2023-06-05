import httpx as httpx
from fastapi import FastAPI, Request, Response

app = FastAPI()

"""
https://stackoverflow.com/questions/70610266/proxy-an-external-website-using-python-fast-api-not-supporting-query-params
https://www.youtube.com/watch?v=HkNg_fpxb8M
"""


@app.middleware("http")
async def _reverse_proxy(request: Request, call_next):

    api_backend = "http://localhost:8000"

    print("headers")
    print(request.headers)

    async with httpx.AsyncClient() as client:
        response = await client.request(
            method=request.method,
            url=api_backend+request.url.path,
            headers=request.headers,
            data=await request.body(),
        )

    print("response")
    print(response)

    proxy_response = Response(
        content=response.content,
        status_code=response.status_code,
        headers=response.headers,
    )

    return proxy_response


app.add_route("/{path:path}", _reverse_proxy, ["GET", "POST"])
