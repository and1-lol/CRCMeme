from js import Response, Headers
import datetime
import hashlib
import json
import secrets # Used for secure server-side random generation

def hash_password(password):
    # Added a simple static salt to mitigate basic rainbow tables
    # For high-security, consider using an external WebCrypto PBKDF2/Bcrypt binding
    salt = "CraftCoin_Secure_Salt_2026!"
    salted = password + salt
    return hashlib.sha256(salted.encode()).hexdigest()

def get_cors_headers():
    h = Headers.new()
    h.set("Access-Control-Allow-Origin", "*")
    h.set("Access-Control-Allow-Methods", "POST, OPTIONS, GET")
    h.set("Access-Control-Allow-Headers", "Content-Type")
    return h

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
        pass 

async def on_fetch(request, env):
    headers = get_cors_headers()
    method_str = str(request.method).upper().strip()

    if method_str == "OPTIONS":
        return Response.new("", status=204, headers=headers)
    if method_str == "GET":
        return Response.new("Craftcoin Backend is Online and Secured.", status=200, headers=headers)
    if method_str != "POST":
        return Response.new("Method Not Allowed", status=405, headers=headers)

    try:
        storage = env.CRAFTCOIN_DATA
        body_text = await request.text()
        if not body_text:
            return Response.new("Error: Empty body.", status=400, headers=headers)
        
        body = json.loads(body_text)
        action = body.get("action")

        if action == "get_leaderboard":
            cached_leaderboard = await storage.get("leaderboard:top")
            if not cached_leaderboard:
                cached_leaderboard = "[]"
            
            json_headers = get_cors_headers()
            json_headers.set("Content-Type", "application/json")
            return Response.new(cached_leaderboard, status=200, headers=json_headers)

        # --- ACTION: MINE VIA SERVER-SIDE RANDOM (FIXED SPOOFING) ---
        elif action == "mine_guess":
            username = body.get("username", "").lower().strip()
            pwd = body.get("password", "")
            
            # User-specific rate limiting instead of global blockages
            current_second = str(int(datetime.datetime.now().timestamp()))
            rate_key = f"rate:mine:{username}:{current_second}"
            
            current_rate_raw = await storage.get(rate_key)
            current_rate = int(current_rate_raw) if current_rate_raw else 0
            if current_rate >= 2: # Max 2 mining requests per second per user
                return Response.new("Error: Rate limit exceeded. Slow down.", status=429, headers=headers)
            
            await storage.put(rate_key, str(current_rate + 1), expiration_ttl=60)
            
            user_raw = await storage.get(f"user:{username}")
            if not user_raw:
                return Response.new("Error: User not found.", status=404, headers=headers)
            
            user = json.loads(user_raw)
            if user["password"] != hash_password(pwd):
                return Response.new("Error: Auth failed.", status=403, headers=headers)
            
            # FIX: Server generates the roll number securely. Client can no longer fake it.
            server_roll = secrets.randbelow(1000) # Generates 0-999
            
            if server_roll == 77:
                mining_reward = 5.0
                user["balance"] = float(user.get("balance", 0)) + mining_reward
                await storage.put(f"user:{username}", json.dumps(user))
                await update_cached_leaderboard(storage)
                return Response.new(f"Jackpot! Server rolled exactly 77! Gained {mining_reward} Craftcoins! Balance: {user['balance']}", status=200, headers=headers)
            else:
                return Response.new(f"Missed! Server rolled a {server_roll}. Better luck next time!", status=200, headers=headers)

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

        elif action == "create_account":
            username = body.get("username", "").lower().strip()
            password = body.get("password", "")
            
            if not username or len(username) < 3:
                return Response.new("Error: Invalid username.", status=400, headers=headers)
            if not password or len(password) < 6:
                return Response.new("Error: Password too short.", status=400, headers=headers)
            
            exists = await storage.get(f"user:{username}")
            if exists:
                return Response.new("Error: User exists.", status=400, headers=headers)
            
            user_data = {
                "password": hash_password(password),
                "balance": 0.0,
                "created_at": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            await storage.put(f"user:{username}", json.dumps(user_data))
            await update_cached_leaderboard(storage)
            return Response.new(f"Success: {username} created!", status=200, headers=headers)

        elif action == "transfer":
            sender_name = body.get("username", "").lower().strip()
            pwd = body.get("password", "")
            recipient_name = body.get("recipient", "").lower().strip()
            
            try:
                amount = float(body.get("amount", 0))
                if amount <= 0:
                    raise ValueError
            except ValueError:
                return Response.new("Error: Invalid transfer amount.", status=400, headers=headers)

            if sender_name == recipient_name:
                return Response.new("Error: Cannot transfer to yourself.", status=400, headers=headers)

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

            if float(sender["balance"]) < amount:
                return Response.new("Error: Insufficient funds.", status=400, headers=headers)

            sender["balance"] = float(sender["balance"]) - amount
            recipient["balance"] = float(recipient["balance"]) + amount

            await storage.put(f"user:{sender_name}", json.dumps(sender))
            await storage.put(f"user:{recipient_name}", json.dumps(recipient))
            await update_cached_leaderboard(storage)
            return Response.new(f"Success: Sent {amount} Craftcoins to {recipient_name}!", status=200, headers=headers)

        return Response.new("Error: Invalid action.", status=400, headers=headers)
    except Exception as e:
        return Response.new(f"Server Error: {str(e)}", status=500, headers=headers)
