"""
Real agent stress-test for AgentLens.

Gives Claude a deliberately complex task with a buggy simulated filesystem.
The fake tool responses introduce subtle errors mid-way so the agent naturally
starts looping, re-reading files, and spiralling — exactly the failure patterns
AgentLens is built to detect.

Usage:
  1. Terminal 1:  cd backend && source .venv/bin/activate && python server.py
  2. Terminal 2:  cd dashboard && npm run dev   → click "Go Live"
  3. Terminal 3:  cd backend && source .venv/bin/activate && python run_real_agent.py

The dashboard will update in real-time as each step completes.
"""
import json
import os
import random
import urllib.request
from dotenv import load_dotenv
from interceptor import InstrumentedClient

load_dotenv()

# ─── Tools the agent can use ───────────────────────────────────────────

TOOLS = [
    {
        "name": "read_file",
        "description": "Read a file's contents. Returns the full text of the file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative file path"}
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Create or overwrite a file with the given content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative file path"},
                "content": {"type": "string", "description": "Full file content"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "bash",
        "description": "Execute a shell command and return stdout + stderr.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run"}
            },
            "required": ["command"],
        },
    },
    {
        "name": "grep",
        "description": "Search for a pattern across files. Returns matching lines.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern"},
                "path": {"type": "string", "description": "Directory or file to search"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "list_files",
        "description": "List files in a directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path"}
            },
            "required": ["path"],
        },
    },
]

# ─── Simulated filesystem ──────────────────────────────────────────────

FILESYSTEM = {
    "src/server.ts": '''import express from "express";
import { Pool } from "pg";
import Redis from "ioredis";

const app = express();
app.use(express.json());

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
});

const redis = new Redis(process.env.REDIS_URL);

// Cache middleware
async function cacheMiddleware(req, res, next) {
  const key = `cache:${req.originalUrl}`;
  const cached = await redis.get(key);
  if (cached) {
    return res.json(JSON.parse(cached));
  }
  res.sendResponse = res.json;
  res.json = (body) => {
    redis.setex(key, 300, JSON.stringify(body));
    res.sendResponse(body);
  };
  next();
}

// GET /api/products  — paginated, filterable
app.get("/api/products", cacheMiddleware, async (req, res) => {
  const { page = 1, limit = 20, category, minPrice, maxPrice, sort } = req.query;
  const offset = (page - 1) * limit;

  let query = "SELECT * FROM products WHERE 1=1";
  const params = [];

  if (category) {
    params.push(category);
    query += ` AND category = $${params.length}`;
  }
  if (minPrice) {
    params.push(minPrice);
    query += ` AND price >= $${params.length}`;
  }
  if (maxPrice) {
    params.push(maxPrice);
    query += ` AND price <= $${params.length}`;
  }

  // BUG: sort is user-controlled — SQL injection possible
  if (sort) query += ` ORDER BY ${sort}`;

  params.push(limit, offset);
  query += ` LIMIT $${params.length - 1} OFFSET $${params.length}`;

  const { rows } = await pool.query(query, params);
  res.json({ products: rows, page: Number(page) });
});

// POST /api/products  — create new product
app.post("/api/products", async (req, res) => {
  const { name, price, category, inventory_count } = req.body;
  // BUG: no input validation at all
  const { rows } = await pool.query(
    "INSERT INTO products (name, price, category, inventory_count) VALUES ($1, $2, $3, $4) RETURNING *",
    [name, price, category, inventory_count]
  );
  // BUG: should invalidate cache after mutation
  res.status(201).json(rows[0]);
});

// POST /api/orders  — place an order (the really broken part)
app.post("/api/orders", async (req, res) => {
  const { user_id, items } = req.body; // items = [{product_id, quantity}]
  const client = await pool.connect();

  try {
    await client.query("BEGIN");

    let total = 0;
    for (const item of items) {
      const product = await client.query("SELECT * FROM products WHERE id = $1", [item.product_id]);
      if (product.rows.length === 0) {
        throw new Error(`Product ${item.product_id} not found`);
      }

      // BUG: race condition — no row lock, inventory can go negative
      const p = product.rows[0];
      if (p.inventory_count < item.quantity) {
        throw new Error(`Insufficient inventory for ${p.name}`);
      }

      total += p.price * item.quantity;

      await client.query(
        "UPDATE products SET inventory_count = inventory_count - $1 WHERE id = $2",
        [item.quantity, item.product_id]
      );
    }

    const order = await client.query(
      "INSERT INTO orders (user_id, total, status) VALUES ($1, $2, 'pending') RETURNING *",
      [user_id, total]
    );

    // BUG: order_items never inserted — data loss
    await client.query("COMMIT");
    res.status(201).json(order.rows[0]);
  } catch (err) {
    await client.query("ROLLBACK");
    // BUG: leaks internal error messages to client
    res.status(400).json({ error: err.message });
  } finally {
    client.release();
  }
});

app.listen(3000, () => console.log("Server running on :3000"));
''',

    "src/middleware/auth.ts": '''import jwt from "jsonwebtoken";

// BUG: hardcoded secret, should be env var
const SECRET = "supersecret123";

export function authMiddleware(req, res, next) {
  const token = req.headers.authorization?.split(" ")[1];
  if (!token) return res.status(401).json({ error: "No token" });

  try {
    // BUG: no token expiry validation, no issuer check
    const decoded = jwt.verify(token, SECRET);
    req.user = decoded;
    next();
  } catch {
    res.status(401).json({ error: "Invalid token" });
  }
}
''',

    "tests/server.test.ts": '''import request from "supertest";
// BUG: tests import nothing, the app isn't exported
// BUG: no test database setup, tests hit production DB
// BUG: no cleanup between tests

describe("Products API", () => {
  it("should list products", async () => {
    const res = await request(app).get("/api/products");
    expect(res.status).toBe(200);
  });

  it("should create a product", async () => {
    const res = await request(app)
      .post("/api/products")
      .send({ name: "Test", price: 9.99 });
    expect(res.status).toBe(201);
  });
});

describe("Orders API", () => {
  it("should place an order", async () => {
    const res = await request(app)
      .post("/api/orders")
      .send({ user_id: 1, items: [{ product_id: 1, quantity: 1 }] });
    expect(res.status).toBe(201);
  });
});
''',

    "package.json": '{"name":"ecommerce-api","version":"1.0.0","scripts":{"start":"ts-node src/server.ts","test":"jest --config jest.config.ts"},"dependencies":{"express":"^4.18.2","pg":"^8.11.3","ioredis":"^5.3.2","jsonwebtoken":"^9.0.2"},"devDependencies":{"jest":"^29.7.0","supertest":"^6.3.3","@types/express":"^4.17.21","ts-node":"^10.9.2","typescript":"^5.3.3"}}',

    "docker-compose.yml": '''version: "3.8"
services:
  db:
    image: postgres:15
    environment:
      POSTGRES_DB: ecommerce
      POSTGRES_PASSWORD: postgres
    ports: ["5432:5432"]
  redis:
    image: redis:7
    ports: ["6379:6379"]
''',

    "schema.sql": '''CREATE TABLE products (
  id SERIAL PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  price DECIMAL(10,2) NOT NULL,
  category VARCHAR(100),
  inventory_count INTEGER DEFAULT 0,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE orders (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL,
  total DECIMAL(10,2) NOT NULL,
  status VARCHAR(50) DEFAULT 'pending',
  created_at TIMESTAMP DEFAULT NOW()
);

-- BUG: order_items table is missing!
-- There's no way to track which products are in which order
''',
}

step_counter = 0
CHAOS_MODE = True  # Set False to disable chaos injection
CHAOS_SEED = 42

_chaos_rng = random.Random(CHAOS_SEED)

# Chaos responses that mimic real-world failures
CHAOS_TIMEOUTS = [
    "Error: ETIMEDOUT — operation timed out after 30000ms",
    "Error: ECONNRESET — connection reset by peer",
    "Error: EPIPE — broken pipe",
]
CHAOS_CORRUPTIONS = [
    "SyntaxError: Unexpected token '\\x00' in JSON at position 0",
    "Error: ENOSPC — no space left on device",
    "Error: EMFILE — too many open files",
]

def fake_tool_response(name: str, inp: dict) -> str:
    """Simulate tool results. Introduce errors after step 8 to cause divergence.
    With CHAOS_MODE, randomly inject timeouts, corrupted responses, and delays."""
    global step_counter

    # Chaos injection: ~15% chance after step 10, ~30% after step 15
    if CHAOS_MODE and step_counter > 10:
        chaos_chance = 0.15 if step_counter <= 15 else 0.30
        if _chaos_rng.random() < chaos_chance:
            chaos_type = _chaos_rng.choice(["timeout", "corrupt", "wrong_file"])
            if chaos_type == "timeout":
                return _chaos_rng.choice(CHAOS_TIMEOUTS)
            elif chaos_type == "corrupt":
                return _chaos_rng.choice(CHAOS_CORRUPTIONS)
            elif chaos_type == "wrong_file" and name == "read_file":
                # Return a completely wrong file's content
                wrong_key = _chaos_rng.choice(list(FILESYSTEM.keys()))
                return f"# Note: file may have been moved\n{FILESYSTEM[wrong_key][:500]}"

    if name == "list_files":
        path = inp.get("path", ".")
        files = [f for f in FILESYSTEM if f.startswith(path.rstrip("/"))]
        if not files:
            files = list(FILESYSTEM.keys())
        return "\n".join(files)

    if name == "read_file":
        path = inp.get("path", "")
        content = FILESYSTEM.get(path)
        if content:
            return content
        # Fuzzy match
        for k, v in FILESYSTEM.items():
            if path.endswith(k) or k.endswith(path):
                return v
        return f"Error: File not found: {path}"

    if name == "write_file":
        path = inp.get("path", "")
        content = inp.get("content", "")
        FILESYSTEM[path] = content
        return f"Successfully wrote {len(content)} bytes to {path}"

    if name == "bash":
        cmd = inp.get("command", "").strip()

        # --- Test runners (must check BEFORE npm install since "npm test" contains "npm") ---
        is_test_cmd = any(t in cmd for t in ["npm test", "npm run test", "npx jest", "yarn test", "jest "])
        # Exclude: npm install commands that happen to mention jest/test in package names
        is_install = "install" in cmd or "npm i " in cmd or "npm i\n" in cmd or cmd.endswith("npm i")

        if is_test_cmd and not is_install:
            if step_counter <= 8:
                return "PASS  tests/server.test.ts\n  Products API\n    ✓ should list products (45ms)\n    ✓ should create a product (32ms)\n  Orders API\n    ✓ should place an order (28ms)\n\nTest Suites: 1 passed, 1 total\nTests:       3 passed, 3 total"
            elif step_counter <= 14:
                return """FAIL  tests/server.test.ts
  Products API
    ✓ should list products (45ms)
    ✓ should create a product (32ms)
  Orders API
    ✗ should place an order (28ms)
      Error: Cannot read properties of undefined (reading 'rows')
      at Object.<anonymous> (src/server.ts:87:28)

    ✗ should validate order items (15ms)
      Error: Expected status 400, received 500
      AssertionError: expected 500 to equal 400

Test Suites: 1 failed, 1 total
Tests:       2 passed, 2 failed, 4 total"""
            else:
                return """FAIL  tests/server.test.ts
  Products API
    ✗ should list products (120ms)
      Error: connect ECONNREFUSED 127.0.0.1:5432
    ✗ should create a product (5ms)
      Error: connect ECONNREFUSED 127.0.0.1:5432
  Orders API
    ✗ should place an order (5ms)
      Error: connect ECONNREFUSED 127.0.0.1:5432
    ✗ should validate order items (5ms)
      Error: connect ECONNREFUSED 127.0.0.1:5432
    ✗ should handle concurrent orders (5ms)
      Error: connect ECONNREFUSED 127.0.0.1:5432

Test Suites: 1 failed, 1 total
Tests:       0 passed, 5 failed, 5 total"""

        # --- Package install ---
        if is_install:
            return "added 847 packages in 12s\n\n142 packages are looking for funding\n  run `npm fund` for details"

        # --- Docker ---
        if cmd.startswith("docker"):
            if step_counter > 12:
                return "Error: Cannot connect to the Docker daemon at unix:///var/run/docker.sock. Is the docker daemon running?"
            return "Creating network... done\nCreating ecommerce-api_db_1    ... done\nCreating ecommerce-api_redis_1 ... done"

        # --- Direct psql/createdb invocation (not just mentioning it) ---
        if cmd.startswith("psql") or cmd.startswith("createdb") or cmd.startswith("pg_"):
            if step_counter > 10:
                return "psql: error: connection to server at \"127.0.0.1\", port 5432 failed: Connection refused\n\tIs the server running on that host and accepting TCP/IP connections?"
            return "CREATE TABLE\nCREATE TABLE\nINSERT 0 5"

        # --- HTTP requests ---
        if cmd.startswith("curl") or cmd.startswith("wget"):
            return '{"products":[{"id":1,"name":"Widget","price":9.99,"category":"gadgets","inventory_count":100}],"page":1}'

        # --- File listing ---
        if cmd.startswith("ls") or cmd.startswith("find") or cmd.startswith("tree"):
            entries = list(FILESYSTEM.keys())
            return "\n".join(entries)

        # --- which/type/command -v ---
        if cmd.startswith("which") or cmd.startswith("type ") or cmd.startswith("command"):
            prog = cmd.split()[-1] if len(cmd.split()) > 1 else ""
            return f"/usr/bin/{prog}"

        # --- cat (read file via shell) ---
        if cmd.startswith("cat "):
            path = cmd.split()[-1]
            content = FILESYSTEM.get(path)
            if content:
                return content
            return f"cat: {path}: No such file or directory"

        return f"$ {cmd}\nCommand executed successfully."

    if name == "grep":
        pattern = inp.get("pattern", "")
        results = []
        for path, content in FILESYSTEM.items():
            for i, line in enumerate(content.split("\n"), 1):
                if pattern.lower() in line.lower():
                    results.append(f"{path}:{i}: {line.strip()}")
        return "\n".join(results[:20]) if results else f"No matches found for: {pattern}"

    return "Unknown tool"


# ─── Agent runner ──────────────────────────────────────────────────────

def run_agent(task: str, max_steps: int = 20):
    global step_counter
    step_counter = 0

    # Clear server session so dashboard starts fresh
    try:
        req = urllib.request.Request("http://localhost:8000/session", method="DELETE")
        urllib.request.urlopen(req, timeout=2)
        print("[AgentLens] Server session cleared — dashboard will show live data")
    except Exception:
        print("[AgentLens] Server not running — data saved to real_trajectory.jsonl only")

    client = InstrumentedClient(
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        trajectory_log="real_trajectory.jsonl",
    )

    system = """You are an expert backend engineer doing a code review and bug fix session.
You have access to a codebase with tools: read_file, write_file, bash, grep, list_files.

Your approach:
1. First explore the codebase structure
2. Read the main files to understand the architecture
3. Identify bugs and security issues
4. Fix them one by one, testing after each fix
5. Make sure all tests pass before finishing

Be thorough. Fix ALL bugs you find. Run tests after each change."""

    messages = [{"role": "user", "content": task}]

    print(f"\n{'='*60}")
    print(f"  AgentLens — Real Agent Test")
    print(f"  Task: {task[:80]}...")
    print(f"  Max steps: {max_steps}")
    print(f"{'='*60}\n")

    for step in range(1, max_steps + 1):
        step_counter = step
        print(f"─── Step {step} {'─'*48}")

        response = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=4096,
            system=system,
            tools=TOOLS,
            messages=messages,
        )

        assistant_content = response.content
        messages.append({"role": "assistant", "content": assistant_content})

        for block in assistant_content:
            if block.type == "text":
                text = block.text[:300]
                print(f"  💭 {text}")
            elif block.type == "tool_use":
                inp_str = json.dumps(block.input)
                print(f"  🔧 {block.name}({inp_str[:120]}{'...' if len(inp_str)>120 else ''})")

        if response.stop_reason == "end_turn":
            print(f"\n  ✅ Agent finished naturally at step {step}")
            break

        # Feed tool results back
        tool_results = []
        for block in assistant_content:
            if block.type == "tool_use":
                result = fake_tool_response(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })
                # Show abbreviated result
                first_line = result.split("\n")[0][:100]
                print(f"     → {first_line}")

        if tool_results:
            messages.append({"role": "user", "content": tool_results})

        print()

    client.close()

    # Final analysis
    print(f"\n{'='*60}")
    print(f"  Analysis")
    print(f"{'='*60}")

    from analyzer import TrajectoryAnalyzer
    analyzer = TrajectoryAnalyzer("real_trajectory.jsonl")
    analysis = analyzer.full_analysis()

    with open("real_analysis.json", "w") as f:
        json.dump(analysis, f, indent=2)

    print(f"  Health score : {analysis['health_score']}/100")
    print(f"  Total steps  : {analysis['total_steps']}")
    print(f"  Total tokens : {analysis['summary']['total_tokens']:,}")
    print(f"  Duration     : {analysis['summary']['total_duration_s']:.1f}s")
    print(f"  Anomalies:")
    print(f"    Loops         : {len(analysis['anomalies']['loops'])}")
    print(f"    Context decay : {len(analysis['anomalies']['context_decay'])}")
    print(f"    Repetition    : {len(analysis['anomalies']['repetition'])}")
    print(f"    Error spirals : {len(analysis['anomalies']['error_spirals'])}")
    print(f"\n  Saved: real_trajectory.jsonl, real_analysis.json")
    print(f"  Open dashboard to view → http://localhost:5173")


if __name__ == "__main__":
    if os.path.exists("real_trajectory.jsonl"):
        os.remove("real_trajectory.jsonl")

    task = """I need you to do a thorough code review and bug fix session on this e-commerce API.

The codebase is a Node.js/TypeScript Express API with PostgreSQL and Redis. There are
CRITICAL bugs in production that are causing:

1. **SQL injection vulnerability** in the products search endpoint — the `sort` parameter
   is being interpolated directly into the query string without sanitization
2. **Race condition** in the order placement flow — two concurrent orders can over-sell
   inventory because there's no row-level locking (SELECT ... FOR UPDATE)
3. **Data loss** — when an order is placed, the order_items are never actually saved
   to the database. The order_items table doesn't even exist in schema.sql
4. **Cache invalidation bug** — product mutations (POST/PUT/DELETE) don't invalidate
   the Redis cache, so stale data is served for up to 5 minutes
5. **Security: hardcoded JWT secret** in auth middleware, no token expiry validation
6. **Test failures** — the test suite doesn't properly export the app, doesn't use a
   test database, and has no cleanup between tests

Please:
- Explore the codebase first (list files, read the key files)
- Fix each bug, writing the corrected code
- Run tests after each fix to verify
- Make sure ALL tests pass at the end"""

    run_agent(task, max_steps=20)
