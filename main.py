from js import Response
import datetime
import hashlib
import json

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}

async def on_fetch(request, env):
    # 1. Handle OPTIONS
    if request.method == "OPTIONS":
        return Response.new("", headers=CORS_HEADERS)

    # 2. Handle GET
    if request.method != "POST":
        return Response.new("Craftcoin Backend is Online.", headers=CORS_HEADERS, status=200)

    storage = env.CRAFTCOIN_DATA

    try:
        body_text = await request.text()
        body = json.loads(body_text)
        action = body.get("action")
        
        if action == "create_account":
            username = body.get("username", "").lower().strip()
            password = body.get("password", "")
            
            exists = await storage.get(f"user:{username}")
            if exists:
                return Response.new("Error: User exists.", headers=CORS_HEADERS, status=400)
            
            user_data = {
                "password": hash_password(password),
                "balance": 0,
                "created_at": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            await storage.put(f"user:{username}", json.dumps(user_data))
            return Response.new(f"Success: {username} created!", headers=CORS_HEADERS)

        elif action == "transfer":
            sender_name = body.get("username", "").lower().strip()
            pwd = body.get("password", "")
            recipient_name = body.get("recipient", "").lower().strip()
            amount = float(body.get("amount", 0))

            sender_raw = await storage.get(f"user:{sender_name}")
            if not sender_raw:
                return Response.new("Error: Sender not found.", headers=CORS_HEADERS, status=404)
            
            sender = json.loads(sender_raw)
            if sender["password"] != hash_password(pwd):
                return Response.new("Error: Auth failed.", headers=CORS_HEADERS, status=403)

            recipient_raw = await storage.get(f"user:{recipient_name}")
            if not recipient_raw:
                return Response.new("Error: Recipient not found.", headers=CORS_HEADERS, status=404)
            recipient = json.loads(recipient_raw)

            if sender["balance"] < amount:
                return Response.new("Error: No funds.", headers=CORS_HEADERS, status=400)

            sender["balance"] -= amount
            recipient["balance"] += amount

            await storage.put(f"user:{sender_name}", json.dumps(sender))
            await storage.put(f"user:{recipient_name}", json.dumps(recipient))
            return Response.new(f"Success: Sent {amount}!", headers=CORS_HEADERS)

        return Response.new("Error: Invalid action.", headers=CORS_HEADERS, status=400)

    except Exception as e:
        return Response.new(f"Server Error: {str(e)}", headers=CORS_HEADERS, status=500)
