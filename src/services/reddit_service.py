"""Reddit service for fetching goal clips."""

import asyncpraw
import re
import aiohttp
from typing import Optional, Dict, Any, Union
from bs4 import BeautifulSoup
from src.config import CLIENT_ID, CLIENT_SECRET, USER_AGENT
from src.utils.logger import app_logger
from src.config.teams import premier_league_teams
from src.utils.url_utils import get_base_domain
from src.services.video_service import video_extractor  

async def create_reddit_client() -> asyncpraw.Reddit:
    """Create and return a Reddit client instance.
    
    Returns:
        asyncpraw.Reddit: Authenticated Reddit client
    """
    return asyncpraw.Reddit(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        user_agent=USER_AGENT
    )

def clean_text(text: str) -> str:
    """Clean text to handle unicode characters."""
    return text.encode('ascii', 'ignore').decode('utf-8')

def find_team_in_title(title: str, include_metadata: bool = False) -> Optional[Union[str, Dict[str, Any]]]:
    """Find Premier League team in post title.
    
    Args:
        title (str): Post title to search
        include_metadata (bool): If True, return team data dictionary, otherwise just team name
        
    Returns:
        Optional[Union[str, Dict[str, Any]]]: Team name/data if found, None otherwise
    """
    if not title:
        return None
        
    # Look for score patterns first
    score_patterns = [
        r'(.*?)\s*\[(\d+)\]\s*-\s*(\d+)\s*(.*)',  # Team1 [1] - 0 Team2
        r'(.*?)\s*(\d+)\s*-\s*\[(\d+)\]\s*(.*)',  # Team1 0 - [1] Team2
        r'(.*?)\s*\[(\d+)\s*-\s*(\d+)\]\s*(.*)',  # Team1 [1-0] Team2
    ]
    
    title_lower = title.lower()
    
    for pattern in score_patterns:
        match = re.search(pattern, title_lower)
        if match:
            team1, score1, score2, team2 = match.groups()
            team1 = team1.strip()
            team2 = team2.strip()
            
            # Determine which team scored based on bracket position
            is_team1_scoring = '[' in title.split('-')[0]
            scoring_team = team1 if is_team1_scoring else team2
            other_team = team2 if is_team1_scoring else team1
            
            # Find Premier League team
            for team_name, team_data in premier_league_teams.items():
                team_name_lower = team_name.lower()
                aliases = [alias.lower() for alias in team_data.get('aliases', [])]
                
                # Create patterns with word boundaries
                team_patterns = [rf'\b{re.escape(name)}\b' for name in [team_name_lower] + aliases]
                
                # Check scoring team first
                if any(re.search(pattern, scoring_team) for pattern in team_patterns):
                    if include_metadata:
                        return {
                            'name': team_name,
                            'data': team_data,
                            'is_scoring': True
                        }
                    return team_name
                    
                # Then check other team
                if any(re.search(pattern, other_team) for pattern in team_patterns):
                    if include_metadata:
                        return {
                            'name': team_name,
                            'data': team_data,
                            'is_scoring': False
                        }
                    return team_name
    
    # If no score pattern found, try to find any team in the title
    for team_name, team_data in premier_league_teams.items():
        team_name_lower = team_name.lower()
        aliases = [alias.lower() for alias in team_data.get('aliases', [])]
        
        # Create patterns with word boundaries
        team_patterns = [rf'\b{re.escape(name)}\b' for name in [team_name_lower] + aliases]
        
        if any(re.search(pattern, title_lower) for pattern in team_patterns):
            if include_metadata:
                return {
                    'name': team_name,
                    'data': team_data,
                    'is_scoring': None
                }
            return team_name
            
    return None

async def extract_mp4_link(submission) -> Optional[str]:
    """Extract MP4 link from submission.
    
    Args:
        submission: Reddit submission object
        
    Returns:
        str: MP4 link if found, None otherwise
    """
    try:
        app_logger.info("=== Starting MP4 extraction ===")
        app_logger.info(f"Submission URL: {submission.url}")
        app_logger.info(f"Submission media: {submission.media}")
        
        # Get base domain
        base_domain = get_base_domain(submission.url)
        app_logger.info(f"Base domain: {base_domain}")
        
        # First check if submission URL is already an MP4
        if submission.url.endswith('.mp4'):
            app_logger.info("✓ Direct MP4 URL found")
            return submission.url
            
        # Check if it's a Reddit video
        if hasattr(submission, 'media') and submission.media:
            if 'reddit_video' in submission.media:
                app_logger.info("✓ Reddit video found")
                url = submission.media['reddit_video']['fallback_url']
                app_logger.info(f"Reddit video URL: {url}")
                return url
                
        # Use video extractor for supported base domains
        supported_domains = {'streamff', 'streamin', 'dubz'}
        if base_domain in supported_domains:
            app_logger.info(f"Using video extractor for {base_domain}")
            mp4_url = video_extractor.extract_mp4_url(submission.url)
            if mp4_url:
                app_logger.info(f"✓ Found MP4 URL: {mp4_url}")
                return mp4_url
            else:
                app_logger.warning(f"Video extractor failed to find MP4 URL for: {submission.url}")
                
        app_logger.warning(f"No MP4 URL found for submission: {submission.url}")
        return None
            
    except Exception as e:
        app_logger.error(f"Error extracting MP4 link: {str(e)}")
        return None
