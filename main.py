from js import Response, JSON
import datetime
import hashlib
import random

# Helper to generate a hash (replacing your password logic)
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

async def on_fetch(request, env):
    # Check if the KV namespace is bound
    # You must create a KV namespace named "CRAFTCOIN_DATA" in the dashboard
    storage = env.CRAFTCOIN_DATA

    try:
        # Parse the input (The "Request")
        data = await request.json()
        action = data.action # e.g., "create_account", "transfer", "get_balance"
        
        # --- ACTION: CREATE ACCOUNT ---
        if action == "create_account":
            username = data.username.lower()
            password = data.password
            
            # Check if user exists in KV
            exists = await storage.get(f"user:{username}")
            if exists:
                return Response.new("User already exists", status=400)
            
            user_data = {"password": hash_password(password), "balance": 0}
            await storage.put(f"user:{username}", JSON.stringify(user_data))
            return Response.new(f"Account {username} created!")

        # --- ACTION: TRANSFER ---
        elif action == "transfer":
            sender = data.username.lower()
            pwd = data.password
            recipient = data.recipient.lower()
            amount = float(data.amount)

            # 1. Auth Sender
            raw_sender = await storage.get(f"user:{sender}")
            if not raw_sender:
                return Response.new("Sender not found", status=404)
            
            sender_obj = JSON.parse(raw_sender)
            if sender_obj.password != hash_password(pwd):
                return Response.new("Auth failed", status=403)

            # 2. Check Balance
            if sender_obj.balance < amount:
                return Response.new("Insufficient funds", status=400)

            # 3. Get Recipient
            raw_recip = await storage.get(f"user:{recipient}")
            if not raw_recip:
                return Response.new("Recipient not found", status=404)
            recip_obj = JSON.parse(raw_recip)

            # 4. Update Balances
            sender_obj.balance -= amount
            recip_obj.balance += amount

            await storage.put(f"user:{sender}", JSON.stringify(sender_obj))
            await storage.put(f"user:{recipient}", JSON.stringify(recip_obj))

            return Response.new(f"Transferred {amount} to {recipient}")

        return Response.new("Invalid Action", status=400)

    except Exception as e:
        return Response.new(f"Error: {str(e)}", status=500)
