import os, json, httpx, asyncio

async def test():
    key = 'sk-84437dbf50d1455197c80d4f02828220'
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            'https://api.deepseek.com/v1/chat/completions',
            headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
            json={
                'model': 'deepseek-chat',
                'messages': [{'role': 'user', 'content': 'hi'}],
                'max_tokens': 10
            },
        )
        print('Status:', resp.status_code)
        print('Body:', resp.text[:300])

asyncio.run(test())
