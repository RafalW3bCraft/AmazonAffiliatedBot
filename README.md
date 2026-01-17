# Amazon Affiliate Bot

A comprehensive Python-based Amazon affiliate marketing bot that automates deal discovery, product search, and affiliate link management with Telegram integration and web dashboard analytics.

---

## 🚀 Features

### Core Functionality
- **🤖 Telegram Bot**: Interactive bot for deal discovery and product search
- **🌐 Web Dashboard**: Real-time analytics and management interface
- **🛍️ Deal Scraping**: Automated scraping of Amazon deals (Today's Deals, Lightning Deals, Best Deals)
- **🔍 Keyword Search**: Search Amazon products by keyword with affiliate tags
- **🖼️ Image Extraction**: Automatic product image extraction and display
- **✅ Link Validation**: Comprehensive affiliate link validation and tag verification
- **📊 Analytics**: Track clicks, conversions, and earnings
- **🤖 AI Content Generation**: OpenAI-powered content generation for engaging posts

### Advanced Features
- **Deal Quality Scoring**: Filters deals by discount, rating, and review count
- **Affiliate Tag Verification**: Ensures affiliate tags persist after redirects
- **Multi-Region Support**: US, UK, DE, FR, CA, JP, AU, IN
- **Deal of the Day Integration**: Dedicated method for featured deals
- **Rate Limiting**: Smart rate limiting with exponential backoff
- **Error Handling**: Comprehensive error handling and logging

---

## 📋 Requirements

- **Python**: 3.11 or newer
- **Database**: PostgreSQL (recommended) or in-memory database for testing
- **API Keys**:
  - Telegram Bot Token (from [@BotFather](https://t.me/botfather))
  - Amazon Affiliate ID (from [Amazon Associates](https://affiliate-program.amazon.com/))
  - OpenAI API Key (optional, for AI content generation)

---

## 🛠️ Installation

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/AmazonAffiliatedBot.git
cd AmazonAffiliatedBot
```

### 2. Create Virtual Environment (Recommended)

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

Or install directly:
```bash
pip install .
```

---

## ⚙️ Configuration

### Environment Variables

Create a `.env` file in the project root:

```env
# Telegram Configuration
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHANNEL=@your_telegram_channel

# Amazon Affiliate
AMAZON_AFFILIATE_ID=one4allmarket-21

# Optional: Regional Affiliate IDs
AMAZON_AFFILIATE_ID_UK=your_uk_affiliate_id
AMAZON_AFFILIATE_ID_DE=your_de_affiliate_id
# ... etc for other regions

# OpenAI (Optional - for AI content generation)
OPENAI_API_KEY=your_openai_api_key

# Database Configuration
DATABASE_URL=postgresql://user:password@host/database?sslmode=require
PGDATABASE=your_database
PGHOST=your_host
PGPASSWORD=your_password
PGUSER=your_user

# Application Settings
MAX_DEALS_PER_SOURCE=5
POST_INTERVAL_MINUTES=6
REQUEST_TIMEOUT=30
RATE_LIMIT_DELAY=2
DEFAULT_REGION=US

# Web Dashboard
FLASK_HOST=0.0.0.0
FLASK_PORT=5000
FLASK_SECRET_KEY=your-secret-key-change-in-production

# Admin Users (comma-separated Telegram user IDs)
ADMIN_USER_IDS=123456789,987654321
```

**⚠️ Security Note**: Never commit your `.env` file to version control!

---

## 🎯 Usage

### Running the Bot

#### Full Mode (Bot + Web Dashboard)
```bash
python main.py
```

#### Bot Only
```bash
python main.py bot
```

#### Web Dashboard Only
```bash
python main.py web
```

#### Post Deals Manually
```bash
python main.py post
```

### Telegram Bot Commands

#### User Commands
- `/start` - Welcome message and setup
- `/help` - Show all available commands
- `/deals` - Get latest deals (all categories)
- `/search <keyword>` - Search products by keyword
  - Example: `/search wireless headphones`
- `/category` - Set preferred product categories
- `/region` - Set your Amazon region
- `/stats` - View your statistics

#### Category Commands
- `/electronics` - Electronics deals
- `/home` - Home & Kitchen deals
- `/fashion` - Fashion deals
- `/sports` - Sports & Outdoors deals
- `/beauty` - Beauty deals
- `/books` - Books deals

#### Admin Commands
- `/admin` - Admin panel
- `/add_deal <url>` - Manually add a deal
- `/broadcast <message>` - Broadcast message to all users

### Web Dashboard

Access the dashboard at: `http://localhost:5000`

**Features:**
- Real-time deal statistics
- User analytics
- Deal management
- Configuration overview
- Health monitoring

---

## 📁 Project Structure

```
AmazonAffiliatedBot/
├── config.py                 # Configuration management
├── scraper.py                # Amazon deal scraper & product search
├── telegram_bot.py           # Telegram bot implementation
├── main.py                   # Main application entry point
├── web_dashboard_clean.py    # Flask web dashboard
├── link_validator.py         # Affiliate link validation
├── content_generator.py      # AI content generation
├── scheduler.py              # Task scheduling
├── database.py               # PostgreSQL database manager
├── database_simple.py        # In-memory database (fallback)
├── models.py                 # Data models
├── static/                   # Web dashboard static files
│   ├── css/
│   └── js/
├── templates/               # Web dashboard templates
│   ├── base.html
│   ├── dashboard.html
│   ├── deals.html
│   └── users.html
├── requirements.txt         # Python dependencies
├── example.env              # Environment variables template
└── README.md                # This file
```

---

## 🔧 Key Features Explained

### 1. Deal Scraping

The bot automatically scrapes deals from multiple Amazon sources:
- Today's Deals
- Lightning Deals
- Best Deals
- Goldbox

**Quality Filtering:**
- Minimum 20% discount
- Minimum 4.0 star rating
- Minimum 50 reviews
- Deal freshness scoring

### 2. Keyword Search

Search Amazon products by keyword:
```python
products = await scraper.search_products_by_keyword(
    keyword="wireless headphones",
    max_results=20,
    affiliate_id="one4allmarket-21"
)
```

**Features:**
- Automatic affiliate tag appending
- Quality filtering (rating, reviews)
- Image extraction
- Complete product information

### 3. Image Extraction

Products automatically include images:
- Extracted from Amazon product pages
- Full resolution URLs
- Fallback handling for missing images
- Displayed in Telegram messages

### 4. Affiliate Tag Verification

Ensures affiliate tags are correctly appended:
- Validates tag presence in URLs
- Verifies tags after redirects
- Logs warnings for missing tags
- Prevents revenue loss

### 5. Deal of the Day

Dedicated method for featured deals:
```python
deal = await scraper.get_deal_of_the_day(
    affiliate_id="one4allmarket-21"
)
```

---

## 🐛 Troubleshooting

### Common Issues

**1. Bot not responding**
- Check `TELEGRAM_BOT_TOKEN` in `.env`
- Verify bot is running: `python main.py bot`
- Check logs: `tail -f dealbot.log`

**2. No deals found**
- Amazon may be rate limiting - increase `RATE_LIMIT_DELAY`
- Check internet connection
- Verify Amazon pages are accessible

**3. Affiliate links not working**
- Verify `AMAZON_AFFILIATE_ID` is correct
- Check affiliate account status
- Review link validation logs

**4. Database connection errors**
- Verify PostgreSQL is running
- Check `DATABASE_URL` format
- Ensure database exists

**5. Images not displaying**
- Check image URLs in logs
- Verify Amazon image CDN access
- Some images may expire (Amazon CDN limitation)

---

## 📊 Performance

### Optimization Tips

1. **Rate Limiting**: Adjust `RATE_LIMIT_DELAY` to balance speed vs. rate limits
2. **Database**: Use PostgreSQL for production (faster than in-memory)
3. **Caching**: Consider caching deal results to reduce API calls
4. **Concurrent Requests**: Adjust `max_concurrent` in link validation

### Expected Performance

- **Deal Scraping**: 2-5 seconds per source
- **Keyword Search**: 3-8 seconds per search
- **Link Validation**: 1-3 seconds per link
- **Image Extraction**: <100ms per product

---

## 🔒 Security

### Best Practices

1. **Environment Variables**: Never commit `.env` file
2. **API Keys**: Rotate keys regularly
3. **Database**: Use strong passwords and SSL connections
4. **Input Validation**: All user inputs are sanitized
5. **Rate Limiting**: Prevents abuse and Amazon blocks

### Security Features

- Input sanitization in web dashboard
- URL validation before processing
- Affiliate tag format validation
- SQL injection protection (parameterized queries)
- XSS protection in web interface

---

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Code Style

- Follow PEP 8 guidelines
- Use type hints where possible
- Add docstrings to functions
- Write tests for new features

---

## 📝 License

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

## 🙏 Acknowledgments

- Amazon Associates Program
- Telegram Bot API
- OpenAI API
- BeautifulSoup for web scraping
- All contributors and users

---

## 📞 Support

For issues, questions, or contributions:
- Check the logs: `dealbot.log`
- Review the code documentation
- Open an issue on GitHub
- Contact the maintainer

---

## 🎯 Roadmap

### Planned Features
- [ ] Amazon Product Advertising API (PA-API) integration
- [ ] Image caching and CDN support
- [ ] Advanced analytics dashboard
- [ ] Multi-language support
- [ ] Automated A/B testing for content
- [ ] Mobile app integration
- [ ] Webhook support for real-time updates

### Recent Updates
- ✅ Image extraction implementation
- ✅ Keyword search functionality
- ✅ Affiliate tag verification
- ✅ Deal of the Day integration
- ✅ Enhanced error handling
- ✅ Improved rate limiting

---

## 📈 Statistics

Track your affiliate performance:
- Total deals posted
- Total clicks
- Conversion rate
- Total earnings
- Active users
- Category breakdown

Access via:
- Telegram: `/stats`
- Web Dashboard: `/api/stats`

---

**Made with ❤️ for Amazon Affiliate Marketers**

*Last Updated: 2025*
