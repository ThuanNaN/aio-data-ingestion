#!/usr/bin/env python3
"""
arXiv Daily Crawler
Crawl new papers from arXiv API based on configured topics.
"""

import os
import sys
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path

import feedparser
import pandas as pd
import requests
import yaml


def setup_logging(log_dir: str) -> logging.Logger:
    """Setup logging configuration."""
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    
    log_file = Path(log_dir) / f"crawl_{datetime.now().strftime('%Y-%m-%d')}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__)


def load_config(config_path: str = "config.yaml") -> dict:
    """Load configuration file."""
    script_dir = Path(__file__).parent
    config_file = script_dir / config_path
    
    with open(config_file, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def build_query(category: str, days_back: int = 1) -> str:
    """
    Build query string for arXiv API.
    Query by category and recent submission date.
    """
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)
    
    date_range = f"[{start_date.strftime('%Y%m%d')}0000 TO {end_date.strftime('%Y%m%d')}2359]"
    query = f"cat:{category} AND submittedDate:{date_range}"
    
    return query


def fetch_papers(base_url: str, category: str, max_results: int, 
                 days_back: int, request_delay: float) -> list:
    """
    Call arXiv API and get list of papers.
    """
    query = build_query(category, days_back)
    
    params = {
        'search_query': query,
        'start': 0,
        'max_results': max_results,
        'sortBy': 'submittedDate',
        'sortOrder': 'descending'
    }
    
    response = requests.get(base_url, params=params, timeout=30)
    response.raise_for_status()
    
    time.sleep(request_delay)
    
    feed = feedparser.parse(response.content)
    
    papers = []
    for entry in feed.entries:
        arxiv_id = entry.id.split('/abs/')[-1]
        
        authors = ', '.join([author.name for author in entry.get('authors', [])])
        
        categories = ', '.join([tag.term for tag in entry.get('tags', [])])
        
        pdf_url = ''
        for link in entry.get('links', []):
            if link.get('type') == 'application/pdf':
                pdf_url = link.href
                break
        
        paper = {
            'arxiv_id': arxiv_id,
            'title': entry.title.replace('\n', ' ').strip(),
            'authors': authors,
            'abstract': entry.summary.replace('\n', ' ').strip(),
            'categories': categories,
            'published': entry.published,
            'updated': entry.updated,
            'pdf_url': pdf_url,
            'primary_category': category
        }
        papers.append(paper)
    
    return papers


def remove_duplicates(papers: list) -> list:
    """Remove duplicate papers based on arxiv_id."""
    seen = set()
    unique_papers = []
    
    for paper in papers:
        if paper['arxiv_id'] not in seen:
            seen.add(paper['arxiv_id'])
            unique_papers.append(paper)
    
    return unique_papers


def save_to_csv(papers: list, output_dir: str, date_str: str = None) -> str:
    """Save papers list to CSV file."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    if date_str is None:
        date_str = datetime.now().strftime('%Y-%m-%d')
    
    output_file = Path(output_dir) / f"papers_{date_str}.csv"
    
    df = pd.DataFrame(papers)
    
    if output_file.exists():
        existing_df = pd.read_csv(output_file)
        df = pd.concat([existing_df, df], ignore_index=True)
        df = df.drop_duplicates(subset=['arxiv_id'], keep='first')
    
    df.to_csv(output_file, index=False, encoding='utf-8-sig')
    
    return str(output_file)


def main() -> int:
    """Main function to run arXiv crawler (cronjob target)."""
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    config = load_config()
    
    logger = setup_logging(config['log_dir'])
    logger.info("=" * 50)
    logger.info("Starting arXiv crawler")
    logger.info(f"Categories: {config['categories']}")
    
    all_papers = []
    
    for category in config['categories']:
        logger.info(f"Crawling category: {category}")
        
        try:
            papers = fetch_papers(
                base_url=config['api']['base_url'],
                category=category,
                max_results=config['max_results_per_category'],
                days_back=config['days_back'],
                request_delay=config['api']['request_delay']
            )
            logger.info(f"  -> Found {len(papers)} papers")
            all_papers.extend(papers)
            
        except requests.RequestException as e:
            logger.error(f"  -> Error crawling {category}: {e}")
            continue
    
    unique_papers = remove_duplicates(all_papers)
    logger.info(f"Total papers after dedup: {len(unique_papers)}")
    
    if unique_papers:
        output_file = save_to_csv(unique_papers, config['output_dir'])
        logger.info(f"Saved to: {output_file}")
    else:
        logger.warning("No papers to save")
    
    logger.info("Done!")
    logger.info("=" * 50)
    
    return len(unique_papers)


if __name__ == "__main__":
    main()
