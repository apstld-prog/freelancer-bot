import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_URL = os.getenv("DB_URL")

UPWORK_AFFILIATE_ID = os.getenv("UPWORK_AFFILIATE_ID")
FREELANCER_AFFILIATE_ID = os.getenv("FREELANCER_AFFILIATE_ID")
FIVERR_AFFILIATE_ID = os.getenv("FIVERR_AFFILIATE_ID")

PPH_AFFILIATE_BASE = os.getenv('PPH_AFFILIATE_BASE')


# Optional affiliate placeholders (set later if you join programs)
MALT_AFFILIATE_BASE = os.getenv("MALT_AFFILIATE_BASE")  # e.g., deep link base ending with 'ued='
WORKANA_AFFILIATE_BASE = os.getenv("WORKANA_AFFILIATE_BASE")
TWAGO_AFFILIATE_BASE = os.getenv("TWAGO_AFFILIATE_BASE")
FREELANCERMAP_AFFILIATE_BASE = os.getenv("FREELANCERMAP_AFFILIATE_BASE")
YUNOJUNO_AFFILIATE_BASE = os.getenv("YUNOJUNO_AFFILIATE_BASE")
WORKSOME_AFFILIATE_BASE = os.getenv("WORKSOME_AFFILIATE_BASE")
CODEABLE_AFFILIATE_BASE = os.getenv("CODEABLE_AFFILIATE_BASE")
GURU_AFFILIATE_BASE = os.getenv("GURU_AFFILIATE_BASE")
NINETY9_AFFILIATE_BASE = os.getenv("NINETY9_AFFILIATE_BASE")  # 99designs
WRIPPLE_AFFILIATE_BASE = os.getenv("WRIPPLE_AFFILIATE_BASE")
TOPTAL_AFFILIATE_BASE = os.getenv("TOPTAL_AFFILIATE_BASE")

# Enable/disable sources (default: all enabled)
ENABLE_FREELANCER = (os.getenv("ENABLE_FREELANCER","true").lower() != "false")
ENABLE_PPH = (os.getenv("ENABLE_PPH","true").lower() != "false")
ENABLE_KARIERA = (os.getenv("ENABLE_KARIERA","true").lower() != "false")
ENABLE_JOBFIND = (os.getenv("ENABLE_JOBFIND","true").lower() != "false")
ENABLE_SKYWALKER = (os.getenv("ENABLE_SKYWALKER","true").lower() != "false")
ENABLE_CAREERJET = (os.getenv("ENABLE_CAREERJET","true").lower() != "false")
ENABLE_MALT = (os.getenv("ENABLE_MALT","true").lower() != "false")
ENABLE_WORKANA = (os.getenv("ENABLE_WORKANA","true").lower() != "false")
ENABLE_TWAGO = (os.getenv("ENABLE_TWAGO","true").lower() != "false")
ENABLE_FREELANCERMAP = (os.getenv("ENABLE_FREELANCERMAP","true").lower() != "false")
ENABLE_YUNOJUNO = (os.getenv("ENABLE_YUNOJUNO","true").lower() != "false")
ENABLE_WORKSOME = (os.getenv("ENABLE_WORKSOME","true").lower() != "false")
ENABLE_CODEABLE = (os.getenv("ENABLE_CODEABLE","true").lower() != "false")
ENABLE_GURU = (os.getenv("ENABLE_GURU","true").lower() != "false")
ENABLE_99DESIGNS = (os.getenv("ENABLE_99DESIGNS","true").lower() != "false")
ENABLE_WRIPPLE = (os.getenv("ENABLE_WRIPPLE","true").lower() != "false")
ENABLE_TOPTAL = (os.getenv("ENABLE_TOPTAL","true").lower() != "false")
ADMIN_STATS_NOTIFY = (os.getenv('ADMIN_STATS_NOTIFY','false').lower() == 'true')

