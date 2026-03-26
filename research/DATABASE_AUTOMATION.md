# Database Automation: Auto-Updates & Management

**Goal:** Build a self-updating database that automatically enriches, tracks changes, and stays current

---

## 🎯 Overview

You've built a database. Now make it **self-maintaining**:
- ✅ Auto-enrich missing data
- ✅ Detect changes (funding, shutdowns, launches)
- ✅ Weekly updates
- ✅ Quality monitoring
- ✅ Notifications

---

## 📊 Current Database Status

### **What You Have:**
- **187 companies** in `ai_startups.csv`
- **50 university AI startups** in `university_ai_startups.csv`
- **14M reference data** in Parquet files

### **Tools Built:**
- ✅ `parquet_enricher.py` - Auto-enrich from 14M companies
- ✅ `analyze_data_gaps.py` - Find missing data
- ✅ `snapshot_database.py` - Version control
- ✅ `query_parquet.py` - Search 14M companies

---

## 🔄 Auto-Update Strategy

### **Weekly Update Cycle**

```
Sunday 2am:
├── 1. Take snapshot (backup)
├── 2. Scrape new companies (universities, VCs)
├── 3. Enrich gaps (missing descriptions)
├── 4. Detect changes (funding, websites)
├── 5. Flag issues (404s, shutdowns)
├── 6. Generate report
└── 7. Send notification
```

---

## 🛠️ Component 1: Auto-Enrichment

### **Enrich Missing Data Weekly**

**Create:** `scripts/auto_enrich.py`

```python
#!/usr/bin/env python3
"""
Auto-Enrichment Script
Runs weekly to fill missing data
"""

import pandas as pd
import os
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.parquet_enricher import ParquetEnricher
from scripts.snapshot_database import create_snapshot


def auto_enrich_database(input_csv='data/ai_startups.csv', min_completeness=0.5):
    """
    Auto-enrich companies with missing data

    Args:
        input_csv: Database file
        min_completeness: Only enrich companies below this score
    """

    print("=" * 80)
    print("🔄 AUTO-ENRICHMENT")
    print("=" * 80)
    print(f"Target: {input_csv}\n")

    # Take snapshot first
    print("📸 Creating snapshot...")
    create_snapshot(input_csv, 'before_auto_enrich')

    # Load database
    df = pd.read_csv(input_csv)
    print(f"📊 Loaded {len(df):,} companies\n")

    # Calculate completeness for each company
    def calculate_completeness(row):
        """Calculate how complete a company profile is"""
        fields = ['description', 'website', 'location', 'funding_amount',
                 'team_size', 'linkedin', 'founding_date']

        filled = sum(1 for field in fields if pd.notna(row.get(field)) and row.get(field) != '')
        return filled / len(fields)

    df['completeness'] = df.apply(calculate_completeness, axis=1)

    # Find companies needing enrichment
    needs_enrichment = df[df['completeness'] < min_completeness]

    print(f"🎯 Companies needing enrichment: {len(needs_enrichment):,}")
    print(f"   (Completeness < {min_completeness})\n")

    if len(needs_enrichment) == 0:
        print("✅ All companies are well-enriched!")
        return df

    # Enrich
    enricher = ParquetEnricher()

    companies = needs_enrichment.to_dict('records')
    enriched = enricher.enrich_batch(companies, show_progress=True)

    # Update dataframe
    enriched_df = pd.DataFrame(enriched)
    df.update(enriched_df)

    # Recalculate completeness
    df['completeness'] = df.apply(calculate_completeness, axis=1)

    # Save
    df.to_csv(input_csv, index=False)

    # Stats
    avg_before = needs_enrichment['completeness'].mean()
    avg_after = df[df.index.isin(needs_enrichment.index)]['completeness'].mean()
    improvement = (avg_after - avg_before) / avg_before * 100

    print(f"\n📈 RESULTS:")
    print(f"   Average completeness before: {avg_before:.2%}")
    print(f"   Average completeness after:  {avg_after:.2%}")
    print(f"   Improvement: +{improvement:.1f}%")

    # Save enrichment log
    log_entry = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'companies_enriched': len(needs_enrichment),
        'avg_completeness_before': avg_before,
        'avg_completeness_after': avg_after,
        'improvement': improvement
    }

    log_file = 'data/enrichment_log.csv'
    if os.path.exists(log_file):
        log_df = pd.read_csv(log_file)
        log_df = pd.concat([log_df, pd.DataFrame([log_entry])], ignore_index=True)
    else:
        log_df = pd.DataFrame([log_entry])

    log_df.to_csv(log_file, index=False)

    return df


if __name__ == '__main__':
    auto_enrich_database()
```

### **Schedule Weekly:**
```bash
# Crontab: Every Sunday at 2am
0 2 * * 0 cd /path/to/ai_startup_scraper && python scripts/auto_enrich.py
```

---

## 📊 Component 2: Change Detection

### **Track What Changed**

**Create:** `scripts/detect_changes.py`

```python
#!/usr/bin/env python3
"""
Change Detection
Compares current database with previous snapshot to find changes
"""

import pandas as pd
import os
from datetime import datetime


def detect_changes(current_csv='data/ai_startups.csv'):
    """Detect changes since last snapshot"""

    print("=" * 80)
    print("🔍 CHANGE DETECTION")
    print("=" * 80)

    # Find most recent snapshot
    snapshot_dir = 'data/snapshots'
    snapshots = sorted([f for f in os.listdir(snapshot_dir) if f.endswith('.csv')])

    if len(snapshots) < 2:
        print("⚠️  Need at least 2 snapshots to compare")
        return

    latest_snapshot = os.path.join(snapshot_dir, snapshots[-1])
    previous_snapshot = os.path.join(snapshot_dir, snapshots[-2])

    print(f"Comparing:")
    print(f"  Previous: {snapshots[-2]}")
    print(f"  Current:  {snapshots[-1]}\n")

    # Load both
    current = pd.read_csv(latest_snapshot)
    previous = pd.read_csv(previous_snapshot)

    changes = {
        'new_companies': [],
        'removed_companies': [],
        'funding_changes': [],
        'website_changes': [],
        'description_changes': []
    }

    # Find new companies
    new_companies = set(current['startup_name']) - set(previous['startup_name'])
    changes['new_companies'] = list(new_companies)

    # Find removed companies
    removed = set(previous['startup_name']) - set(current['startup_name'])
    changes['removed_companies'] = list(removed)

    # Find funding changes
    for idx, row in current.iterrows():
        name = row['startup_name']

        # Find in previous
        prev_row = previous[previous['startup_name'] == name]

        if len(prev_row) == 0:
            continue

        prev_row = prev_row.iloc[0]

        # Check funding
        if pd.notna(row.get('funding_amount')) and pd.notna(prev_row.get('funding_amount')):
            if row['funding_amount'] != prev_row['funding_amount']:
                changes['funding_changes'].append({
                    'company': name,
                    'old': prev_row['funding_amount'],
                    'new': row['funding_amount']
                })

        # Check website
        if row.get('website') != prev_row.get('website'):
            changes['website_changes'].append({
                'company': name,
                'old': prev_row.get('website'),
                'new': row.get('website')
            })

    # Print report
    print(f"📊 CHANGES DETECTED:\n")
    print(f"  ➕ New companies: {len(changes['new_companies'])}")
    print(f"  ➖ Removed companies: {len(changes['removed_companies'])}")
    print(f"  💰 Funding changes: {len(changes['funding_changes'])}")
    print(f"  🌐 Website changes: {len(changes['website_changes'])}")

    # Show details
    if changes['new_companies']:
        print(f"\n➕ NEW COMPANIES:")
        for company in changes['new_companies'][:10]:
            print(f"   • {company}")
        if len(changes['new_companies']) > 10:
            print(f"   ... and {len(changes['new_companies']) - 10} more")

    if changes['funding_changes']:
        print(f"\n💰 FUNDING CHANGES:")
        for change in changes['funding_changes'][:5]:
            print(f"   • {change['company']}: ${change['old']:,.0f} → ${change['new']:,.0f}")

    # Save change report
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_file = f'data/change_reports/changes_{timestamp}.json'
    os.makedirs('data/change_reports', exist_ok=True)

    import json
    with open(report_file, 'w') as f:
        json.dump(changes, f, indent=2)

    print(f"\n💾 Saved report: {report_file}")

    return changes


if __name__ == '__main__':
    detect_changes()
```

---

## 🚨 Component 3: Health Monitoring

### **Monitor Database Quality**

**Create:** `scripts/monitor_health.py`

```python
#!/usr/bin/env python3
"""
Database Health Monitor
Checks for issues: 404 websites, missing data, duplicates
"""

import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor
import time


def check_website_status(url, timeout=5):
    """Check if website is accessible"""
    if pd.isna(url) or url == '':
        return 'missing'

    try:
        response = requests.head(url, timeout=timeout, allow_redirects=True)
        if response.status_code == 200:
            return 'ok'
        elif response.status_code == 404:
            return '404'
        else:
            return f'error_{response.status_code}'
    except:
        return 'timeout'


def monitor_database_health(csv_file='data/ai_startups.csv'):
    """Run health checks on database"""

    print("=" * 80)
    print("🏥 DATABASE HEALTH MONITOR")
    print("=" * 80)

    df = pd.read_csv(csv_file)

    print(f"\n📊 Checking {len(df):,} companies...\n")

    health_report = {
        'total_companies': len(df),
        'missing_websites': 0,
        'missing_descriptions': 0,
        'dead_websites': [],
        'duplicates': [],
        'low_quality': []
    }

    # Check for missing data
    health_report['missing_websites'] = df['website'].isna().sum()
    health_report['missing_descriptions'] = df['description'].isna().sum()

    # Check for duplicates
    duplicates = df[df.duplicated(subset=['startup_name'], keep=False)]
    health_report['duplicates'] = duplicates['startup_name'].tolist()

    # Check website status (sample of 50 to avoid rate limiting)
    print("🌐 Checking website status (sampling 50)...")

    sample = df[df['website'].notna()].sample(min(50, len(df)))

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(
            check_website_status,
            sample['website']
        ))

    # Count issues
    dead_websites = [(row['startup_name'], row['website'])
                     for idx, row in sample.iterrows()
                     if results[idx] in ['404', 'timeout']]

    health_report['dead_websites'] = dead_websites

    # Calculate quality scores
    def quality_score(row):
        """Calculate quality score (0-1)"""
        fields = ['description', 'website', 'location', 'funding_amount',
                 'team_size', 'linkedin', 'founding_date']
        filled = sum(1 for f in fields if pd.notna(row.get(f)) and row.get(f) != '')
        return filled / len(fields)

    df['quality_score'] = df.apply(quality_score, axis=1)

    low_quality = df[df['quality_score'] < 0.3]
    health_report['low_quality'] = low_quality['startup_name'].tolist()

    # Print report
    print(f"\n📊 HEALTH REPORT:")
    print(f"   Total companies: {health_report['total_companies']:,}")
    print(f"   ⚠️  Missing websites: {health_report['missing_websites']:,}")
    print(f"   ⚠️  Missing descriptions: {health_report['missing_descriptions']:,}")
    print(f"   ⚠️  Duplicate entries: {len(health_report['duplicates']):,}")
    print(f"   ⚠️  Low quality (<30%): {len(health_report['low_quality']):,}")
    print(f"   ⚠️  Dead websites (sample): {len(dead_websites)}")

    # Overall health score
    total_issues = (
        health_report['missing_websites'] +
        health_report['missing_descriptions'] +
        len(health_report['duplicates']) +
        len(health_report['low_quality'])
    )

    health_percentage = (1 - total_issues / (health_report['total_companies'] * 4)) * 100

    print(f"\n🏥 OVERALL HEALTH: {health_percentage:.1f}%")

    if health_percentage >= 90:
        print("   ✅ Excellent")
    elif health_percentage >= 75:
        print("   ⚠️  Good, but needs attention")
    else:
        print("   ❌ Poor, immediate action needed")

    return health_report


if __name__ == '__main__':
    monitor_database_health()
```

---

## 📧 Component 4: Notifications

### **Email Reports**

**Create:** `scripts/send_report.py`

```python
#!/usr/bin/env python3
"""
Email Report Generator
Sends weekly database update reports
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import pandas as pd
import os


def generate_weekly_report():
    """Generate HTML email report"""

    # Load current stats
    df = pd.read_csv('data/ai_startups.csv')

    # Load enrichment log
    if os.path.exists('data/enrichment_log.csv'):
        log = pd.read_csv('data/enrichment_log.csv')
        last_enrich = log.iloc[-1] if len(log) > 0 else None
    else:
        last_enrich = None

    # Build HTML report
    html = f"""
    <html>
    <body>
        <h2>🚀 AI Startup Database - Weekly Report</h2>
        <p><strong>Date:</strong> {datetime.now().strftime('%Y-%m-%d')}</p>

        <h3>📊 Database Stats</h3>
        <ul>
            <li>Total companies: {len(df):,}</li>
            <li>With websites: {df['website'].notna().sum():,} ({df['website'].notna().sum()/len(df)*100:.1f}%)</li>
            <li>With descriptions: {df['description'].notna().sum():,} ({df['description'].notna().sum()/len(df)*100:.1f}%)</li>
            <li>With funding data: {df['funding_amount'].notna().sum():,}</li>
        </ul>

        <h3>🔄 This Week's Enrichment</h3>
    """

    if last_enrich is not None:
        html += f"""
        <ul>
            <li>Companies enriched: {int(last_enrich['companies_enriched'])}</li>
            <li>Avg completeness improvement: +{last_enrich['improvement']:.1f}%</li>
        </ul>
        """
    else:
        html += "<p>No enrichment this week</p>"

    html += """
        <h3>📈 Top Sources</h3>
    """

    top_sources = df['source'].value_counts().head(5)
    html += "<ul>"
    for source, count in top_sources.items():
        html += f"<li>{source}: {count:,} companies</li>"
    html += "</ul>"

    html += """
        <p>---</p>
        <p><small>Generated by AI Startup Scraper</small></p>
    </body>
    </html>
    """

    return html


def send_email_report(to_email, smtp_config):
    """Send email report"""

    subject = f"AI Startup Database Report - {datetime.now().strftime('%Y-%m-%d')}"
    html_content = generate_weekly_report()

    # Create message
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = smtp_config['from_email']
    msg['To'] = to_email

    # Attach HTML
    html_part = MIMEText(html_content, 'html')
    msg.attach(html_part)

    # Send
    try:
        with smtplib.SMTP(smtp_config['server'], smtp_config['port']) as server:
            server.starttls()
            server.login(smtp_config['username'], smtp_config['password'])
            server.send_message(msg)

        print(f"✅ Report sent to {to_email}")
    except Exception as e:
        print(f"❌ Error sending email: {e}")


if __name__ == '__main__':
    # Configure SMTP settings
    smtp_config = {
        'server': 'smtp.gmail.com',
        'port': 587,
        'username': 'your_email@gmail.com',
        'password': 'your_app_password',  # Use app-specific password
        'from_email': 'your_email@gmail.com'
    }

    send_email_report('recipient@example.com', smtp_config)
```

---

## 🤖 Component 5: Complete Automation

### **Master Automation Script**

**Create:** `scripts/weekly_update.sh`

```bash
#!/bin/bash
# Weekly Database Update Script
# Runs every Sunday at 2am

set -e  # Exit on error

echo "=================================="
echo "🚀 WEEKLY DATABASE UPDATE"
echo "=================================="
echo "Started: $(date)"
echo ""

# Change to project directory
cd /path/to/ai_startup_scraper

# Activate virtual environment if needed
# source venv/bin/activate

# 1. Take snapshot
echo "📸 Creating snapshot..."
python scripts/snapshot_database.py create --reason "weekly_update"

# 2. Scrape new companies (optional - if you have scrapers set up)
# echo "🔍 Scraping new companies..."
# python scripts/scrape_all_universities.py

# 3. Auto-enrich gaps
echo "🔄 Auto-enriching..."
python scripts/auto_enrich.py

# 4. Detect changes
echo "🔍 Detecting changes..."
python scripts/detect_changes.py

# 5. Run health check
echo "🏥 Running health check..."
python scripts/monitor_health.py

# 6. Generate and send report
echo "📧 Sending report..."
python scripts/send_report.py

echo ""
echo "✅ Weekly update complete: $(date)"
echo "=================================="
```

### **Make it executable:**
```bash
chmod +x scripts/weekly_update.sh
```

### **Schedule with Cron:**
```bash
# Edit crontab
crontab -e

# Add this line (runs every Sunday at 2am)
0 2 * * 0 /path/to/ai_startup_scraper/scripts/weekly_update.sh >> /path/to/logs/weekly_update.log 2>&1
```

---

## 📊 Monitoring Dashboard

### **Simple Dashboard**

**Create:** `scripts/dashboard.py`

```python
#!/usr/bin/env python3
"""
Simple Terminal Dashboard
Shows database stats at a glance
"""

import pandas as pd
from datetime import datetime


def show_dashboard():
    """Display dashboard"""

    df = pd.read_csv('data/ai_startups.csv')

    print("\n" + "=" * 80)
    print("📊 AI STARTUP DATABASE DASHBOARD")
    print("=" * 80)
    print(f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Overall stats
    print("📈 OVERVIEW")
    print(f"   Total companies: {len(df):,}")
    print(f"   Data completeness: {(df['description'].notna().sum()/len(df)*100):.1f}%")
    print(f"   Total funding tracked: ${df['funding_amount'].sum():,.0f}")

    # By source
    print(f"\n📁 BY SOURCE")
    sources = df['source'].value_counts().head(5)
    for source, count in sources.items():
        print(f"   {source:30s}: {count:,}")

    # Quality metrics
    print(f"\n✅ QUALITY METRICS")
    print(f"   With websites: {df['website'].notna().sum():,} ({df['website'].notna().sum()/len(df)*100:.1f}%)")
    print(f"   With descriptions: {df['description'].notna().sum():,} ({df['description'].notna().sum()/len(df)*100:.1f}%)")
    print(f"   With LinkedIn: {df['linkedin'].notna().sum():,} ({df['linkedin'].notna().sum()/len(df)*100:.1f}%)")

    # Recent activity
    if os.path.exists('data/enrichment_log.csv'):
        log = pd.read_csv('data/enrichment_log.csv')
        if len(log) > 0:
            last = log.iloc[-1]
            print(f"\n🔄 LAST ENRICHMENT")
            print(f"   Date: {last['timestamp']}")
            print(f"   Companies enriched: {int(last['companies_enriched'])}")
            print(f"   Improvement: +{last['improvement']:.1f}%")

    print("\n" + "=" * 80 + "\n")


if __name__ == '__main__':
    show_dashboard()
```

**Run anytime:**
```bash
python scripts/dashboard.py
```

---

## 🎯 Automation Goals

### **Week 1:**
- ✅ Set up auto-enrichment
- ✅ Create weekly snapshot schedule
- ✅ Build health monitoring

### **Week 2:**
- ✅ Implement change detection
- ✅ Create email reports
- ✅ Test full automation

### **Week 3-4:**
- ✅ Add scraper automation
- ✅ Set up monitoring dashboard
- ✅ Fine-tune schedules

---

## 💡 Pro Tips

1. **Test Before Automating** - Run manually first
2. **Log Everything** - Keep enrichment logs
3. **Start Small** - Weekly updates, not daily
4. **Monitor Costs** - If using APIs/proxies
5. **Backup Regularly** - Snapshots are crucial
6. **Version Control** - Git commit changes

---

## 📝 Checklist

- [ ] Auto-enrichment script working
- [ ] Weekly snapshot schedule set
- [ ] Change detection implemented
- [ ] Health monitoring running
- [ ] Email reports configured
- [ ] Cron jobs scheduled
- [ ] Dashboard accessible
- [ ] Logs being saved

---

**Next Steps:** See [SCALING_DISCOVERY.md](SCALING_DISCOVERY.md) for discovery automation and [ACCELERATOR_LEARNING.md](ACCELERATOR_LEARNING.md) for scraping techniques.
