from js import Response
import datetime
import hashlib
import json

# --- HELPER FUNCTIONS ---
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# Standard headers for CORS
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}

async def on_fetch(request, env):
    # 1. Handle "OPTIONS" (CORS preflight)
    if request.method == "OPTIONS":
        return Response.new("", headers=CORS_HEADERS)

    # 2. Handle Browser visits (GET)
    if request.method != "POST":
        return Response.new(
            "Craftcoin Cloud is Active. Please use the web portal.", 
            headers=CORS_HEADERS,
            status=200
        )

    # 3. Connect to KV Storage
    # If this fails, the binding name in Cloudflare doesn't match 'CRAFTCOIN_DATA'
    try:
        storage = env.CRAFTCOIN_DATA
    except Exception:
        return Response.new("Server Error: KV Binding 'CRAFTCOIN_DATA' not found.", status=500)

    try:
        # 4. Read Input using Python-native methods
        body_raw = await request.text()
        body = json.loads(body_raw)
        
        action = body.get("action")
        
        # --- ACTION: CREATE ACCOUNT ---
        if action == "create_account":
            username = body.get("username", "").lower().strip()
            password = body.get("password", "")
            
            if not username or not password:
                return Response.new("Error: Missing username/password.", headers=CORS_HEADERS, status=400)

            exists = await storage.get(f"user:{username}")
            if exists:
                return Response.new("Error: User already exists.", headers=CORS_HEADERS, status=400)
            
            user_data = {
                "password": hash_password(password),
                "balance": 0,
                "created_at": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            # Use json.dumps instead of JS.stringify
            await storage.put(f"user:{username}", json.dumps(user_data))
            return Response.new(f"Success: Account '{username}' created!", headers=CORS_HEADERS)

        # --- ACTION: TRANSFER ---
        elif action == "transfer":
            sender_name = body.get("username", "").lower().strip()
            pwd = body.get("password", "")
            recipient_name = body.get("recipient", "").lower().strip()
            amount = float(body.get("amount", 0))

            # Get Sender
            sender_raw = await storage.get(f"user:{sender_name}")
            if not sender_raw:
                return Response.new("Error: Sender not found.", headers=CORS_HEADERS, status=404)
            
            sender = json.loads(sender_raw)
            if sender.get("password") != hash_password(pwd):
                return Response.new("Error: Auth failed.", headers=CORS_HEADERS, status=403)

            # Get Recipient
            recipient_raw = await storage.get(f"user:{recipient_name}")
            if not recipient_raw:
                return Response.new("Error: Recipient not found.", headers=CORS_HEADERS, status=404)
            recipient = json.loads(recipient_raw)

            # Logic
            if sender.get("balance", 0) < amount:
                return Response.new("Error: Insufficient funds.", headers=CORS_HEADERS, status=400)

            sender["balance"] -= amount
            recipient["balance"] += amount

            # Save back using Python json
            await storage.put(f"user:{sender_name}", json.dumps(sender))
            await storage.put(f"user:{recipient_name}", json.dumps(recipient))

            return Response.new(f"Success: Sent {amount} to {recipient_name}!", headers=CORS_HEADERS)

        # Catch-all for unknown actions to prevent hanging
        return Response.new("Error: Invalid action.", headers=CORS_HEADERS, status=400)

    except Exception as e:
        # This catches JSON errors or code crashes and returns a response so it doesn't hang
        return Response.new(f"Server Error: {str(e)}", headers=CORS_HEADERS, status=500)
