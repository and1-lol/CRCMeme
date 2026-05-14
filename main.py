from js import Response, Object, Headers
import datetime
import hashlib
import json

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# Helper to format headers into a JS-compatible object
def get_cors_headers():
    h = Headers.new()
    h.set("Access-Control-Allow-Origin", "*")
    h.set("Access-Control-Allow-Methods", "POST, OPTIONS, GET")
    h.set("Access-Control-Allow-Headers", "Content-Type")
    return h

async def on_fetch(request, env):
    headers = get_cors_headers()

    # Handle Preflight
    if request.method == "OPTIONS":
        return Response.new("", status=204, headers=headers)

    # Handle GET request (serving status or metadata)
    if request.method == "GET":
        return Response.new("Craftcoin Backend is Online.", status=200, headers=headers)

    if request.method != "POST":
        return Response.new("Method Not Allowed", status=405, headers=headers)

    try:
        storage = env.CRAFTCOIN_DATA
        body_text = await request.text()
        
        if not body_text:
            return Response.new("Error: Empty body.", status=400, headers=headers)
            
        body = json.loads(body_text)
        action = body.get("action")
        
        if action == "create_account":
            username = body.get("username", "").lower().strip()
            password = body.get("password", "")
            
            if not username:
                return Response.new("Error: Username empty.", status=400, headers=headers)

            exists = await storage.get(f"user:{username}")
            if exists:
                return Response.new("Error: User exists.", status=400, headers=headers)
            
            user_data = {
                "password": hash_password(password),
                "balance": 100,
                "created_at": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            await storage.put(f"user:{username}", json.dumps(user_data))
            return Response.new(f"Success: {username} created!", status=200, headers=headers)

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
