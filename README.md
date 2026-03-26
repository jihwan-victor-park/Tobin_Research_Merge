# AI Startup Scraper

An automated web scraper that identifies and collects information about AI startups from multiple sources including Y Combinator, Product Hunt, Crunchbase, Wellfound (AngelList), and various accelerators/incubators.

## Features

- **Multi-source scraping**: Y Combinator, Product Hunt, Crunchbase, Wellfound, and more
- **AI detection**: Automatically identifies AI-related startups using keyword matching
- **Comprehensive data collection**: Company name, description, website, funding, team, and social links
- **CSV export**: Easy-to-update CSV format for Excel/Google Sheets
- **Incremental updates**: Re-run to update existing data without duplicates
- **Extensible**: Add custom sources with the generic scraper

## Installation

1. Clone or download this repository
2. Install dependencies:

```bash
cd ai_startup_scraper
pip install -r requirements.txt
```

3. (Optional) Configure API keys:
```bash
cp .env.example .env
# Edit .env and add your Crunchbase API key if you have one
```

## Usage

### Basic Usage

Scrape all sources:
```bash
python main.py --all
```

Scrape specific sources:
```bash
python main.py --sources yc producthunt
```

Scrape only AI-related startups:
```bash
python main.py --all --ai-only
```

Set custom limit per source:
```bash
python main.py --sources yc --limit 100
```

### Available Sources

**Main Sources:**
- `yc` - Y Combinator companies
- `producthunt` - Product Hunt launches
- `crunchbase` - Crunchbase startups (API key recommended)
- `wellfound` - Wellfound/AngelList startups

**Accelerators:**
- `techstars` - Techstars portfolio
- `500global` - 500 Global portfolio
- `alchemist` - Alchemist Accelerator
- `plug_and_play` - Plug and Play Tech Center

### Command-Line Options

```
--all                 Scrape all available sources
--sources [SOURCE...] Specific sources to scrape (space-separated)
--limit N             Maximum companies per source (default: 50)
--ai-only            Only save AI-related startups
--output PATH        Custom output file path
```

### Examples

```bash
# Scrape Y Combinator and accelerators
python main.py --sources yc techstars 500global

# Get 200 companies from each source, AI only
python main.py --all --limit 200 --ai-only

# Save to custom location
python main.py --sources yc --output ~/Desktop/startups.csv
```

## Output Format

The scraper creates a CSV file (`data/ai_startups.csv`) with the following fields:

- `startup_name` - Company name
- `description` - Company description/tagline
- `website` - Company website URL
- `founding_date` - Founding date
- `location` - Company location
- `funding_stage` - Current funding stage (Seed, Series A, etc.)
- `funding_amount` - Total funding raised
- `investors` - List of investors
- `team_size` - Number of employees
- `founders` - Founder names
- `linkedin` - LinkedIn URL
- `twitter` - Twitter/X URL
- `contact_email` - Contact email
- `source` - Data source (YC, Product Hunt, etc.)
- `is_ai_related` - Boolean indicating if AI-related
- `ai_confidence_score` - Confidence score (0.0 to 1.0)
- `scraped_date` - When the data was collected

## AI Detection

The scraper uses keyword matching to identify AI-related startups. Keywords include:

- Core terms: artificial intelligence, machine learning, deep learning, neural networks
- Technologies: GPT, transformers, LLMs, computer vision, NLP
- Applications: chatbots, automation, predictive analytics
- Related: data science, algorithms, model training

The confidence score indicates how many AI keywords were found. Higher scores mean more confident AI classification.

## Updating Data

Simply re-run the scraper to update your dataset. The system:
- Updates existing entries if found (matched by name + source)
- Adds new entries automatically
- Preserves existing data while updating with fresh information

```bash
# Update your dataset
python main.py --all
```

## Access Limitations & Notes

### Crunchbase
- **Limitations**: Heavy rate limiting and anti-bot measures
- **Solution**: Get a Crunchbase API key (paid service) and add to `.env`
- **Alternative**: The scraper includes basic web scraping but data may be limited

### Product Hunt
- **Limitations**: May require authentication for full access
- **Note**: Basic scraping works for public listings

### Wellfound (AngelList)
- **Limitations**: Site structure changes frequently
- **Note**: May require updates to selectors over time

### General Notes
- All sites may implement rate limiting
- Some sites use JavaScript rendering (Selenium may be needed for best results)
- Respect robots.txt and terms of service
- Consider adding delays between requests to be polite

## Extending the Scraper

### Add a Custom Source

```python
from scrapers.generic_scraper import GenericScraper

# Create a scraper for your custom source
scraper = GenericScraper(
    source_name="My Accelerator",
    base_url="https://myaccelerator.com/portfolio"
)

# Scrape
startups = scraper.scrape(limit=50)

# Add to data manager
from utils.data_manager import DataManager
dm = DataManager()
for startup in startups:
    dm.add_startup(startup)
dm.save()
```

### Add to Configuration

Edit [config.py](config.py) to add your source to the `SOURCES` dictionary and update the accelerator configs in [scrapers/generic_scraper.py](scrapers/generic_scraper.py).

## Troubleshooting

### "Access denied (403)" errors
- The site is blocking automated access
- Solutions: Use API keys, add delays, use Selenium, or try different headers

### "No data scraped"
- The site structure may have changed
- Check the scraper code and update HTML selectors
- Try enabling Selenium for JavaScript-heavy sites

### Dependencies issues
```bash
pip install --upgrade -r requirements.txt
```

## Project Structure

```
ai_startup_scraper/
├── main.py                          # Main orchestrator script
├── config.py                        # Configuration and settings
├── requirements.txt                 # Python dependencies
├── .env.example                     # Environment variables template
│
├── README.md                        # Main documentation
├── DIFFICULT_ACCELERATORS.md        # Catalog of 20 hard-to-scrape accelerators
├── SCRAPING_STRATEGIES.md           # Advanced scraping techniques guide
│
├── scripts/                         # Analysis & specialized scripts
│   ├── README.md                   # Scripts documentation
│   ├── quick_w24_analysis.py       # Fast YC W24 analysis (53% AI)
│   ├── analyze_w24_ai.py           # Full W24 analysis with DB
│   ├── analyze_2024_cohorts.py     # Multi-accelerator comparison
│   ├── scrape_recent_batches.py    # Historical YC batch trends
│   └── scrape_startx_2025.py       # StartX interactive scraper
│
├── docs/                            # Analysis documents
│   └── W19_vs_W23_Analysis.md      # Historical batch analysis
│
├── data/                            # Output directory
│   └── ai_startups.csv             # Generated CSV database
│
├── scrapers/                        # Scraper modules
│   ├── yc_scraper.py               # Y Combinator (Algolia API)
│   ├── skydeck_scraper.py          # Berkeley SkyDeck (Algolia API)
│   ├── seedcamp_scraper.py         # Seedcamp
│   ├── antler_scraper.py           # Antler
│   ├── producthunt_scraper.py      # Product Hunt
│   ├── crunchbase_scraper.py       # Crunchbase
│   ├── wellfound_scraper.py        # Wellfound/AngelList
│   ├── startx_scraper.py           # StartX (Stanford)
│   └── generic_scraper.py          # Generic scraper template
│
└── utils/                           # Utility modules
    ├── ai_detector.py              # AI keyword detection
    └── data_manager.py             # CSV data management
```

## Advanced Documentation

For more detailed information about scraping difficult sources:

- **[DIFFICULT_ACCELERATORS.md](DIFFICULT_ACCELERATORS.md)** - Catalog of 20 accelerators/incubators that are particularly challenging to scrape, organized by difficulty tier with specific challenges and approaches
- **[SCRAPING_STRATEGIES.md](SCRAPING_STRATEGIES.md)** - Comprehensive guide to scraping strategies for different difficulty levels, including:
  - Tier-specific strategies (JavaScript-heavy, auth-required, pagination, etc.)
  - Complete code examples and templates
  - Common pitfalls and solutions
  - Legal and ethical considerations
  - Tool recommendations (Selenium, Playwright, API reverse engineering)

These guides are essential if you're planning to expand the scraper to include more challenging sources like Techstars, 500 Global, or On Deck.

## License

This tool is for educational and research purposes. Always respect website terms of service and robots.txt files. Consider using official APIs where available.

## Contributing

Feel free to add more sources, improve scrapers, or enhance the AI detection logic. The modular design makes it easy to extend.

## Future Enhancements

- [ ] Add Selenium support for JavaScript-heavy sites
- [ ] Implement proper Crunchbase API integration
- [ ] Add more accelerators and incubators
- [ ] Improve AI detection with ML models
- [ ] Add email notification for new AI startups
- [ ] Create a web dashboard for viewing data
- [ ] Add database storage option (PostgreSQL/MongoDB)
- [ ] Implement concurrent scraping for speed
