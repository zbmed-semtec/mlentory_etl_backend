# Dagster Basics

### 🎯 What is Dagster? (And Why Should You Care?)

Imagine you're running a restaurant. You have multiple steps to prepare a meal:

1. Get ingredients (extract data)
2. Cook them (transform data)
3. Serve the dish (load data)

Without a system, you'd have to manually:

- Remember which step comes first
- Check if each step is done before starting the next
- Track what succeeded and what failed
- Re-run everything if something breaks

**Dagster is like having a smart kitchen manager** that:

- Knows the order of operations automatically
- Runs steps in the right sequence
- Shows you what's happening in real-time
- Lets you re-run just the parts that failed

In MLentory, Dagster orchestrates your ETL pipeline: extracting ML model data from sources like HuggingFace, transforming it to FAIR4ML format, and loading it into Neo4j and Elasticsearch.

---

### 🚀 Before You Start

**What you'll need:**

- Dagster running (usually at `http://localhost:3000`)
- Your MLentory project set up
- Basic understanding of what ETL means (Extract, Transform, Load)

**What you'll learn:**

- How to view and understand your data pipeline
- How to run individual steps or the entire pipeline
- How to check if things are working
- How to fix problems when they occur

**Don't worry if:**

- You've never used Dagster before
- You're not sure what "materialization" means
- The UI looks overwhelming at first

Let's everything step by step! 🎓

---

### 🧩 Core Concepts (Made Simple)

Let's break down Dagster's main ideas using simple language and examples.

#### 📦 1. Assets: The "Things" Your Pipeline Creates

**Think of it like this:** An asset is like a finished product in a factory. In MLentory, assets are things like:

- Raw data files from HuggingFace
- Normalized data in FAIR4ML format
- Data loaded into Neo4j
- Data indexed in Elasticsearch

**In simple terms:**

- An **asset** = a piece of data your pipeline produces
- Each asset has a **name** (like `hf_raw_models` or `hf_models_normalized`)
- Assets can **depend on** other assets (you need raw data before you can normalize it)

**Real example from MLentory:**

```
hf_raw_data (asset)
    ↓
hf_models_normalized (asset)
    ↓
hf_load_models_to_neo4j+ (asset)
```

This means: first get raw data, then normalize it, then load it into Neo4j.

**Key point:** Assets are the "outputs" of your pipeline. When you create an asset, you're creating that piece of data.

---

#### ▶️ 2. Materialization: Actually Running the Code

**Think of it like this:** Materialization is like pressing the "bake" button on a recipe. The recipe (code) exists, but nothing happens until you actually run it.

**What "materialize" means:**

- It's just a fancy word for "run the code that creates this asset"
- When you materialize an asset, Dagster executes the Python code that produces it
- The asset gets created or updated with fresh data

**What happens when you materialize:**

1. You click "Materialize" in the UI (or run it via code)
2. Dagster checks: "Does this asset depend on other assets first?"
3. If yes, it runs those first (automatically!)
4. Then it runs the code for your asset
5. You see progress in real-time
6. When done, the asset exists and is ready to use

**Example:**

- You want to materialize `hf_models_normalized`
- Dagster sees it needs `hf_raw_data` first
- It automatically runs `hf_raw_data` first
- Then it runs the normalization code
- Now you have normalized data!

**Key point:** Materialization = running the code. Nothing happens until you materialize.

---

#### 🔗 3. Dependencies: The Automatic Ordering System

**Think of it like this:** Dependencies are like prerequisites in school. You can't take Calculus 2 before Calculus 1. Dagster automatically enforces this.

**What dependencies do:**

- They tell Dagster which assets must run before others
- Dagster automatically runs dependencies first
- You don't have to manually figure out the order

**Simple example:**
```
Asset A: Get raw data
Asset B: Normalize data (depends on A)
Asset C: Load to database (depends on B)
```

If you want to run Asset C, Dagster automatically runs:

1. Asset A first
2. Then Asset B
3. Then Asset C

You just click "Materialize" on C, and Dagster handles the rest!

**Visual representation:**
```
A → B → C
```
The arrow means "B needs A first" and "C needs B first".

**Key point:** Dependencies = automatic ordering. You don't have to think about it!

---

#### 📋 4. Jobs: Grouping Related Work

**Think of it like this:** A job is like a recipe that includes multiple steps. Instead of running each step separately, you can run the whole recipe at once.

**What jobs are:**

- A collection of assets that belong together
- A way to run multiple assets at once
- Something you can schedule to run automatically

**Example from MLentory:**

A job called `hf_etl_job` might include:

- Extract raw data from HuggingFace
- Transform to FAIR4ML
- Load into Neo4j
- Index in Elasticsearch

Instead of materializing each asset separately, you can run the whole job!

**Key point:** Jobs = convenience. They let you run related assets together.

---

### 🖥️ The Dagster UI: Your Visual Control Center

The Dagster UI is a web interface (usually at `http://localhost:3000`) where you can see and control your pipelines. Don't worry if it looks complex at first—we'll walk through it step by step.

#### 🗂️ The Main Tabs (What Each One Does)

**1. Assets Tab** 📦

- **What it shows:** List of all assets, its code location and the run status
- **When clicked on View Lineage:** A visual graph of all your assets can be see
- **What you'll see:** Boxes (assets) connected by arrows (dependencies)
- **Colors mean:**
  - 🟢 **Green** = Success! This asset ran successfully
  - 🔴 **Red** = Failed! Something went wrong
  - 🟡 **Yellow** = Running right now
  - ⚪ **Gray** = Not run yet
- **What you can do:** Click any asset to see details, materialize it, view logs

**2. Jobs Tab** 📋

- **What it shows:** All the jobs you've defined
- **What you'll see:** A list of jobs with their status
- **What you can do:** Run a job, see its history, schedule it

**3. Runs Tab** 📊

- **What it shows:** History of everything that's run
- **What you'll see:** A timeline of all executions
- **What you can do:** Click any run to see detailed logs, see what succeeded/failed, debug problems

**4. Schedules Tab** ⏰

- **What it shows:** Jobs that run automatically
- **What you'll see:** When jobs are scheduled to run next
- **What you can do:** Enable/disable schedules, see schedule history

**💡 Pro tip:** Start with the **Assets** tab. It's the most visual and easiest to understand!

---

### 📖 Using the UI: Your First Steps

Let's walk through what you'll actually do in the Dagster UI.

#### 👀 Step 1: Viewing Your Assets

**What you're doing:** Getting familiar with your pipeline structure.

**How to do it:**

1. Open your browser and go to `http://localhost:3000`
2. Click on the **Assets** tab (usually at the top)
3. You'll see a graph with boxes and arrows

**What you're looking at:**

- Each **box** = one asset
- Each **arrow** = a dependency (A → B means B needs A first)
- The **colors** tell you the status

**Try this:**

- Hover over an asset to see quick info
- Click an asset to see full details
- Look at the arrows to understand the flow

---

#### ▶️ Step 2: Materializing Your First Asset

**What you're doing:** Actually running a step of your pipeline.

**How to do it:**
1. Go to the **Assets** tab
2. Find an asset you want to run (start with one that has no dependencies, or use the `+` button)
3. Look for the **"Materialize"** button (usually near the asset name)
4. Click it!

**What happens:**
- The asset status changes to yellow (running)
- You'll see logs appearing in real-time
- When done, it turns green (success) or red (failed)

**Two ways to materialize:**
- **Just this asset:** Click "Materialize" (only runs if dependencies already exist)
- **With dependencies:** Click "Materialize" with a `+` (runs dependencies first automatically)

**💡 Pro tip:** Use the `+` version when you're not sure if dependencies are ready!

**Example:**
- You see `normalized_data` asset
- Click `Materialize+` (the plus means "with dependencies")
- Dagster automatically runs `raw_data` first, then `normalized_data`
- You see both complete!

---

#### 📊 Step 3: Understanding the Asset Graph

**What you're doing:** Learning to "read" the visual representation of your pipeline.

**The graph shows:**
- **Boxes/Circles** = Assets (your data products)
- **Arrows** = Dependencies (the order things must run)
- **Colors** = Status (green/red/yellow/gray)
- **Labels** = Asset names

**How to read it:**
- **Arrows point forward:** If A → B, then A must run before B
- **Multiple arrows into one box:** That asset needs multiple things first
- **No arrows into a box:** This asset has no dependencies (can run first)

**Visual example:**
```
        [A]
         │
         ↓
        [B] ──→ [D]
         │
         ↓
        [C] ──→ [D]
```

This means:
- A has no dependencies (can run first)
- B and C both depend on A
- D depends on both B and C
- So the order is: A → (B and C in parallel) → D

**💡 Pro tip:** Follow the arrows backward to see what needs to run first!

---

#### 📝 Step 4: Viewing What Happened (Runs)

**What you're doing:** Checking the history and results of your pipeline runs.

**How to do it:**
1. Click on the **Runs** tab
2. You'll see a list of all executions
3. Click on any run to see details

**What you'll see:**
- **Which assets ran** (and in what order)
- **Which succeeded** (green checkmarks)
- **Which failed** (red X marks)
- **Logs** for each asset (what actually happened)
- **How long it took** (execution time)
- **Error messages** (if something went wrong)

**Why this matters:**
- You can see what happened even if you weren't watching
- You can debug failures by reading the logs
- You can see how long things take

**💡 Pro tip:** If something fails, the Runs tab is your best friend for debugging!

---

### 🔧 Common Things You'll Do

Here are the most common tasks and how to do them.

#### 🔄 Running an Asset with Its Dependencies

**When you need this:** You want to run an asset, but you're not sure if its dependencies are ready.

**How to do it:**
1. Find the asset in the Assets tab
2. Look for the button with a `+` (like `Materialize+`)
3. Click it!

**What happens:**
- Dagster checks what dependencies are needed
- Runs all dependencies first (automatically)
- Then runs your asset
- Everything happens in the right order

**Example:**
- You want `neo4j_loaded_data`
- It needs `normalized_data` first
- Which needs `raw_data` first
- Click `Materialize+` on `neo4j_loaded_data`
- Dagster runs: `raw_data` → `normalized_data` → `neo4j_loaded_data`
- All automatically!

**💡 Pro tip:** When in doubt, use the `+` version!

---

#### 🔍 Finding Assets in a Large Pipeline

**When you need this:** You have many assets and need to find a specific one.

**How to do it:**
- Use the **search bar** at the top of the Assets tab
- Type part of the asset name
- The graph filters to show matching assets

**Other filters:**
- **By status:** Show only failed assets, or only successful ones
- **By group:** If assets are organized into groups
- **By date:** Show assets materialized in a certain time range

**💡 Pro tip:** Use search when you know the name, use filters when you're looking for problems!

---

#### 📜 Reading Logs to Understand What Happened

**When you need this:** Something didn't work, or you want to see what actually happened.

**How to do it:**
1. Click on an asset (in Assets tab) or a run (in Runs tab)
2. Look for the **Logs** section
3. Scroll through to see what happened

**What logs show:**
- Print statements from your code
- Error messages
- Progress updates
- Execution details

**How to use logs:**
- **For debugging:** Look for error messages (usually in red)
- **For understanding:** Read the print statements to see the flow
- **For timing:** See when each step started and finished

**💡 Pro tip:** Logs are your window into what's actually happening. Use them!

---

### 🔄 Common Workflows (Real Scenarios)

Here are real situations you'll encounter and how to handle them.

#### 🚀 Scenario 1: Running Your Entire Pipeline

**The situation:** You want to run everything from start to finish.

**How to do it:**
1. Go to the **Assets** tab
2. Find the **final asset** (the one that produces your end result)
   - In MLentory, this might be `elasticsearch_indexed_data` or `neo4j_loaded_data`
3. Click **Materialize+** on that asset
4. Watch as Dagster runs everything in order
5. Check the results when done

**What you'll see:**
- Assets turning yellow as they run
- Dependencies running automatically
- Progress in real-time
- Final status (green = success!)

**💡 Pro tip:** The final asset is usually the one with no arrows coming out of it (it's the end of the pipeline).

---

#### 🐛 Scenario 2: Something Failed - How to Fix It

**The situation:** You see a red asset. Something went wrong.

**How to fix it:**
1. **Identify the problem:**
   - Go to **Runs** tab
   - Find the failed run (red status)
   - Click on it

2. **Read the error:**
   - Look at the logs for the failed asset
   - Find the error message (usually at the bottom)
   - Understand what went wrong

3. **Fix the issue:**
   - Maybe your code has a bug
   - Maybe data is missing
   - Maybe a service (like Neo4j) isn't running

4. **Re-run:**
   - Fix the problem
   - Go back to **Assets** tab
   - Click **Materialize** on the failed asset again

**Common issues:**
- **"Dependency not found":** The asset it depends on hasn't been materialized yet
- **"Connection error":** A service (Neo4j, Elasticsearch) isn't running
- **"Validation error":** Data doesn't match the schema

**💡 Pro tip:** Read the error message carefully. It usually tells you exactly what's wrong!

---

#### ✅ Scenario 3: Checking if Everything is Up to Date

**The situation:** You want to see the current status of your entire pipeline.

**How to check:**
1. Go to **Assets** tab
2. Look at the colors:
   - 🟢 **Green** = Up to date and successful
   - 🔴 **Red** = Failed (needs attention)
   - 🟡 **Yellow** = Currently running
   - ⚪ **Gray** = Not materialized yet

**What this tells you:**
- If everything is green, your pipeline is healthy!
- If something is red, you need to fix it
- If something is gray, it hasn't run yet (might be okay if you don't need it)

**💡 Pro tip:** A quick glance at the Assets tab gives you a health check of your entire pipeline!

---

### ❓ Common Questions (FAQ)

**Q: Do I need to materialize assets in order?**
A: No! Dagster handles the order automatically. Just materialize the asset you want, and it will run dependencies first.

**Q: What if I materialize the same asset twice?**
A: That's fine! It will run again and update the asset with fresh data. This is called "re-materialization."

**Q: Can I run multiple assets at the same time?**
A: Yes! If assets don't depend on each other, Dagster can run them in parallel automatically.

**Q: What's the difference between an asset and a job?**
A: An asset is a single piece of data. A job is a collection of assets you can run together.

**Q: How do I know if an asset is "fresh" or "stale"?**
A: Check the Assets tab. Green usually means it's up to date. You can also check the "Last Materialized" timestamp.

**Q: Can I schedule assets to run automatically?**
A: Yes! Use the Schedules tab to set up automatic runs (like "run every day at 2 AM").

**Q: What if I change the code for an asset?**
A: You'll need to re-materialize it for the changes to take effect. The old version of the asset will still exist until you run it again.

---

### ✅ Key Takeaways

**Remember these main points:**

1. **Assets** = The data your pipeline creates (files, database records, etc.)
2. **Materialization** = Running the code to create/update an asset
3. **Dependencies** = Automatic ordering (Dagster runs things in the right order)
4. **The UI** = Your visual control center (see everything, run everything)
5. **Jobs** = Convenient way to run multiple assets together

**The big picture:**

- Dagster handles the complexity of ordering and dependencies
- You just need to know what you want to run
- The UI shows you everything visually
- Logs help you understand what's happening

**Don't worry about:**

- Remembering the exact order of operations (Dagster does this)
- Manually running dependencies (Dagster does this)
- Tracking what succeeded/failed (Dagster shows this)

**Focus on:**

- Understanding what your assets do
- Knowing which asset produces your final result
- Reading logs when something goes wrong
- Using the UI to monitor and control your pipeline

---

### 📋 Quick Reference Card

Keep this handy when you're using Dagster!

| Concept | What It Means | How to Use It |
|---------|--------------|---------------|
| **Asset** | A piece of data your pipeline creates | View in Assets tab, click to see details |
| **Materialize** | Run the code that creates/updates an asset | Click "Materialize" button on an asset |
| **Materialize+** | Run asset with all dependencies | Click "Materialize+" to run everything needed |
| **Dependency** | An asset that must run before another | Shown as arrows in the graph |
| **Job** | Collection of assets that run together | View in Jobs tab, run entire job at once |
| **Run** | One execution of assets | View in Runs tab, see history and logs |
| **Status** | Current state of an asset | 🟢 Green = success, 🔴 Red = failed, 🟡 Yellow = running, ⚪ Gray = not run |

**Color Guide:**

- 🟢 **Green** = Success! Everything worked.
- 🔴 **Red** = Failed! Something went wrong, check logs.
- 🟡 **Yellow** = Running! Wait for it to finish.
- ⚪ **Gray** = Not run yet. This is normal if you haven't materialized it.

---

**Next:** [Neo4j Introduction](neo4j.md) | [Previous: Schema](schema.md) | [Back to Tutorial Overview](../concepts-tutorial.md)
