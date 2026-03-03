# Auto News Agent

Automatically finds the best events happening on campus this week and turns them into Instagram-ready posters.

---

## Before You Start (One-Time Setup)

**1. Get a Gemini API key**
- Go to [aistudio.google.com](https://aistudio.google.com) → sign in → "Get API key" → copy it

**2. Save the key on your computer**

Open Terminal, paste this (replace `YOUR_KEY_HERE` with your actual key):
```
echo 'GEMINI_API_KEY=YOUR_KEY_HERE' > .env
```

**3. Install dependencies**
```
pip install -e .
```

---

## How to Use

### Get this week's events (text only)
```
PYTHONPATH=src python -m auto_news_agent.cli --campus usc_la --print
```

### Get events + generate Instagram posters
```
PYTHONPATH=src python -m auto_news_agent.cli --campus usc_la --generate-posters
```

Posters are saved in the `outputs/posters/` folder.

### Regenerate posters from a previous run
```
PYTHONPATH=src python -m auto_news_agent.cli --posters-only outputs/usc_la_weekly_digest_2026-03-02.json --campus usc_la
```

---

## Supported Schools

| Name | Campus ID |
|------|-----------|
| USC | `usc_la` |
| UCLA | `ucla` |
| UC Berkeley | `ucb` |
| UW | `uw` |
| Columbia | `columbia` |
| NYU | `nyu` |
| Stanford | `stanford` |

Just swap `usc_la` in the commands above with whichever school you want.

---

## Where Are My Files?

| File | What it is |
|------|-----------|
| `outputs/*.json` | Event list for the week |
| `outputs/posters/*.png` | Instagram poster images |
