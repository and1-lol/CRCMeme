from js import Response, JSON
import datetime
import hashlib
import random

# --- YOUR HELPER FUNCTIONS ---
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

async def on_fetch(request, env):
    # 1. PREVENT THE JSON ERROR
    # Browsers send a "GET" request when you visit the URL. 
    # We must stop here because GET requests have no JSON data to read.
    if request.method != "POST":
        return Response.new(
            "Craftcoin Cloud is Active. Please use the Client Menu to interact.", 
            status=200
        )

    # 2. BIND TO STORAGE
    # Ensure you created a KV namespace named CRAFTCOIN_DATA in the dashboard
    storage = env.CRAFTCOIN_DATA

    try:
        # 3. READ INPUT SAFELY
        body = await request.json()
        action = body.action
        
        # --- LOGIC: CREATE ACCOUNT ---
        if action == "create_account":
            username = body.username.lower().strip()
            password = body.password
            
            # Check KV for existing user
            exists = await storage.get(f"user:{username}")
            if exists:
                return Response.new("Error: Username already exists.", status=400)
            
            # Save new user to KV
            user_data = {
                "password": hash_password(password),
                "balance": 0,
                "address": username,
                "created_at": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            await storage.put(f"user:{username}", JSON.stringify(user_data))
            return Response.new(f"Success: Account '{username}' created with 0 Craftcoin!")

        # --- LOGIC: TRANSFER ---
        elif action == "transfer":
            sender_name = body.username.lower().strip()
            pwd = body.password
            recipient_name = body.recipient.lower().strip()
            amount = float(body.amount)

            if amount <= 0:
                return Response.new("Error: Amount must be positive.", status=400)

            # Auth Sender
            sender_raw = await storage.get(f"user:{sender_name}")
            if not sender_raw:
                return Response.new("Error: Sender account not found.", status=404)
            
            sender = JSON.parse(sender_raw)
            if sender.password != hash_password(pwd):
                return Response.new("Error: Authentication failed.", status=403)

            # Check Recipient
            if sender_name == recipient_name:
                return Response.new("Error: Cannot transfer to yourself.", status=400)
                
            recipient_raw = await storage.get(f"user:{recipient_name}")
            if not recipient_raw:
                return Response.new("Error: Recipient address not found.", status=404)
            recipient = JSON.parse(recipient_raw)

            # Update Balances
            if sender.balance < amount:
                return Response.new("Error: Insufficient funds.", status=400)

            sender.balance -= amount
            recipient.balance += amount

            # Save back to KV
            await storage.put(f"user:{sender_name}", JSON.stringify(sender))
            await storage.put(f"user:{recipient_name}", JSON.stringify(recipient))

            return Response.new(f"Success: Transferred {amount} Craftcoin to {recipient_name}!")

        return Response.new("Error: Invalid Action Request.", status=400)

    except Exception as e:
        # This catches errors if the JSON sent is malformed
        return Response.new(f"Server Error: {str(e)}", status=500)

return Response.new(
    "Your message here", 
    headers={
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type"
    }
)

