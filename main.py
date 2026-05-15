from js import Response, Object
import datetime
import hashlib
import json

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# Fixed: Formats Python dictionaries to JS Objects natively to stop browser connection drops
def get_cors_headers():
    d = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS, GET",
        "Access-Control-Allow-Headers": "Content-Type"
    }
    return Object.fromEntries(Object.entries(json.loads(json.dumps(d))))

async def on_fetch(request, env):
    headers = get_cors_headers()
    method_str = str(request.method).upper().strip()

    # Handle Preflight Security Options Requests
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

        # --- ACTION: GET LEADERBOARD ---
        if action == "get_leaderboard":
            kv_list = await storage.list(prefix="user:")
            users_found = []
            
            for key_obj in kv_list.keys:
                key_name = key_obj.name
                raw_data = await storage.get(key_name)
                if raw_data:
                    parsed = json.loads(raw_data)
                    display_name = key_name.replace("user:", "")
                    users_found.append({
                        "username": display_name,
                        "balance": float(parsed.get("balance", 0))
                    })
            
            users_found.sort(key=lambda x: x["balance"], reverse=True)
            top_ten = users_found[:10]
            return Response.new(json.dumps(top_ten), status=200, headers=headers)
        
        # --- ACTION: MINE VIA NUMBER GUESS ---
        elif action == "mine_guess":
            username = body.get("username", "").lower().strip()
            pwd = body.get("password", "")
            guess_str = body.get("guess", "0")

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

            # Strict 1/100 Rule: Only the number 77 wins!
            if guess == 77:
                mining_reward = 5.0
                user["balance"] += mining_reward
                await storage.put(f"user:{username}", json.dumps(user))
                return Response.new(f" Successful Mine! Rolled exactly 77! Gained {mining_reward} Craftcoins! Balance: {user['balance']}", status=200, headers=headers)
            else:
                return Response.new(f" Missed! Rolled a {guess}. Only a roll of 77 wins at this 1/100 rate.", status=200, headers=headers)

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
            return Response.new(f"Success: Sent {amount}!", status=200, headers=headers)

        return Response.new("Error: Invalid action.", status=400, headers=headers)

    except Exception as e:
        return Response.new(f"Server Error: {str(e)}", status=500, headers=headers)
