from js import Response, Headers, fetch
import datetime
import hashlib
import json
import asyncio
import random

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_cors_headers():
    h = Headers.new()
    h.set("Access-Control-Allow-Origin", "*")
    h.set("Access-Control-Allow-Methods", "POST, OPTIONS, GET")
    h.set("Access-Control-Allow-Headers", "Content-Type")
    return h

# Asynchronous helper to pull data from GitHub's REST API
async def github_get(env, filename):
    owner = env.GITHUB_OWNER
    repo = env.GITHUB_REPO
    token = env.GITHUB_TOKEN
    url = f"https://github.com{owner}/{repo}/contents/database/{filename}"
    
    # Cloudflare Python Workers safely use the underlying JavaScript fetch FFI
    js_resp = await fetch(url, headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3.raw",
        "User-Agent": "Cloudflare-Worker"
    })
    
    if js_resp.status != 200:
        return None
    
    text_data = await js_resp.text()
    return json.loads(text_data)

# Asynchronous helper to commit or update data inside GitHub
async def github_put(env, filename, data_dict):
    owner = env.GITHUB_OWNER
    repo = env.GITHUB_REPO
    token = env.GITHUB_TOKEN
    url = f"https://github.com{owner}/{repo}/contents/database/{filename}"
    
    # We first grab the current file metadata to acquire its unique SHA hash string
    meta_resp = await fetch(url, headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Cloudflare-Worker"
    })
    
    sha = None
    if meta_resp.status == 200:
        meta_json = json.loads(await meta_resp.text())
        sha = meta_json.get("sha")

    # Encode payload to base64 format requested by GitHub API
    content_bytes = json.dumps(data_dict, indent=2).encode('utf-8')
    # Using Javascript runtime utility for high performance encoding conversion
    from js import btoa
    # Convert string byte stream characters over to native base64 format strings
    content_b64 = btoa("".join([chr(b) for b in content_bytes]))

    payload = {
        "message": f"Database update for {filename} via Craftcoin Engine",
        "content": content_b64
    }
    if sha:
        payload["sha"] = sha

    await fetch(url, method="PUT", headers={
        "Authorization": f"token {token}",
        "Content-Type": "application/json",
        "User-Agent": "Cloudflare-Worker"
    }, body=json.dumps(payload))

# Helper to fetch directory lists from GitHub to populate leaderboards
async def github_list_users(env):
    owner = env.GITHUB_OWNER
    repo = env.GITHUB_REPO
    token = env.GITHUB_TOKEN
    url = f"https://github.com{owner}/{repo}/contents/database"
    
    resp = await fetch(url, headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Cloudflare-Worker"
    })
    if resp.status != 200:
        return []
    
    items = json.loads(await resp.text())
    return [item["name"] for item in items if item["name"].endswith(".json")]

async def on_fetch(request, env):
    headers = get_cors_headers()
    method_str = str(request.method).upper().strip()

    if method_str == "OPTIONS":
        return Response.new("", status=204, headers=headers)
    if method_str == "GET":
        return Response.new("Craftcoin GitHub Backend is Online.", status=200, headers=headers)
    if method_str != "POST":
        return Response.new("Method Not Allowed", status=405, headers=headers)

    try:
        body_text = await request.text()
        if not body_text:
            return Response.new("Error: Empty body.", status=400, headers=headers)
            
        body = json.loads(body_text)
        action = body.get("action")

        # --- ACTION: GET LEADERBOARD (SCALED CONCURRENT GITHUB ENGINE) ---
        if action == "get_leaderboard":
            filenames = await github_list_users(env)
            users_found = []
            
            # Asynchronously pool all requests concurrently bypassing loop latency bottlenecks
            tasks = [github_get(env, fname) for fname in filenames]
            results = await asyncio.gather(*tasks)

            for fname, user_data in zip(filenames, results):
                if user_data:
                    display_name = fname.replace(".json", "")
                    users_found.append({
                        "username": display_name,
                        "balance": float(user_data.get("balance", 0))
                    })
            
            users_found.sort(key=lambda x: x["balance"], reverse=True)
            top_ten = users_found[:10]
            
            json_headers = get_cors_headers()
            json_headers.set("Content-Type", "application/json")
            return Response.new(json.dumps(top_ten), status=200, headers=json_headers)
        
        # --- ACTION: MINE VIA NUMBER GUESS (SECURE SERVER SIDE VALIDATION) ---
        elif action == "mine_guess":
            username = body.get("username", "").lower().strip()
            pwd = body.get("password", "")

            user = await github_get(env, f"{username}.json")
            if not user:
                return Response.new("Error: User not found.", status=404, headers=headers)
                
            if user["password"] != hash_password(pwd):
                return Response.new("Error: Auth failed.", status=403, headers=headers)

            server_roll = random.randint(1, 100)

            if server_roll == 77:
                mining_reward = 5.0
                user["balance"] += mining_reward
                await github_put(env, f"{username}.json", user)
                return Response.new(f"🎉 Jackpot! Server rolled 77! Gained {mining_reward} Craftcoins! Balance: {user['balance']}", status=200, headers=headers)
            else:
                return Response.new(f"❌ Missed! Server rolled a {server_roll}. Try again!", status=200, headers=headers)

        # --- ACTION: GET BALANCE ---
        elif action == "get_balance":
            username = body.get("username", "").lower().strip()
            pwd = body.get("password", "")
            
            user = await github_get(env, f"{username}.json")
            if not user:
                return Response.new("Error: User not found.", status=404, headers=headers)
                
            if user["password"] != hash_password(pwd):
                return Response.new("Error: Auth failed.", status=403, headers=headers)
                
            return Response.new(f"Balance: {user['balance']} Craftcoins", status=200, headers=headers)

        # --- ACTION: CREATE ACCOUNT ---
        elif action == "create_account":
            username = body.get("username", "").lower().strip()
            password = body.get("password", "")
            
            if not username or not username.isalnum():
                return Response.new("Error: Username must be alphanumeric.", status=400, headers=headers)

            exists = await github_get(env, f"{username}.json")
            if exists:
                return Response.new("Error: User exists.", status=400, headers=headers)
            
            user_data = {
                "password": hash_password(password),
                "balance": 0.0,
                "created_at": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            await github_put(env, f"{username}.json", user_data)
            return Response.new(f"Success: {username} created with 0 coins!", status=200, headers=headers)

        # --- ACTION: TRANSFER (SECURITY PROTECTED FOR DISADVANTAGED OVERLAPS) ---
        elif action == "transfer":
            sender_name = body.get("username", "").lower().strip()
            pwd = body.get("password", "")
            recipient_name = body.get("recipient", "").lower().strip()
            
            try:
                amount = float(body.get("amount", 0))
            except (ValueError, TypeError):
                return Response.new("Error: Invalid numeric amount.", status=400, headers=headers)

            if amount <= 0:
                return Response.new("Error: Transfer amount must be positive.", status=400, headers=headers)
            if sender_name == recipient_name:
                return Response.new("Error: Cannot transfer to yourself.", status=400, headers=headers)

            # Pull active users concurrently
            sender_task = github_get(env, f"{sender_name}.json")
            recipient_task = github_get(env, f"{recipient_name}.json")
            sender, recipient = await asyncio.gather(sender_task, recipient_task)

            if not sender:
                return Response.new("Error: Sender not found.", status=404, headers=headers)
            if sender["password"] != hash_password(pwd):
                return Response.new("Error: Auth failed.", status=403, headers=headers)
            if not recipient:
                return Response.new("Error: Recipient not found.", status=404, headers=headers)
            if sender["balance"] < amount:
                return Response.new("Error: No funds.", status=400, headers=headers)

            sender["balance"] -= amount
            recipient["balance"] += amount

            # Concurrently update database storage configurations
            await asyncio.gather(
                github_put(env, f"{sender_name}.json", sender),
                github_put(env, f"{recipient_name}.json", recipient)
            )
            return Response.new(f"Success: Sent {amount}!", status=200, headers=headers)

        return Response.new("Error: Invalid action.", status=400, headers=headers)

    except Exception as e:
        return Response.new(f"Server Error: {str(e)}", status=500, headers=headers)
