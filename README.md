# Amazon Affiliate Bot

A Python project that combines a Telegram bot and a Flask web dashboard for Amazon affiliate link management, automation, and analytics.

---

## Features

- **Telegram Bot**: Manage Amazon affiliate links and interact with users via Telegram.
- **Web Dashboard**: Monitor and manage affiliate activity through a Flask-powered web interface.
- **Database Integration**: Uses PostgreSQL for robust data storage.
- **Web Scraping**: Extracts product data using BeautifulSoup and lxml.
- **OpenAI Integration**: Leverage AI for content generation and automation.
- **Scheduler & Utilities**: Automated tasks and link validation.

---

## Project Structure

```
AmazonAffiliatedBot/
├── LICENSE
├── README.md
├── .env
├── config.py
├── content_generator.py
├── database.py
├── database_simple.py
├── dealbot.log
├── link_validator.py
├── main.py
├── models.py
├── pyproject.toml
├── requirements.txt
├── scheduler.py
├── scraper.py
├── static/
├── telegram_bot.py
├── templates/
├── uv.lock
├── web_dashboard_clean.py
└── __pycache__/
```

---

## Requirements

- Python 3.11 or newer
- PostgreSQL database (local or cloud)
- Git

---

## Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/AmazonAffiliatedBot.git
   cd AmazonAffiliatedBot
   ```

2. **(Optional) Create and activate a virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install .
   ```
   Or, if you have a `requirements.txt`:
   ```bash
   pip install -r requirements.txt
   ```

---

## Configuration

1. **Set up environment variables**

   Create a `.env` file in the project root with the following content (replace values with your actual credentials):

   ```
   # AmazonBot
   OPENAI_API_KEY=your_openai_api_key
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   TELEGRAM_CHANNEL=@your_telegram_channel
   DATABASE_URL=postgresql://user:password@host/database?sslmode=require&channel_binding=require
   PGDATABASE=your_database
   PGHOST=your_host
   PGPASSWORD=your_password
   PGUSER=your_user
   AMAZON_AFFILIATE_ID=your_amazon_affiliate_id
   AFFILIATE_ID=your_affiliate_id
   ```

   **Never share your `.env` file or credentials publicly.**

2. **Database**

   - Make sure your PostgreSQL database is running and accessible.
   - The `DATABASE_URL` and related variables should match your database setup.

---

## Usage

### Run the Telegram Bot

```bash
python telegram_bot.py
```
or
```bash
python main.py
```
*(Check which file is your main bot entry point.)*

### Run the Web Dashboard

```bash
python web_dashboard_clean.py
```
or for production:
```bash
gunicorn web_dashboard_clean:app
```

---

## Additional Scripts

- `content_generator.py`, `link_validator.py`, `scheduler.py`, `scraper.py`: Utility scripts for content, link validation, scheduling, and scraping.
- `database.py`, `database_simple.py`, `models.py`: Database models and helpers.

---

## Static & Templates

- `static/`: Static files for the web dashboard (CSS, JS, images).
- `templates/`: HTML templates for Flask.

---
<!-- GitAds-Verify: HXXYC9E7544TMKWN6RXD5JU7ENCMLE4G -->
## License

MIT License

Copyright (c) 2025 RafalW3bCraft

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
---

**Note:**  
- Replace placeholder values in `.env` with your actual credentials.
- For any issues, check the logs (`dealbot.log`) or review the code for more details.
- Contributions and issues are
