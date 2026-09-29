import time
import requests

def main():
    base = "http://127.0.0.1:8992"
    
    # 1. Archive discovery
    print("Fetching archive days for 2023...")
    r = requests.get(f"{base}/api/archive/days?year=2023")
    r.raise_for_status()
    print("Archive days 2023:", r.json()["dates"][:5], "...")
    
    # 2. Trigger download
    print("\nStarting download for wetPf2 on 2023-01-01 (max 5 profiles)...")
    res = requests.post(f"{base}/api/download", json={
        "stream": "nrt",
        "level": "level2",
        "product": "wetPf2",
        "date": "2023-01-01",
        "max_profiles": 5,
        "sampling": "first"
    })
    res.raise_for_status()
    job_id = res.json()["id"]
    print(f"Job ID: {job_id}")
    
    # 3. Poll job
    while True:
        st = requests.get(f"{base}/api/jobs/{job_id}").json()
        print(f"State: {st['state']} - {st.get('phase')} - {st.get('message')}")
        if st["state"] in ("completed", "failed", "cancelled"):
            if st["state"] == "failed":
                print(f"Error: {st.get('error')}")
            break
        time.sleep(2)

    # 4. Search local to verify
    print("\nSearching local profiles...")
    search = requests.post(f"{base}/api/profiles/search", json={"limit": 10})
    print(f"Found {search.json()['total']} profiles.")

if __name__ == "__main__":
    main()
