from js import Response, JSON
import datetime
import hashlib

# --- HELPER FUNCTIONS ---
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# Standard headers for CORS (allows your website to talk to this backend)
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}

async def on_fetch(request, env):
    # 1. Handle "OPTIONS" request (Browser security check)
    if request.method == "OPTIONS":
        return Response.new("", headers=CORS_HEADERS)

    # 2. Handle Browser visits (GET request)
    if request.method != "POST":
        return Response.new(
            "Craftcoin Cloud is Active. Please use the web portal or client menu.", 
            headers=CORS_HEADERS,
            status=200
        )

    # 3. Connect to KV Storage
    # Ensure you named your KV binding 'CRAFTCOIN_DATA' in the dashboard
    storage = env.CRAFTCOIN_DATA

    try:
        # 4. Read Input
        body = await request.json()
        action = body.action
        
        # --- ACTION: CREATE ACCOUNT ---
        if action == "create_account":
            username = body.username.lower().strip()
            password = body.password
            
            exists = await storage.get(f"user:{username}")
            if exists:
                return Response.new("Error: User already exists.", headers=CORS_HEADERS, status=400)
            
            user_data = {
                "password": hash_password(password),
                "balance": 0,
                "created_at": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            await storage.put(f"user:{username}", JSON.stringify(user_data))
            return Response.new(f"Success: Account '{username}' created!", headers=CORS_HEADERS)

        # --- ACTION: TRANSFER ---
        elif action == "transfer":
            sender_name = body.username.lower().strip()
            pwd = body.password
            recipient_name = body.recipient.lower().strip()
            amount = float(body.amount)

            # Get Sender
            sender_raw = await storage.get(f"user:{sender_name}")
            if not sender_raw:
                return Response.new("Error: Sender not found.", headers=CORS_HEADERS, status=404)
            
            sender = JSON.parse(sender_raw)
            if sender.password != hash_password(pwd):
                return Response.new("Error: Auth failed.", headers=CORS_HEADERS, status=403)

            # Get Recipient
            recipient_raw = await storage.get(f"user:{recipient_name}")
            if not recipient_raw:
                return Response.new("Error: Recipient not found.", headers=CORS_HEADERS, status=404)
            recipient = JSON.parse(recipient_raw)

            # Logic
            if sender.balance < amount:
                return Response.new("Error: Insufficient funds.", headers=CORS_HEADERS, status=400)

            sender.balance -= amount
            recipient.balance += amount

            # Save back to KV
            await storage.put(f"user:{sender_name}", JSON.stringify(sender))
            await storage.put(f"user:{recipient_name}", JSON.stringify(recipient))

            return Response.new(f"Success: Sent {amount} to {recipient_name}!", headers=CORS_HEADERS)

        return Response.new("Error: Invalid action.", headers=CORS_HEADERS, status=400)

    except Exception as e:
        return Response.new(f"Server Error: {str(e)}", headers=CORS_HEADERS, status=500)
