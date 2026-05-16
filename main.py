from js import Response, Headers
import datetime
import hashlib
import json

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_cors_headers():
    h = Headers.new()
    h.set("Access-Control-Allow-Origin", "*")
    h.set("Access-Control-Allow-Methods", "POST, OPTIONS, GET")
    h.set("Access-Control-Allow-Headers", "Content-Type")
    return h

# Helper to automatically update the leaderboard cache on database writes
async def update_cached_leaderboard(storage):
    try:
        kv_list = await storage.list(prefix="user:")
        users_found = []
        for key_obj in kv_list.keys:
            raw_data = await storage.get(key_obj.name)
            if raw_data:
                parsed = json.loads(raw_data)
                display_name = key_obj.name.replace("user:", "")
                users_found.append({
                    "username": display_name,
                    "balance": float(parsed.get("balance", 0))
                })
        users_found.sort(key=lambda x: x["balance"], reverse=True)
        top_ten = users_found[:10]
        await storage.put("leaderboard:top", json.dumps(top_ten))
    except Exception:
        pass  # Fails silently to ensure user's primary action isn't blocked

async def on_fetch(request, env):
    headers = get_cors_headers()
    method_str = str(request.method).upper().strip()

    if method_str == "OPTIONS":
        return Response.new("", status=204, headers=headers)
    if method_str == "GET":
        return Response.new("Craftcoin Backend is Online.", status=200, headers=headers)
    if method_str != "POST":
        return Response.new("Method Not Allowed", status=405, headers=headers)

    try:
        storage = env.CRAFTCOIN_DATA
        body_text = await request.text()
        if not body_text:
            return Response.new("Error: Empty body.", status=400, headers=headers)
        
        body = json.loads(body_text)
        action = body.get("action")

        # --- ACTION: GET LEADERBOARD (Optimized to 1 KV read) ---
        if action == "get_leaderboard":
            cached_leaderboard = await storage.get("leaderboard:top")
            if not cached_leaderboard:
                cached_leaderboard = "[]"
            
            json_headers = get_cors_headers()
            json_headers.set("Content-Type", "application/json")
            return Response.new(cached_leaderboard, status=200, headers=json_headers)

        # --- ACTION: MINE VIA NUMBER GUESS (With 10 req/sec limit) ---
        elif action == "mine_guess":
            username = body.get("username", "").lower().strip()
            pwd = body.get("password", "")
            guess_str = body.get("guess", "0")
            
            # Global Rate Limiter Check (Max 10 total requests per second)
            current_second = str(int(datetime.datetime.now().timestamp()))
            rate_key = f"rate:mine:{current_second}"
            
            current_rate_raw = await storage.get(rate_key)
            current_rate = int(current_rate_raw) if current_rate_raw else 0
            
            if current_rate >= 10:
                return Response.new("Error: Global mining limit reached (max 10/sec). Try again.", status=429, headers=headers)
            
            # Increment and set 60-second expiration lifecycle
            await storage.put(rate_key, str(current_rate + 1), expiration_ttl=60)
            
            # Authenticate user
            user_raw = await storage.get(f"user:{username}")
            if not user_raw:
                return Response.new("Error: User not found.", status=404, headers=headers)
            
            user = json.loads(user_raw)
            if user["password"] != hash_password(pwd):
                return Response.new("Error: Auth failed.", status=403, headers=headers)
            
            try:
                guess = int(guess_str)
            except ValueError:
                return Response.new("Error: Invalid number.", status=400, headers=headers)
            
            # Process dice guess logic
            if guess == 77:
                mining_reward = 5.0
                user["balance"] += mining_reward
                await storage.put(f"user:{username}", json.dumps(user))
                await update_cached_leaderboard(storage)
                return Response.new(f"Jackpot! Rolled exactly 77! Gained {mining_reward} Craftcoins! Balance: {user['balance']}", status=200, headers=headers)
            else:
                return Response.new(f"Missed! Rolled a {guess}. Only a roll of 77 wins at this 1/1000 rate.", status=200, headers=headers)

        # --- ACTION: GET BALANCE ---
        elif action == "get_balance":
            username = body.get("username", "").lower().strip()
            pwd = body.get("password", "")
            
            user_raw = await storage.get(f"user:{username}")
            if not user_raw:
                return Response.new("Error: User not found.", status=404, headers=headers)
            
            user = json.loads(user_raw)
            if user["password"] != hash_password(pwd):
                return Response.new("Error: Auth failed.", status=403, headers=headers)
            
            return Response.new(f"Balance: {user['balance']} Craftcoins", status=200, headers=headers)

        # --- ACTION: CREATE ACCOUNT ---
        elif action == "create_account":
            username = body.get("username", "").lower().strip()
            password = body.get("password", "")
            
            if not username:
                return Response.new("Error: Username empty.", status=400, headers=headers)
            
            exists = await storage.get(f"user:{username}")
            if exists:
                return Response.new("Error: User exists.", status=400, headers=headers)
            
            user_data = {
                "password": hash_password(password),
                "balance": 0,
                "created_at": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            await storage.put(f"user:{username}", json.dumps(user_data))
            await update_cached_leaderboard(storage)
            return Response.new(f"Success: {username} created with 0 coins!", status=200, headers=headers)

        # --- ACTION: TRANSFER ---
        elif action == "transfer":
            sender_name = body.get("username", "").lower().strip()
            pwd = body.get("password", "")
            recipient_name = body.get("recipient", "").lower().strip()
            amount = float(body.get("amount", 0))

            sender_raw = await storage.get(f"user:{sender_name}")
            if not sender_raw:
                return Response.new("Error: Sender not found.", status=404, headers=headers)
            
            sender = json.loads(sender_raw)
            if sender["password"] != hash_password(pwd):
                return Response.new("Error: Auth failed.", status=403, headers=headers)

            recipient_raw = await storage.get(f"user:{recipient_name}")
            if not recipient_raw:
                return Response.new("Error: Recipient not found.", status=404, headers=headers)
            
            recipient = json.loads(recipient_raw)

            if sender["balance"] < amount:
                return Response.new("Error: No funds.", status=400, headers=headers)

            sender["balance"] -= amount
            recipient["balance"] += amount

            await storage.put(f"user:{sender_name}", json.dumps(sender))
            await storage.put(f"user:{recipient_name}", json.dumps(recipient))
            await update_cached_leaderboard(storage)
            return Response.new(f"Success: Sent {amount}!", status=200, headers=headers)

        return Response.new("Error: Invalid action.", status=400, headers=headers)
    except Exception as e:
        return Response.new(f"Server Error: {str(e)}", status=500, headers=headers)
