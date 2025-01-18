"""
Twitter CLI - Command line interface for Twitter API operations with rate limiting
"""

import argparse
from datetime import datetime, timedelta, timezone
import json
import sys
import os
from typing import Optional, Dict, Any, Literal, List
from requests_oauthlib import OAuth1Session
from dotenv import load_dotenv
import time
from dataclasses import dataclass
from collections import defaultdict
import mimetypes


class Period:
    """Time period for rate limiting"""
    def __init__(self, hr: int = 0, min: int = 0):
        self.hr = hr
        self.min = min

    def to_timedelta(self) -> timedelta:
        return timedelta(hours=self.hr, minutes=self.min)


class RateLimit:
    """Rate limit configuration"""
    def __init__(self, rate: int, period: Period, scope: Literal["PER USER", "PER APP"]):
        self.rate = rate
        self.period = period
        self.scope = scope


class EndpointLimits:
    """Rate limits and parameters for an endpoint"""
    def __init__(
        self,
        user_limit: Optional[RateLimit] = None,
        app_limit: Optional[RateLimit] = None,
        results: Optional[int] = None,
        query_length: Optional[int] = None,
        params: Optional[Dict[str, str]] = None
    ):
        self.user_limit = user_limit
        self.app_limit = app_limit
        self.results = results
        self.query_length = query_length
        self.params = params


class RateLimitState:
    """Current state of rate limiting for an endpoint"""
    def __init__(
        self,
        endpoint: str,
        scope: Literal["PER USER", "PER APP"],
        scope_id: str,
        requests_remaining: int,
        reset_at: datetime = datetime.now(timezone.utc),
        window_start: datetime = datetime.now(timezone.utc)
    ):
        self.endpoint = endpoint
        self.scope = scope
        self.scope_id = scope_id
        self.requests_remaining = requests_remaining
        self.reset_at = reset_at
        self.window_start = window_start

    def is_limited(self) -> bool:
        """Check if rate limit is currently exceeded"""
        return self.requests_remaining <= 0 and datetime.now(timezone.utc) < self.reset_at

    def reset_if_expired(self) -> None:
        """Reset rate limit if window has expired"""
        if datetime.now(timezone.utc) >= self.reset_at:
            self.reset()

    def reset(self) -> None:
        """Reset rate limit state with fresh window"""
        self.window_start = datetime.now(timezone.utc)
        self.requests_remaining = TWITTER_RATE_LIMITS[self.endpoint].user_limit.rate if self.scope == "PER USER" else TWITTER_RATE_LIMITS[self.endpoint].app_limit.rate
        period = TWITTER_RATE_LIMITS[self.endpoint].user_limit.period if self.scope == "PER USER" else TWITTER_RATE_LIMITS[self.endpoint].app_limit.period
        self.reset_at = self.window_start + period.to_timedelta()


class TwitterRateLimiter:
    """Rate limiter for Twitter API endpoints"""
    def __init__(self):
        self.states: Dict[str, Dict[str, RateLimitState]] = defaultdict(dict)

    def _get_state_key(self, endpoint: str, scope: Literal["PER USER", "PER APP"], scope_id: str) -> str:
        return f"{endpoint}:{scope}:{scope_id}"

    def _get_or_create_state(self, endpoint: str, scope: Literal["PER USER", "PER APP"], scope_id: str) -> RateLimitState:
        key = self._get_state_key(endpoint, scope, scope_id)
        if key not in self.states[endpoint]:
            limit_config = TWITTER_RATE_LIMITS[endpoint]
            rate_limit = limit_config.user_limit if scope == "PER USER" else limit_config.app_limit
            if rate_limit:
                state = RateLimitState(
                    endpoint=endpoint,
                    scope=scope,
                    scope_id=scope_id,
                    requests_remaining=rate_limit.rate
                )
                self.states[endpoint][key] = state
        return self.states[endpoint][key]

    def check_rate_limit(self, endpoint: str, user_id: Optional[str] = None, app_id: Optional[str] = None) -> bool:
        """Check if request can proceed under rate limits"""
        if endpoint not in TWITTER_RATE_LIMITS:
            return True

        limits = TWITTER_RATE_LIMITS[endpoint]
        is_limited = False

        if limits.user_limit and user_id:
            state = self._get_or_create_state(endpoint, "PER USER", user_id)
            state.reset_if_expired()
            if state.is_limited():
                is_limited = True

        if limits.app_limit and app_id:
            state = self._get_or_create_state(endpoint, "PER APP", app_id)
            state.reset_if_expired()
            if state.is_limited():
                is_limited = True

        return not is_limited

    def record_request(self, endpoint: str, user_id: Optional[str] = None, app_id: Optional[str] = None) -> None:
        """Record a request and update rate limit states"""
        if endpoint not in TWITTER_RATE_LIMITS:
            return

        limits = TWITTER_RATE_LIMITS[endpoint]

        if limits.user_limit and user_id:
            state = self._get_or_create_state(endpoint, "PER USER", user_id)
            state.reset_if_expired()
            state.requests_remaining = max(0, state.requests_remaining - 1)

        if limits.app_limit and app_id:
            state = self._get_or_create_state(endpoint, "PER APP", app_id)
            state.reset_if_expired()
            state.requests_remaining = max(0, state.requests_remaining - 1)

    def get_rate_limit_info(self, endpoint: str, user_id: Optional[str] = None, app_id: Optional[str] = None) -> Dict:
        """Get current rate limit information for an endpoint"""
        if endpoint not in TWITTER_RATE_LIMITS:
            return {"error": "Endpoint not found"}

        info = {"endpoint": endpoint, "limits": {}}

        if user_id:
            state = self._get_or_create_state(endpoint, "PER USER", user_id)
            state.reset_if_expired()
            info["limits"]["user"] = {
                "requests_remaining": state.requests_remaining,
                "reset_at": state.reset_at.isoformat(),
                "window_start": state.window_start.isoformat()
            }

        if app_id:
            state = self._get_or_create_state(endpoint, "PER APP", app_id)
            state.reset_if_expired()
            info["limits"]["app"] = {
                "requests_remaining": state.requests_remaining,
                "reset_at": state.reset_at.isoformat(),
                "window_start": state.window_start.isoformat()
            }

        return info


class TwitterAuth:
    """Handle Twitter authentication with PIN-based OAuth flow and token caching"""
    def __init__(self):
        load_dotenv()
        self.consumer_key = os.getenv('TWITTER_API_KEY')
        self.consumer_secret = os.getenv('TWITTER_API_SECRET')
        self.token_cache_file = os.path.join(os.path.dirname(__file__), '..', '.cache', 'twitter_tokens.json')

        if not all([self.consumer_key, self.consumer_secret]):
            raise ValueError("Missing required Twitter API credentials in .env file")
        
        # Ensure cache directory exists
        os.makedirs(os.path.dirname(self.token_cache_file), exist_ok=True)

    def _load_cached_tokens(self) -> tuple[str, str] | None:
        try:
            if os.path.exists(self.token_cache_file):
                with open(self.token_cache_file, 'r') as f:
                    tokens = json.load(f)
                return tokens.get('access_token'), tokens.get('access_token_secret')
        except Exception as e:
            print(f"Warning: Failed to load cached tokens: {e}")
        return None

    def _save_tokens(self, access_token: str, access_token_secret: str):
        try:
            with open(self.token_cache_file, 'w') as f:
                json.dump({
                    'access_token': access_token,
                    'access_token_secret': access_token_secret
                }, f)
        except Exception as e:
            print(f"Warning: Failed to cache tokens: {e}")

    def get_oauth(self) -> OAuth1Session:
        cached_tokens = self._load_cached_tokens()
        if cached_tokens:
            access_token, access_token_secret = cached_tokens
            return OAuth1Session(
                self.consumer_key,
                client_secret=self.consumer_secret,
                resource_owner_key=access_token,
                resource_owner_secret=access_token_secret
            )

        # Explicitly set callback to 'oob' (Out Of Band) for PIN-based auth
        oauth = OAuth1Session(
            self.consumer_key,
            client_secret=self.consumer_secret,
            callback_uri='oob'
        )
        
        try:
            fetch_response = oauth.fetch_request_token("https://api.twitter.com/oauth/request_token")
        except ValueError:
            raise ValueError("Failed to get request token. Check your API key and secret.")

        resource_owner_key = fetch_response.get("oauth_token")
        resource_owner_secret = fetch_response.get("oauth_token_secret")

        base_authorization_url = "https://api.twitter.com/oauth/authorize"
        authorization_url = oauth.authorization_url(base_authorization_url)
        print("\n🔑 Please go to this URL to authorize the application:")
        print(f"\n{authorization_url}\n")
        
        verifier = input("Enter the PIN from the website: ").strip()

        access_token_url = "https://api.twitter.com/oauth/access_token"
        oauth = OAuth1Session(
            self.consumer_key,
            client_secret=self.consumer_secret,
            resource_owner_key=resource_owner_key,
            resource_owner_secret=resource_owner_secret,
            verifier=verifier
        )

        oauth_tokens = oauth.fetch_access_token(access_token_url)
        access_token = oauth_tokens["oauth_token"]
        access_token_secret = oauth_tokens["oauth_token_secret"]

        self._save_tokens(access_token, access_token_secret)
        print("✅ Authentication tokens cached for future use")

        return OAuth1Session(
            self.consumer_key,
            client_secret=self.consumer_secret,
            resource_owner_key=access_token,
            resource_owner_secret=access_token_secret
        )


class TwitterAPI:
    def __init__(self):
        self.auth = TwitterAuth()
        self.oauth = self.auth.get_oauth()
        self.api_base = "https://api.twitter.com/2"
        self.rate_limiter = TwitterRateLimiter()
        self._user_id = None
        self._user_id_cache_file = os.path.join(os.path.dirname(__file__), '..', '.cache', 'twitter_user_id.json')
        self._load_cached_user_id()

    def _load_cached_user_id(self):
        """Load cached user ID if available"""
        try:
            if os.path.exists(self._user_id_cache_file):
                with open(self._user_id_cache_file, 'r') as f:
                    data = json.load(f)
                    self._user_id = data.get('user_id')
        except Exception:
            pass

    def _save_user_id(self, user_id: str):
        """Save user ID to cache"""
        try:
            with open(self._user_id_cache_file, 'w') as f:
                json.dump({'user_id': user_id}, f)
        except Exception:
            pass

    @property
    def user_id(self) -> str:
        """Get user ID with caching"""
        if self._user_id is None:
            result = self._make_request("get", "users/me")
            if "error" in result:
                raise ValueError(f"Failed to get user ID: {result['error']}")
            self._user_id = result["data"]["id"]
            self._save_user_id(self._user_id)
        return self._user_id

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Core request method with rate limiting and error handling"""
        endpoint_path = endpoint.replace(self.api_base, "").lstrip("/")
        endpoint_id = f"{method.upper()} /{endpoint_path}"
        url = f"{self.api_base}/{endpoint}"

        try:
            if 'headers' not in kwargs:
                kwargs['headers'] = {}
            kwargs['headers'].update({"User-Agent": "v2TwitterPython"})
            
            # Make the request
            response = getattr(self.oauth, method)(url, **kwargs)
            
            # Get data first
            try:
                data = response.json()
                if response.status_code in (200, 201):
                    return data
            except Exception as e:
                return {"error": f"Failed to parse response: {str(e)}"}
            
            # Only handle rate limits if we didn't get data
            if response.status_code == 429:
                reset_time = int(response.headers.get('x-rate-limit-reset', 0))
                current_time = int(datetime.now().timestamp())
                sleep_time = max(reset_time - current_time, 0)
                
                if sleep_time > 0:
                    reset_at = datetime.fromtimestamp(reset_time).strftime("%H:%M:%S")
                    current_at = datetime.now().strftime("%H:%M:%S")
                    print(f"\n⛔ Twitter API rate limit hit")
                    print(f"⏰ Current time: {current_at}")
                    print(f"🔄 Reset at: {reset_at}")
                    print(f"⌛ Waiting {sleep_time} seconds...")
                    print(f"📝 Endpoint: {endpoint_id}")
                    print(f"📊 Remaining: 0/{response.headers.get('x-rate-limit-limit', '?')}")
                    time.sleep(sleep_time)
                    
                    # Try again after waiting
                    return self._make_request(method, endpoint, **kwargs)
            
            # Handle other errors
            if 'errors' in data:
                return {"error": data['errors'][0]['message']}
            elif 'error' in data:
                return {"error": data['error']['message']}
            
            return {"error": f"API returned status code {response.status_code}: {response.text}"}
            
        except Exception as e:
            return {"error": str(e)}

    def get_user_info(self, username: str) -> Dict[str, Any]:
        """Get user information"""
        print(f"\n👤 Fetching info for @{username}")
        params = {
            "user.fields": "created_at,description,public_metrics,verified,location,url,profile_image_url,entities,pinned_tweet_id"
        }
        return self._make_request(
            "get",
            f"users/by/username/{username}",
            params=params
        )
        
    def get_user_tweets(self, user_id: str, limit: int = 10) -> Dict[str, Any]:
        """Get tweets from a user"""
        print(f"\n📜 Fetching tweets (limit: {limit})")
        
        params = {
            "max_results": min(limit, 100),
            "tweet.fields": "created_at,public_metrics,author_id,text,context_annotations",
            "expansions": "author_id,referenced_tweets.id",
            "user.fields": "username,name,verified"
        }
        
        return self._make_request("get", f"users/{user_id}/tweets", params=params)

    def search_tweets(self, query: str, limit: int = 10) -> Dict[str, Any]:
        """Search tweets with enhanced feedback and Twitter search operators"""
        formatted_query = f"({query}) -is:retweet lang:en"
        print(f"\n🔍 Searching for: '{formatted_query}' (limit: {limit})")
        
        params = {
            "query": formatted_query,
            "max_results": min(limit, 100),
            "tweet.fields": "created_at,public_metrics,author_id,text,context_annotations,entities,geo,lang,referenced_tweets",
            "expansions": "author_id,referenced_tweets.id,attachments.media_keys,entities.mentions.username",
            "user.fields": "username,name,verified,profile_image_url",
            "media.fields": "type,url,preview_image_url"
        }
        
        return self._make_request("get", "tweets/search/recent", params=params)

    def get_tweet(self, tweet_id: str) -> Dict[str, Any]:
        params = {
            "tweet.fields": "created_at,public_metrics,author_id,text"
        }
        return self._make_request(
            "get",
            f"tweets/{tweet_id}",
            params=params
        )

    def upload_media(self, media_path: str) -> Dict[str, Any]:
        """Upload media file to Twitter and return media ID"""
        if not os.path.exists(media_path):
            return {"error": "Media file not found"}
            
        file_size = os.path.getsize(media_path)
        mime_type = mimetypes.guess_type(media_path)[0]
        
        # INIT phase
        init_payload = {
            'command': 'INIT',
            'total_bytes': file_size,
            'media_type': mime_type,
        }
        
        init_response = self.oauth.post(
            'https://upload.twitter.com/1.1/media/upload.json',
            data=init_payload
        )
        
        if init_response.status_code != 202:
            return {"error": f"Media upload initialization failed: {init_response.text}"}
        
        media_id = init_response.json()['media_id']
        
        # APPEND phase
        segment_index = 0
        bytes_sent = 0
        
        with open(media_path, 'rb') as media_file:
            while bytes_sent < file_size:
                chunk = media_file.read(4*1024*1024)  # 4MB chunks
                if not chunk:
                    break
                    
                append_payload = {
                    'command': 'APPEND',
                    'media_id': media_id,
                    'segment_index': segment_index
                }
                
                files = {'media': chunk}
                
                append_response = self.oauth.post(
                    'https://upload.twitter.com/1.1/media/upload.json',
                    data=append_payload,
                    files=files
                )
                
                if append_response.status_code != 204:
                    return {"error": f"Media chunk upload failed: {append_response.text}"}
                    
                segment_index += 1
                bytes_sent = media_file.tell()
        
        # FINALIZE phase
        finalize_payload = {
            'command': 'FINALIZE',
            'media_id': media_id
        }
        
        finalize_response = self.oauth.post(
            'https://upload.twitter.com/1.1/media/upload.json',
            data=finalize_payload
        )
        
        if finalize_response.status_code != 201:
            return {"error": f"Media upload finalization failed: {finalize_response.text}"}
        
        return {"media_id": str(media_id)}

    def create_tweet(self, text: str, media_path: Optional[str] = None, reply_to_id: Optional[str] = None) -> Dict[str, Any]:
        if len(text) > 280:
            return {"error": "Tweet exceeds 280 character limit"}
        
        payload = {"text": text}
        
        if media_path:
            if not os.path.exists(media_path):
                return {"error": f"Media file not found: {media_path}"}
            file_size = os.path.getsize(media_path)
            if file_size > 15 * 1024 * 1024:
                return {"error": "Media file exceeds maximum size limit"}
            
            media_result = self.upload_media(media_path)
            if "error" in media_result:
                return media_result
            
            payload["media"] = {"media_ids": [media_result["media_id"]]}
        
        if reply_to_id:
            payload["reply"] = {"in_reply_to_tweet_id": reply_to_id}
        
        return self._make_request("post", "tweets", json=payload)

    def like_tweet(self, tweet_id: str) -> Dict[str, Any]:
        payload = {"tweet_id": tweet_id}
        return self._make_request(
            "post",
            f"users/{self.user_id}/likes",
            json=payload
        )

    def unlike_tweet(self, tweet_id: str) -> Dict[str, Any]:
        return self._make_request(
            "delete",
            f"users/{self.user_id}/likes/{tweet_id}"
        )

    def get_home_timeline(self, limit: int = 20) -> Dict[str, Any]:
        """Get user's home timeline"""
        print(f"\n📱 Fetching home timeline (limit: {limit})")
        
        params = {
            "max_results": min(limit, 100),
            "tweet.fields": "created_at,public_metrics,author_id,text",
            "expansions": "author_id",
            "user.fields": "username,name,verified"
        }
        
        return self._make_request(
            "get",
            f"users/{self.user_id}/timelines/reverse_chronological",
            params=params
        )

    def delete_tweet(self, tweet_id: str) -> Dict[str, Any]:
        """Delete a tweet by ID"""
        return self._make_request(
            "delete",
            f"tweets/{tweet_id}"
        )

def initialize_rate_limits() -> Dict[str, EndpointLimits]:
    """Initialize the rate limit configurations for all endpoints"""
    rate_limits = {}
    
    # Add rate limits for each endpoint
    rate_limits["DELETE /2/tweets/:id"] = EndpointLimits(
        user_limit=RateLimit(rate=17, period=Period(hr=24), scope="PER USER"),
        app_limit=RateLimit(rate=17, period=Period(hr=24), scope="PER APP")
    )
    
    rate_limits["GET /2/users/me"] = EndpointLimits(
        user_limit=RateLimit(
            rate=25,
            period=Period(hr=24),
            scope="PER USER"
        )
    )
    
    rate_limits["GET /2/tweets/search/recent"] = EndpointLimits(
        user_limit=RateLimit(
            rate=1,
            period=Period(min=15),
            scope="PER USER"
        ),
        app_limit=RateLimit(
            rate=1,
            period=Period(min=15),
            scope="PER APP"
        ),
        results=100,
        query_length=512
    )
    
    rate_limits["GET /2/tweets/:id"] = EndpointLimits(
        user_limit=RateLimit(
            rate=1,
            period=Period(min=15),
            scope="PER USER"
        )
    )

    rate_limits["GET /2/users/:id/followers"] = EndpointLimits(
        user_limit=RateLimit(
            rate=1,
            period=Period(min=15),
            scope="PER USER"
        ),
        app_limit=RateLimit(
            rate=1,
            period=Period(min=15),
            scope="PER APP"
        )
    )

    rate_limits["POST /2/tweets"] = EndpointLimits(
        user_limit=RateLimit(
            rate=17,
            period=Period(hr=24),
            scope="PER USER"
        ),
        app_limit=RateLimit(
            rate=17,
            period=Period(hr=24),
            scope="PER APP"
        )
    )

    rate_limits["POST /2/users/:id/likes"] = EndpointLimits(
        user_limit=RateLimit(
            rate=50,
            period=Period(hr=24),
            scope="PER USER"
        )
    )

    rate_limits["DELETE /2/users/:id/likes/:tweet_id"] = EndpointLimits(
        user_limit=RateLimit(
            rate=50,
            period=Period(hr=24),
            scope="PER USER"
        )
    )

    rate_limits["GET /2/users/:id/timelines/reverse_chronological"] = EndpointLimits(
        user_limit=RateLimit(
            rate=1,
            period=Period(min=15),
            scope="PER USER"
        )
    )

    return rate_limits

# Initialize global rate limits
TWITTER_RATE_LIMITS = initialize_rate_limits()

def format_tweet(tweet: Dict[str, Any]) -> str:
    """Format a tweet for display"""
    created_at = tweet.get("created_at", "Unknown date")
    metrics = tweet.get("public_metrics", {})
    
    return (
        f"\n🐦 Tweet ID: {tweet.get('id')}\n"
        f"👤 Author ID: {tweet.get('author_id')}\n"
        f"📅 Created: {created_at}\n"
        f"📝 Text: {tweet.get('text')}\n"
        f"📊 Metrics: {json.dumps(metrics, indent=2)}\n"
        f"{'-' * 50}"
    )

def format_user(user: Dict[str, Any]) -> str:
    """Format a user for display"""
    metrics = user.get("public_metrics", {})
    created_at = user.get("created_at", "Unknown date")
    
    return (
        f"\n👤 User: @{user.get('username')}\n"
        f"📛 Name: {user.get('name')}\n"
        f"🆔 ID: {user.get('id')}\n"
        f"📅 Joined: {created_at}\n"
        f"🖼️ Profile Image: {user.get('profile_image_url', 'Not available')}\n"
        f"📊 Metrics: {json.dumps(metrics, indent=2)}\n"
        f"{'-' * 50}"
    )

def setup_argparse() -> argparse.ArgumentParser:
    """Setup command line argument parsing"""
    parser = argparse.ArgumentParser(
        description='Twitter CLI Tool with Rate Limiting',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Add reset-cache command
    reset_cache_parser = subparsers.add_parser('reset-cache', help='Reset cached authentication tokens')

    # User info command
    user_parser = subparsers.add_parser('user', help='Get user information')
    user_parser.add_argument('username', help='Twitter username')

    # Tweets command
    tweets_parser = subparsers.add_parser('tweets', help='Get user tweets')
    tweets_parser.add_argument('username', help='Twitter username')
    tweets_parser.add_argument('--limit', type=int, default=10, help='Number of tweets to retrieve')

    # Search command
    search_parser = subparsers.add_parser('search', help='Search tweets')
    search_parser.add_argument('query', help='Search query')
    search_parser.add_argument('--limit', type=int, default=10, help='Number of tweets to retrieve')

    # Post command
    post_parser = subparsers.add_parser('post', help='Create a new tweet')
    post_parser.add_argument('text', help='Tweet text (max 280 characters)')
    post_parser.add_argument('--media', help='Path to media file to upload with tweet')
    post_parser.add_argument('--reply-to', help='Tweet ID to reply to')

    # Like/Unlike commands
    like_parser = subparsers.add_parser('like', help='Like a tweet')
    like_parser.add_argument('tweet_id', help='ID of tweet to like')

    unlike_parser = subparsers.add_parser('unlike', help='Unlike a tweet')
    unlike_parser.add_argument('tweet_id', help='ID of tweet to unlike')

    # Timeline command
    timeline_parser = subparsers.add_parser('timeline', help='Get your home timeline')
    timeline_parser.add_argument('--limit', type=int, default=20, help='Number of tweets to retrieve')

    # Delete tweet command
    delete_parser = subparsers.add_parser('delete', help='Delete a tweet')
    delete_parser.add_argument('tweet_id', help='ID of tweet to delete')

    return parser

def format_search_results(result: Dict[str, Any], query: str) -> None:
    """Format and display search results"""
    if "error" in result:
        print(f"\n❌ Search error: {result['error']}")
        return
        
    if not result.get("data"):
        print(f"\n📭 No tweets found matching: '{query}'")
        return
        
    tweet_count = len(result.get("data", []))
    print(f"\n✅ Found {tweet_count} tweets")
    
    users = {user["id"]: user for user in result.get("includes", {}).get("users", [])}
    
    for tweet in result["data"]:
        author = users.get(tweet.get("author_id", ""), {})
        metrics = tweet.get("public_metrics", {})
        print(
            f"\n👤 @{author.get('username', 'unknown')} {'✓' if author.get('verified') else ''}"
            f"\n💬 {tweet.get('text')}"
            f"\n📅 {tweet.get('created_at', 'unknown')}"
            f"\n❤️  {metrics.get('like_count', 0)} 🔄 {metrics.get('retweet_count', 0)} 💬 {metrics.get('reply_count', 0)}"
            f"\n{'-' * 50}"
        )
    
    if result.get("meta", {}).get("next_token"):
        print("\nℹ️ More results available. Use --limit to retrieve more.")

def main():
    """Main CLI entry point"""
    parser = setup_argparse()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    try:
        if args.command == 'reset-cache':
            auth = TwitterAuth()
            if os.path.exists(auth.token_cache_file):
                os.remove(auth.token_cache_file)
                print("✅ Authentication cache cleared successfully")
            else:
                print("ℹ️ No cache file found")
            return

        twitter = TwitterAPI()
        
        if args.command == 'user':
            result = twitter.get_user_info(args.username)
            if 'error' in result:
                print(f"\n❌ Error: {result['error']}")
            else:
                user_data = result.get('data', {})
                metrics = user_data.get("public_metrics", {})
                print(
                    f"\n✅ User Profile:"
                    f"\n👤 @{user_data.get('username')} {'✓' if user_data.get('verified') else ''}"
                    f"\n📛 Name: {user_data.get('name')}"
                    f"\n📝 Bio: {user_data.get('description')}"
                    f"\n📍 Location: {user_data.get('location', 'Not specified')}"
                    f"\n🔗 URL: {user_data.get('url', 'Not specified')}"
                    f"\n🖼️ Profile Image: {user_data.get('profile_image_url', 'Not available')}"
                    f"\n📅 Joined: {user_data.get('created_at', 'Unknown')}"
                    f"\n📊 Stats:"
                    f"\n   • Followers: {metrics.get('followers_count', 0):,}"
                    f"\n   • Following: {metrics.get('following_count', 0):,}"
                    f"\n   • Tweets: {metrics.get('tweet_count', 0):,}"
                    f"\n{'-' * 50}"
                )

        elif args.command == 'tweets':
            user_result = twitter.get_user_info(args.username)
            if 'error' in user_result:
                print(f"❌ Error: {user_result['error']}")
                return
                
            user_id = user_result['data']['id']
            result = twitter.get_user_tweets(user_id, args.limit)
            if 'error' in result:
                print(f"❌ Error: {result['error']}")
            else:
                print(f"\n✅ Found {len(result.get('data', []))} tweets from @{args.username}")
                for tweet in result.get('data', []):
                    print(format_tweet(tweet))

        elif args.command == 'search':
            result = twitter.search_tweets(args.query, args.limit)
            if 'error' in result:
                print(f"❌ Error: {result['error']}")
            else:
                if not result.get('data'):
                    print(f"\n📭 No tweets found matching: '{args.query}'")
                else:
                    print(f"\n✅ Found {len(result['data'])} tweets:")
                    users = {user["id"]: user for user in result.get("includes", {}).get("users", [])}
                    
                    for tweet in result["data"]:
                        author = users.get(tweet.get("author_id", ""), {})
                        metrics = tweet.get("public_metrics", {})
                        print(
                            f"\n👤 @{author.get('username', 'unknown')} {'✓' if author.get('verified') else ''}"
                            f"\n💬 {tweet.get('text')}"
                            f"\n📅 {tweet.get('created_at', 'unknown')}"
                            f"\n❤️  {metrics.get('like_count', 0)} 🔄 {metrics.get('retweet_count', 0)} 💬 {metrics.get('reply_count', 0)}"
                            f"\n{'-' * 50}"
                        )
                    
                    if result.get("meta", {}).get("next_token"):
                        print("\nℹ️ More results available. Use --limit to retrieve more.")

        elif args.command == 'post':
            result = twitter.create_tweet(
                text=args.text,
                media_path=args.media,
                reply_to_id=args.reply_to
            )
            if 'error' in result:
                print(f"❌ Error: {result['error']}")
            else:
                tweet_id = result['data']['id']
                print(f"✅ Tweet posted successfully!")
                # Get and display the posted tweet
                tweet_result = twitter.get_tweet(tweet_id)
                if 'error' not in tweet_result:
                    print(format_tweet(tweet_result['data']))

        elif args.command == 'like':
            result = twitter.like_tweet(args.tweet_id)
            if 'error' in result:
                print(f"❌ Error: {result['error']}")
            else:
                print(f"✅ Successfully liked tweet: {args.tweet_id}")

        elif args.command == 'unlike':
            result = twitter.unlike_tweet(args.tweet_id)
            if 'error' in result:
                print(f"❌ Error: {result['error']}")
            else:
                print(f"✅ Successfully unliked tweet: {args.tweet_id}")

        elif args.command == 'timeline':
            result = twitter.get_home_timeline(args.limit)
            if 'error' in result:
                print(f"❌ Error: {result['error']}")
            else:
                print(f"\n✅ Found {len(result.get('data', []))} tweets in your timeline")
                users = {user["id"]: user for user in result.get("includes", {}).get("users", [])}
                
                for tweet in result.get('data', []):
                    author = users.get(tweet.get("author_id", ""), {})
                    metrics = tweet.get("public_metrics", {})
                    print(
                        f"\n👤 @{author.get('username', 'unknown')} {'✓' if author.get('verified') else ''}"
                        f"\n💬 {tweet.get('text')}"
                        f"\n📅 {tweet.get('created_at', 'unknown')}"
                        f"\n❤️  {metrics.get('like_count', 0)} 🔄 {metrics.get('retweet_count', 0)} 💬 {metrics.get('reply_count', 0)}"
                        f"\n{'-' * 50}"
                    )
                
                if result.get("meta", {}).get("next_token"):
                    print("\nℹ️ More tweets available. Use --limit to retrieve more.")

        elif args.command == 'delete':
            result = twitter.delete_tweet(args.tweet_id)
            if 'error' in result:
                print(f"❌ Error: {result['error']}")
            else:
                print(f"✅ Successfully deleted tweet: {args.tweet_id}")

    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"❌ An error occurred: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()