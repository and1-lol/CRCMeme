        # --- ACTION: MINE VIA NUMBER GUESS (With 10 requests/sec global rate limit) ---
        elif action == "mine_guess":
            username = body.get("username", "").lower().strip()
            pwd = body.get("password", "")
            guess_str = body.get("guess", "0")
            
            # 1. Global Rate Limiter Check (Max 10 per second total)
            current_second = str(int(datetime.datetime.now().timestamp()))
            rate_key = f"rate:mine:{current_second}"
            
            current_rate_raw = await storage.get(rate_key)
            current_rate = int(current_rate_raw) if current_rate_raw else 0
            
            if current_rate >= 10:
                return Response.new("Error: Global mining limit reached (max 10/sec). Try again instantly.", status=429, headers=headers)
            
            # Increment the rate limiter and set a 10-second TTL to auto-delete expired logs
            await storage.put(rate_key, str(current_rate + 1), expiration_ttl=60)
            
            # 2. Proceed with Normal Verification
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
            
            if guess == 77:
                mining_reward = 5.0
                user["balance"] += mining_reward
                await storage.put(f"user:{username}", json.dumps(user))
                await update_cached_leaderboard(storage)
                return Response.new(f"Jackpot! Rolled exactly 77! Gained {mining_reward} Craftcoins! Balance: {user['balance']}", status=200, headers=headers)
            else:
                return Response.new(f"Missed! Rolled a {guess}. Only a roll of 77 wins at this 1/1000 rate.", status=200, headers=headers)
