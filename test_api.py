import httpx
import asyncio

async def run_tests():
    print("=== Testing ML Worker ===")
    async with httpx.AsyncClient(base_url="http://localhost:8001") as client:
        # Test Embed
        print("1. Testing /embed...")
        r = None
        try:
            r = await client.post("/internal/ml/embed", json={"text": "Тестовая строка для эмбеддинга"})
            r.raise_for_status()
            vector = r.json().get("embedding", [])
            print(f"Success! Vector length: {len(vector)}")
        except Exception as e:
            err_text = getattr(r, 'text', str(e)) if r else str(e)
            print(f"Embed Failed: {err_text}")

        # Test Parse
        print("\n2. Testing /parse-characteristics...")
        r = None
        try:
            sample_characteristics = '[["Толщина, мкм", "50.000"], ["Цвет", "черный"]]'
            r = await client.post("/internal/ml/parse-characteristics", json={"raw_text": sample_characteristics})
            r.raise_for_status()
            data = r.json()
            print(f"Success! Parsed output: {data}")
        except Exception as e:
            err_text = getattr(r, 'text', str(e)) if r else str(e)
            print(f"Parse Failed: {err_text}")

    print("\n=== Testing Backend ===")
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        # Test calculate NMCC graph
        print("1. Testing /calculate...")
        r = None
        try:
            r = await client.post("/api/v1/nmck/calculate", json={
                "target_ste_id": "STE-TEST-123",
                "target_region": "Пермский край",
                "selected_prices": [100.0, 105.0, 95.0, 500.0]
            })
            r.raise_for_status()
            data = r.json()
            print("Success! Response:")
            print(f"Thread ID: {data.get('thread_id')}")
            print(f"Human Input Required: {data.get('state', {}).get('requires_manual_input')}")
        except Exception as e:
            err_text = getattr(r, 'text', str(e)) if r else str(e)
            print(f"Calculate Failed: {err_text}")

if __name__ == "__main__":
    asyncio.run(run_tests())
