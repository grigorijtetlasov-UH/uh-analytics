from .security import SecurityCollector
from .economy import EconomyCollector
from .infrastructure import InfrastructureCollector
from .social import SocialCollector
from .realestate import RealEstateCollector
from .market import MarketCollector
from .weather import WeatherCollector
# from .newsfield import NewsFieldCollector (off)

ALL_COLLECTORS = [
    SecurityCollector,
    EconomyCollector,
    InfrastructureCollector,
    SocialCollector,
    RealEstateCollector,
    MarketCollector,
    WeatherCollector,
    # NewsFieldCollector,
]
