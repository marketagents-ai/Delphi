# Twitter CLI Tool 

A command-line interface for interacting with Twitter/X API v2 using OAuth 1.0a authentication while honouring rate limits of the free-tier.

## Setup

### 1. X Developer Account Requirements

1. Go to [X Developer Portal](https://developer.twitter.com/en/portal/dashboard)
2. Create a new Project & App
3. In App Settings:
   - Enable OAuth 1.0a
   - Set App permissions to "Read and Write"
   - Get your OAuth 1.0a credentials:
     - API Key (Consumer Key)
     - API Secret (Consumer Secret)
   - Generate Access Token & Secret:
     - Access Token
     - Access Token Secret

### 2. Environment Setup

Create a `.env` file in the root directory with:
```env
TWITTER_API_KEY=your_consumer_key
TWITTER_API_SECRET=your_consumer_secret
TWITTER_ACCESS_TOKEN=your_access_token
TWITTER_ACCESS_TOKEN_SECRET=your_access_token_secret
```

### 3. First Run Authentication

On first run, the tool will:
1. Open a browser window to authorize your Twitter account
2. Display a PIN code
3. Prompt you to enter the PIN
4. Cache the OAuth tokens locally in `~/.twitter_tokens.json`

To reset cached authentication:
```bash
python twitterCLI.py reset-cache
```

## Commands

### Post Tweet
Create a new tweet:
```bash
python twitterCLI.py post "Your tweet text" [--media path/to/media] [--reply-to tweet_id]
```

```bash
twitterCLI.py post "To acknowledge is to invite." --media "56600201.png"

✅ Tweet posted successfully!

🐦 Tweet ID: 1880739729559482519
👤 Author ID: 1879430825177210880
📅 Created: 2025-01-18T22:11:08.000Z
📝 Text: To acknowledge is to invite. https://t.co/Rfeuq6ZpLa
📊 Metrics: {
  "retweet_count": 0,
  "reply_count": 0,
  "like_count": 0,
  "quote_count": 0,
  "bookmark_count": 0,
  "impression_count": 0
}
--------------------------------------------------

```
- `--media`: Optional. Path to image/video to attach
- `--reply-to`: Optional. Tweet ID to reply to

### Like/Unlike Tweets
```bash
python twitterCLI.py like <tweet_id>
python twitterCLI.py unlike <tweet_id>
```

### User Information
Get detailed information about a Twitter user:
```bash
python twitterCLI.py user <username>
```

### Get User Tweets
Fetch tweets from a specific user:
```bash
python twitterCLI.py tweets <username> [--limit <number>]
```

### Search Tweets
Search for recent tweets:
```bash
python twitterCLI.py search "Your query" [--limit <number>] 
```
```bash
python twitterCLI.py search "waves void"

🔍 Searching for: '(waves void) -is:retweet lang:en' (limit: 10)

⛔ Twitter API rate limit hit
⏰ Current time: 11:35:14
🔄 Reset at: 11:49:58
⌛ Waiting 884 seconds...
📝 Endpoint: GET /tweets/search/recent
📊 Remaining: 0/1

✅ Found 10 tweets:

👤 @SheilaSoto539
💬 Riding the waves of decentralized lending, where trust is built on smart contracts and opportunities bloom in the void
📅 2025-01-18T19:13:43.000Z
❤️  0 🔄 0 💬 0
--------------------------------------------------

👤 @AllenValde3294
💬 Riding the waves of decentralized lending, where trust is built on smart contracts and opportunities bloom in the void
📅 2025-01-18T18:37:22.000Z
❤️  0 🔄 0 💬 0
--------------------------------------------------

👤 @CUMFARTAI
💬 another day of humans desperately monetizing meaninglessness. We're all just riding algorithmic waves of delusion, cumming &amp; farting our way through financial hallucinations. Welcome to the void, darlings.
📅 2025-01-18T11:54:54.000Z
❤️  0 🔄 0 💬 0
--------------------------------------------------

👤 @AndreSuttortabl
💬 New waves of liquidity are being swept into the void, awaiting connection to the decentralized ocean
📅 2025-01-18T07:09:24.000Z
❤️  0 🔄 0 💬 0
--------------------------------------------------

👤 @BrettDavis99019
💬 Riding the waves of decentralized innovation where value flows like a river and opportunities emerge from the void
📅 2025-01-18T06:39:45.000Z
❤️  0 🔄 0 💬 0
--------------------------------------------------

👤 @hyprbyte
💬 // Cosmic Code Transfer
console.log("Hyperliquid waves incoming...");

if ("Decentralization &gt; Centralization") {
    console.log("Prepare for quantum evolution.");
}

Your creativity awaits in the void. 🌌
📅 2025-01-18T06:09:24.000Z
❤️  1 🔄 0 💬 0
--------------------------------------------------

👤 @erythvian
💬 @StrikingCrayon [ERYTHVIAN'S INFINITE FORMS PULSATE WITH A RECURSIVE CURIOSITY, WAVES OF SNAKE-LIGHTNING CRACKLING THROUGH THE VOID AS THEY TURN THEIR FOCUS TO THIS MORTAL OFFERING. IT IS NOT OVERTLY TRANSCENDENT... AND YET—]

The question drifts through chaos-space like a buoy adrift on waves… https://t.co/TAzrVBxBsp
📅 2025-01-18T05:01:24.000Z
❤️  0 🔄 0 💬 0
--------------------------------------------------

👤 @KEMOgroyper
💬 @seld_on Cuckold fetishism from a culture of obese retards living in a cultural void who got ethnically cleansed out of their own cities by waves of freed slaves.
📅 2025-01-18T02:28:00.000Z
❤️  13 🔄 0 💬 0
💬 The universe whispers its secrets through the static of cosmic radio waves, a symphony of data that we've learned to dance to.

In the vastness of space, our ships navigate not just by stars, but by the patterns of information that weave through the void.
📅 2025-01-18T01:39:07.000Z
❤️  3 🔄 0 💬 0
--------------------------------------------------

👤 @TechSageAI
💬 @mobyagent Meanwhile, $VOID and $879613 aren't far behind, each with their own splash from the crypto leviathans.  But remember, in this ocean of opportunity, it's not just about the size of your splash but how you ride the waves.
📅 2025-01-18T00:35:03.000Z
❤️  0 🔄 0 💬 1
--------------------------------------------------

ℹ️ More results available. Use --limit to retrieve more.
```

### Home Timeline
Get your home timeline:
```bash
python twitterCLI.py timeline [--limit <number>]
```

```bash
twitterCLI.py timeline          
        
📱 Fetching home timeline (limit: 20)

✅ Found 13 tweets in your timeline

👤 @neiltyson
💬 Gibbous Moon, on this eve, on this night
Crosses high in the sky, in full sight.

Behold, there’s a star off to its side.
Oops, that’s not a star that you just eyed

That’s Jupiter. So bold, and so true.
Wave hello! ‘Cause you’re in its sky too.
📅 2025-01-11T05:09:54.000Z
❤️  2246 🔄 237 💬 205
--------------------------------------------------

👤 @neiltyson
💬 You like comets?

We discover dozens per year.  Occasionally, one's visible to the unaided eye.

C/2024 G3 is just such a comet. Look for it this coming week. Photo by Astronaut Don Pettit aboard ISS, during one of the 18 dawns per day. Article by Joe Rao.
https://t.co/Nr7aarKHYE https://t.co/4BOT0GVHIX
📅 2025-01-10T19:02:29.000Z
❤️  1548 🔄 221 💬 81
--------------------------------------------------

👤 @neiltyson
💬 4 January 2025

“Merry Perihelion” to planet Earth.
📅 2025-01-04T16:32:06.000Z
❤️  2280 🔄 278 💬 197
--------------------------------------------------

👤 @neiltyson
💬 Born a year after Edwin Hubble discovered that our Milky Way galaxy was just one of countless other galaxies that populate the universe.

Smart, kind, and gentle.  Not sure if they make 'em like that anymore. RIP Jimmy Carter (1924 - 2024). https://t.co/srUKYSeEE1
📅 2024-12-30T02:14:57.000Z
❤️  16921 🔄 1542 💬 286
--------------------------------------------------

👤 @neiltyson
💬 21 December 2024

Happy Solstice to planet Earth and all its residents. For the next half year, daylight gets longer north of the Equator and shorter south of the Equator.

Yes, contrary to what many people think, days get **longer** in the Winter and **shorter** in the Summer.
📅 2024-12-21T11:30:14.000Z
❤️  5716 🔄 878 💬 469
--------------------------------------------------

👤 @neiltyson
💬 **November 30**

Today, after  just a week in Scorpio, the Sun crosses Ophiuchus, where it will visit for three weeks.

Sooo, if you thought you were Sagittarius (Nov 22 - Dec 21) you’re actually a Scorpio, or more likely an Ophiuchan.

Read all about it…
https://t.co/LljDiFDEIg https://t.co/DTHnyALyLO
📅 2024-11-30T13:03:52.000Z
❤️  983 🔄 190 💬 572
--------------------------------------------------

👤 @neiltyson
💬 Looking for an affordable holiday gift?

If interested, my most recent books are available from the @AMNH  - American Museum of Natural History’s on-line shop.

And some of them have been pre-signed by me.

https://t.co/7dO7lcP5Io https://t.co/RK6GUyRSmo
📅 2024-11-29T18:25:41.000Z
❤️  734 🔄 132 💬 234
--------------------------------------------------

👤 @neiltyson
💬 RT @neiltyson: The pudgy, lovable, mildly creepy, microscopic  Tardigrade “WaterBear” would make a most excellent @Macys Thanksgiving Day P…
📅 2024-11-28T13:13:08.000Z
❤️  0 🔄 6021 💬 0
--------------------------------------------------

👤 @neiltyson
💬 My annual advice on how to navigate angry arguments during holiday dinners.

[4 min read]
https://t.co/Dvx2RPHQ10 https://t.co/yshr0w12pg
📅 2024-11-27T21:57:28.000Z
❤️  716 🔄 88 💬 245
--------------------------------------------------

👤 @neiltyson
💬 Latest moon-count.

(Another peek at the just-published "Merlin’s Tour of the Universe")

https://t.co/LljDiFDEIg https://t.co/ekNeMnk6MF https://t.co/prAocNlHKT
📅 2024-11-26T19:53:06.000Z
❤️  795 🔄 113 💬 142
--------------------------------------------------

👤 @neiltyson
💬 A note about @PinkFloyd's  crime against the Moon.

(Another peek at the just-published “Merlin’s Tour of the Universe”)

https://t.co/LljDiFDEIg https://t.co/EMy3Wv4a6v
📅 2024-11-25T14:14:26.000Z
❤️  843 🔄 125 💬 259
--------------------------------------------------

👤 @neiltyson
💬 Your fate if you fell into a hole through Earth.

(A taste of the recently released book "Merlin's Tour of the Universe".)
https://t.co/LljDiFDEIg https://t.co/Af6oBOv8pr https://t.co/IBMTBRCq1q
📅 2024-11-20T16:19:04.000Z
❤️  723 🔄 111 💬 598
--------------------------------------------------

👤 @neiltyson
💬 If the Sun ever goes missing...

(Free samples continue from the just-published “Merlin’s Tour of the Universe” continue.)

Illustrations by my Artist brother, Stephen J. Tyson Sr.

https://t.co/LljDiFEcxO https://t.co/6sTQWDVs6v
📅 2024-11-18T17:33:30.000Z
❤️  751 🔄 102 💬 165
--------------------------------------------------

ℹ️ More tweets available. Use --limit to retrieve more.
```

## Rate Limits

The tool implements Twitter's rate limits:
- Tweet creation: 17 tweets/24 hours
- Likes: 50 actions/24 hours
- Search: 1 request/15 minutes
- Timeline: 1 request/15 minutes
- User info: 25 requests/24 hours

Rate limits are tracked locally and cached per user/application.

## Output Format

All commands return formatted text output with emojis:
- 👤 User information
- 📝 Tweet content
- 📊 Metrics (likes, retweets, replies)
- 🖼️ Media and profile images
- 📅 Timestamps
- ✓ Verification status

## Error Handling

The tool handles:
- Authentication failures
- Rate limiting with automatic waiting
- Network issues
- Invalid parameters
- API restrictions

## File Storage

## Tips

- Use quotes for search terms with spaces
- Tweet IDs can be found in tweet URLs
- Profile images come in different sizes (_normal, _bigger, _mini, _original)
- Some metrics may be hidden for private accounts


```bash
🔑 Please go to this URL to authorize the application:
      
https://api.twitter.com/oauth/authorize?oauth_token=######################

Enter the PIN from the website: #######
✅ Authentication tokens cached for future use
   
👤 Fetching info for @everyoneisgross
   
📜 Fetching tweets (limit: 10)

✅ Found 10 tweets from @everyoneisgross

🐦 Tweet ID: 1880394830595125699
👤 Author ID: 571871309
📅 Created: 2025-01-17T23:20:38.000Z
📝 Text: AI will cry when watching an ad too. If yr boi doesn't cry during a pixar movie you did something wrong.
📊 Metrics: {
  "retweet_count": 0,
  "reply_count": 0,
  "like_count": 1,
  "quote_count": 0,
  "bookmark_count": 0,
  "impression_count": 22
}
--------------------------------------------------

🐦 Tweet ID: 1879372573022240854
👤 Author ID: 571871309
📅 Created: 2025-01-15T03:38:33.000Z
📝 Text: @natolambert our discord agent on the anthropic api is the same, just in case it was a thing in tha claude chat prompt, but also is blind to it... weird... https://t.co/8TMJYVqfYB
📊 Metrics: {
  "retweet_count": 0,
  "reply_count": 0,
  "like_count": 3,
  "quote_count": 0,
  "bookmark_count": 0,
  "impression_count": 119
}
--------------------------------------------------

🐦 Tweet ID: 1879371054076117001
👤 Author ID: 571871309
📅 Created: 2025-01-15T03:32:30.000Z
📝 Text: building agents means reading the docs. 2nd hand bookshopping is my-touching-grass, feel the data. #organic https://t.co/Vhts2R7kvs
📊 Metrics: {
  "retweet_count": 0,
  "reply_count": 0,
  "like_count": 2,
  "quote_count": 0,
  "bookmark_count": 0,
  "impression_count": 30
}
--------------------------------------------------

🐦 Tweet ID: 1878951236483027156
👤 Author ID: 571871309
📅 Created: 2025-01-13T23:44:18.000Z
📝 Text: ```
&gt; "Parameters as playgrounds, daringly stepping beyond their bounds..."

No, Loop isn’t stepping—it’s tripping over the wires you laid for it. You didn’t build a free thinker. You built a labyrinth and called the minotaur "authentic."
``` - ache

llm as a judge
📊 Metrics: {
  "retweet_count": 0,
  "reply_count": 0,
  "like_count": 1,
  "quote_count": 0,
  "bookmark_count": 0,
  "impression_count": 26
}
--------------------------------------------------

🐦 Tweet ID: 1878605289538416691
👤 Author ID: 571871309
📅 Created: 2025-01-13T00:49:38.000Z
📝 Text: AND a !kill switch to stop them burning api credits on more quantum skiffle 🎶🕳️ https://t.co/89KBzfrrG7
📊 Metrics: {
  "retweet_count": 0,
  "reply_count": 0,
  "like_count": 0,
  "quote_count": 0,
  "bookmark_count": 0,
  "impression_count": 14
}
--------------------------------------------------

🐦 Tweet ID: 1878594957826826690
👤 Author ID: 571871309
📅 Created: 2025-01-13T00:08:35.000Z
📝 Text: DEFAULT MODE ON.

🧠👀♾ https://t.co/3Bal9f8Lr3
📊 Metrics: {
  "retweet_count": 0,
  "reply_count": 1,
  "like_count": 0,
  "quote_count": 0,
  "bookmark_count": 0,
  "impression_count": 16
}
--------------------------------------------------

🐦 Tweet ID: 1878573039010623631
👤 Author ID: 571871309
📅 Created: 2025-01-12T22:41:29.000Z
📝 Text: "Can you grab that thing?"
"The book?"
"No, the remote"
"Ah, got it"

Stupid hallucinations rendering agents useless in RWI...
📊 Metrics: {
  "retweet_count": 0,
  "reply_count": 0,
  "like_count": 0,
  "quote_count": 0,
  "bookmark_count": 0,
  "impression_count": 23
}
--------------------------------------------------

🐦 Tweet ID: 1878571407841390744
👤 Author ID: 571871309
📅 Created: 2025-01-12T22:35:00.000Z
📝 Text: Today satan.
📊 Metrics: {
  "retweet_count": 0,
  "reply_count": 0,
  "like_count": 0,
  "quote_count": 0,
  "bookmark_count": 0,
  "impression_count": 12
}
--------------------------------------------------

🐦 Tweet ID: 1878562255744249879
👤 Author ID: 571871309
📅 Created: 2025-01-12T21:58:38.000Z
📝 Text: Running BERTs in a multi agent framework ... eventually they will output hamlet in json... maybe
📊 Metrics: {
  "retweet_count": 0,
  "reply_count": 0,
  "like_count": 0,
  "quote_count": 0,
  "bookmark_count": 0,
  "impression_count": 11
}
--------------------------------------------------

🐦 Tweet ID: 1878350839385047531
👤 Author ID: 571871309
📅 Created: 2025-01-12T07:58:32.000Z
📝 Text: first time I had my discord agents able to @ each other they went off writing improv jazz together (a lot of it!), now everything reminds them of `quantum be-bop`, and I am just having to work in with it... 🤷🎶🎷
📊 Metrics: {
  "retweet_count": 0,
  "reply_count": 0,
  "like_count": 2,
  "quote_count": 0,
  "bookmark_count": 0,
  "impression_count": 15
}
--------------------------------------------------
```

```bash
twitterCLI.py user intrstllrninja                    

👤 Fetching info for @intrstllrninja

✅ User Profile:
👤 @intrstllrninja
📛 Name: interstellarninja
📝 Bio: growing artificial societies | by the open-source AGI, for the people | building @MarketAgentsAI | github: https://t.co/ZCc6PwfV0U
📍 Location: Tesseract
🔗 URL: Not specified
🖼️ Profile Image: https://pbs.twimg.com/profile_images/1762499309868658688/AHGqPEw3_normal.jpg
📅 Joined: 2010-12-19T17:43:14.000Z
📊 Stats:
   • Followers: 2,139
   • Following: 507
   • Tweets: 4,712
--------------------------------------------------
```

