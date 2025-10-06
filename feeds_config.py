# feeds_config.py
# Central config for feeds & affiliate status

FEEDS = [
    "freelancer",
    "peopleperhour",
    "kariera",
    "jobfind",
]

# Mark which feeds have affiliate wrapping active (True/False)
AFFILIATE = {
    "freelancer": True,        # has ?referrer=... etc.
    "peopleperhour": False,    # no affiliate (for now)
    "kariera": False,
    "jobfind": False,
}

# Human readable names
FEED_TITLES = {
    "freelancer": "Freelancer",
    "peopleperhour": "PeoplePerHour",
    "kariera": "Kariera.gr",
    "jobfind": "JobFind.gr",
}
